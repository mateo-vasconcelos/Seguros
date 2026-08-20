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
    """Lee el archivo original tal cual. No transforma nada."""
    # TODO: pd.read_excel(ruta)
    ...


def normalizar_tipos(df):
    """Convierte FECHA_CORTE a datetime y agrega columnas ANIO y MES."""
    # TODO: pd.to_datetime en FECHA_CORTE
    # TODO: df["ANIO"] = df["FECHA_CORTE"].dt.year
    # TODO: df["MES"]  = df["FECHA_CORTE"].dt.month
    ...


def normalizar_texto(df):
    """
    Limpia las columnas de texto: quita espacios sobrantes y unifica may/min.

    Ojo: revisa ANTES si hay variantes del mismo nombre de institución a lo
    largo de los años (fusiones, cambios de razón social). Si las hay, aquí
    es donde se mapean a un nombre canónico.
    """
    # TODO: .str.strip() en las columnas de LLAVES
    ...


def desacumular(df):
    """
    Convierte los montos acumulados del año en flujo mensual.

    Dentro de cada (institución, ramo, entidad, año), ordenado por fecha:
        flujo[mes] = acumulado[mes] - acumulado[mes anterior]
    y enero se queda igual, porque ahí el acumulado se reinicia.

    Solo aplica a COLS_FLUJO. Las COLS_SALDO se dejan intactas.
    """
    # TODO: ordenar por LLAVES + FECHA_CORTE
    # TODO: agrupar por LLAVES + ANIO y usar .diff() sobre COLS_FLUJO
    # TODO: rellenar el primer mes de cada grupo con su valor original
    ...


def guardar(df, ruta=RUTA_LIMPIA):
    """Guarda el resultado en Parquet (conserva tipos y pesa mucho menos)."""
    # TODO: ruta.parent.mkdir(parents=True, exist_ok=True)
    # TODO: df.to_parquet(ruta, index=False)
    ...