"""
Pipeline de limpieza de la base de Tendencias del Seguro (SIO - CNSF).

Transforma el archivo crudo en un dataset analítico listo para calcular métricas.
Cada función hace UNA cosa: así se pueden probar y depurar por separado.
"""

from pathlib import Path
import pandas as pd

# Rutas del proyecto (relativas a la raíz del repo, no al notebook)
RAIZ = Path(__file__).resolve().parents[1]
RUTA_CRUDA = RAIZ / "data" / "raw" / "tendencias_seguro_2026-06.xlsx"
RUTA_LIMPIA = RAIZ / "data" / "processed" / "sio_mensual.parquet"

# Llaves que identifican una serie temporal única dentro de la base
LLAVES = ["NOMBRE_CORTO", "DESC_RAMO", "DESC_ENTIDADFEDERATIVA"]

# Columnas de flujo: se acumulan durante el año y hay que desacumular
COLS_FLUJO = ["NUM_SIN_O_RECLAMACION", "PRIMA_EMI", "MONTO_SIN"]

# Columnas de saldo: son fotos a la fecha de corte, NO se desacumulan
COLS_SALDO = ["RIESGOS_ASEG_VIG", "SUMA_ASEG"]


def cargar_crudo(ruta=RUTA_CRUDA):
    """Lee el archivo original, no transforma nada."""
    return pd.read_excel(ruta)



def normalizar_tipos(df):
    """Convierte FECHA_CORTE a datetime y agrega columnas ANIO y MES."""
    df = df.copy()
    df["FECHA_CORTE"]=pd.to_datetime(df["FECHA_CORTE"])
    df["ANIO"] = df["FECHA_CORTE"].dt.year
    df["MES"]  = df["FECHA_CORTE"].dt.month
    return df



def normalizar_texto(df):
    """
    Limpia las columnas de texto: quita espacios sobrantes y unifica may/min.

    Ojo: revisa ANTES si hay variantes del mismo nombre de institución a lo
    largo de los años (fusiones, cambios de razón social). Si las hay, aquí
    es donde se mapean a un nombre canónico.
    """
    df = df.copy()
    df["NOMBRE_CORTO"]=df["NOMBRE_CORTO"].str.strip()
    df["DESC_RAMO"]=df["DESC_RAMO"].str.strip()
    df["DESC_ENTIDADFEDERATIVA"]=df["DESC_ENTIDADFEDERATIVA"].str.strip()
    return df


def desacumular(df):
    """
    Convierte los montos acumulados del año en flujo mensual.

    Dentro de cada (institución, ramo, entidad, año), ordenado por fecha:
        flujo[mes] = acumulado[mes] - acumulado[mes anterior]
    y enero se queda igual, porque ahí el acumulado se reinicia.

    Solo aplica a COLS_FLUJO. Las COLS_SALDO se dejan intactas.

    No necesita df.copy(): sort_values ya devuelve un objeto nuevo.
    """
    df = df.sort_values(LLAVES + ["FECHA_CORTE"])
    df[COLS_FLUJO] = df.groupby(LLAVES + ["ANIO"])[COLS_FLUJO].diff().fillna(df[COLS_FLUJO])
    df = df[df.ANIO > 2021]
    return df



def validar(crudo, limpio):
    """
    Comprueba que el desacumulado sea correcto, comparando contra el crudo.

    La prueba de fondo es exacta, no aproximada: si el flujo mensual esta bien
    calculado, volver a acumularlo dentro de cada (LLAVES, ANIO) tiene que
    reproducir la columna original peso por peso.

    `crudo` es el df ANTES de desacumular (ya con ANIO/MES) y `limpio` el de
    despues. Devuelve un DataFrame con una fila por prueba; revisa que la
    columna `ok` sea True en todas.
    """
    pruebas = []

    # 1. reacumular debe devolver el valor original.
    #    El .loc empareja por indice, no por posicion: desacumular reordena y
    #    filtra filas, asi que comparar por posicion daria resultados falsos.
    recalc = limpio.groupby(LLAVES + ["ANIO"])[COLS_FLUJO].cumsum()
    original = crudo.loc[recalc.index, COLS_FLUJO]
    for c in COLS_FLUJO:
        desv = (recalc[c] - original[c]).abs().max()
        pruebas.append((f"cumsum reproduce {c}", desv == 0, f"desviacion max = {desv:,.0f}"))

    # 2. las columnas de saldo son fotos a la fecha de corte: nadie las toca
    for c in COLS_SALDO:
        igual = limpio[c].equals(crudo.loc[limpio.index, c])
        pruebas.append((f"{c} sin modificar", igual, "intacta" if igual else "FUE MODIFICADA"))

    # 3. el filtro de anio no debe perder ni agregar filas de mas
    esperado = int((crudo["ANIO"] > 2021).sum())
    pruebas.append(("filas tras filtrar 2021", len(limpio) == esperado,
                    f"{len(limpio):,} filas (esperadas {esperado:,})"))

    # 4. desacumular no debe dejar huecos donde antes habia numeros
    nulos = int(limpio[COLS_FLUJO].isna().sum().sum())
    pruebas.append(("sin nulos en COLS_FLUJO", nulos == 0, f"{nulos:,} nulos"))

    return pd.DataFrame(pruebas, columns=["prueba", "ok", "detalle"])


def guardar(df, ruta=RUTA_LIMPIA):
    """Guarda el resultado en Parquet (conserva tipos y pesa mucho menos)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ruta, index=False)