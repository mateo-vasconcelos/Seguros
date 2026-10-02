"""
Métricas de benchmarking sobre el dataset limpio del SIO (CNSF).

Todas las funciones reciben el DataFrame ya procesado por pipeline.py
(flujos mensuales, fechas como datetime) y devuelven un DataFrame agregado.

Convención: ninguna función modifica el DataFrame que recibe.
"""

import warnings

import numpy as np
import pandas as pd

# Columna que identifica a la institución: eje fijo de todas las métricas.
INSTITUCION = "NOMBRE_CORTO"

# La base viene en pesos. Los reportes del sector se leen en millones (mdp).
MDP = 1_000_000

# --- umbrales de alerta de siniestralidad ------------------------------------
# Calibrados sobre 2025 (440 pares institución x ramo). Ver alerta_siniestralidad.
VOLUMEN_MIN = 50        # mdp de prima; por debajo, el cociente es ruido
UMBRAL_ATENCION = 1.5   # rangos intercuartiles sobre la mediana del ramo
UMBRAL_GRAVE = 3.0
SINIESTRALIDAD_CRITICA = 100.0   # %; por encima, los siniestros exceden la prima

# Margen dentro del cual una razón contra el mercado se considera "en línea".
# Sin él, un ramo 3% arriba se diagnosticaría como problema.
TOLERANCIA = 0.15


def nombre_ramo(ramo):
    """
    Nombre del ramo sin el paréntesis aclaratorio de la fuente.

    La base trae tres ramos con una aclaración entre paréntesis —"Gastos
    Médicos (incluye Ind, Gpo y Col)" y dos más—. Es útil en el dato pero
    estorba al leer un resumen. Los DataFrames conservan el nombre completo;
    solo el texto redactado usa el corto.
    """
    return ramo.split(" (")[0]


def _grupos(por, periodo=None):
    """Arma la lista de columnas de agrupación, sin duplicados y en orden."""
    cols = ([periodo] if periodo else []) + list(por)
    return list(dict.fromkeys(cols))


def _dividir(numerador, denominador):
    """
    Cociente que devuelve NaN donde el denominador no es positivo.

    Sin esta guarda pandas produce inf (x/0) o 0/0 -> NaN de forma
    inconsistente, y un solo inf arruina cualquier promedio posterior.
    """
    return numerador / denominador.where(denominador > 0)


def filtrar(df, institucion=None, ramo=None, entidad=None, anio=None):
    """
    Filtro de conveniencia para acotar el DataFrame antes de calcular.
    Cualquier parámetro en None significa "no filtrar por ese criterio".

    Cada criterio acepta un valor suelto o una lista:

        filtrar(df, institucion="AXA Seguros", anio=[2025, 2026])

    Los nombres deben coincidir exactos con los del dataset. Si te equivocas
    en uno, no hay error: devuelve un DataFrame vacío. Revisa `len()` del
    resultado antes de calcular sobre él.
    """
    criterios = {
        INSTITUCION: institucion,
        "DESC_RAMO": ramo,
        "DESC_ENTIDADFEDERATIVA": entidad,
        "ANIO": anio,
    }

    # Se acumulan todas las condiciones en una sola máscara y se aplica una
    # vez al final: filtrar en cadena crearía un DataFrame intermedio por
    # criterio, y sobre 694 mil filas eso se nota.
    mascara = pd.Series(True, index=df.index)
    for columna, valor in criterios.items():
        if valor is None:
            continue
        # is_list_like trata las cadenas como valor suelto, que es justo lo
        # que queremos: "AXA Seguros" no debe leerse como lista de letras.
        valores = valor if pd.api.types.is_list_like(valor) else [valor]
        mascara &= df[columna].isin(valores)

    # La indexación booleana ya devuelve un objeto nuevo: no hay riesgo de
    # modificar el df original, y por eso no hace falta .copy().
    return df[mascara]


def participacion_mercado(df, por=("DESC_RAMO",), periodo="ANIO"):
    """
    Participación de mercado de cada institución.

        participación = prima de la institución / prima total del mercado

    El denominador se calcula sobre el mismo nivel de agregación que `por`.
    Devuelve una fila por institución × grupo × periodo.

    Unidades, marcadas en el nombre de cada columna:

        prima_mdp, mercado_mdp   millones de pesos
        participacion_pct        porcentaje (30.0 = 30%)

    Los valores no vienen redondeados: redondear es cosa de la presentación,
    y hacerlo aquí arrastraría el error a `comparar_vs_mercado`. Para mostrar:

        part.round({"prima_mdp": 1, "mercado_mdp": 1, "participacion_pct": 2})
    """
    grupos = ([periodo] if periodo else []) + list(por)

    if INSTITUCION in grupos:
        raise ValueError(
            f"{INSTITUCION} ya es el eje de la métrica: no lo pases en `por`."
        )

    # Numerador: lo que emitió cada institución dentro de cada celda.
    tabla = df.groupby(grupos + [INSTITUCION])["PRIMA_EMI"].sum().reset_index()
    tabla = tabla.rename(columns={"PRIMA_EMI": "prima_mdp"})

    # Denominador: el total del mercado en esa misma celda. Se usa transform y
    # no otro groupby porque transform devuelve el total repetido en cada fila,
    # ya alineado; dividir dos Series con distinto número de niveles de índice
    # no alinea solo y produce NaN silenciosos.
    if grupos:
        tabla["mercado_mdp"] = tabla.groupby(grupos)["prima_mdp"].transform("sum")
    else:
        # Sin grupos el mercado es una sola celda: todo el DataFrame.
        tabla["mercado_mdp"] = tabla["prima_mdp"].sum()

    # El cociente se calcula ANTES de cambiar de unidad: es adimensional, así
    # que da igual, pero dividir pesos entre pesos evita dudas al leer el code.
    # Un mercado con prima total 0 no tiene participación definida; sin la
    # guarda pandas devolvería inf y arruinaría cualquier promedio posterior.
    tabla["participacion_pct"] = 100 * (
        tabla["prima_mdp"] / tabla["mercado_mdp"].where(tabla["mercado_mdp"] != 0)
    )

    tabla[["prima_mdp", "mercado_mdp"]] /= MDP

    return tabla.sort_values(grupos + ["participacion_pct"],
                             ascending=[True] * len(grupos) + [False],
                             ignore_index=True)


def siniestralidad(df, por=(INSTITUCION, "DESC_RAMO"), periodo="ANIO"):
    """
    Índice de siniestralidad aproximado:

        siniestralidad = MONTO_SIN / PRIMA_EMI

    OJO: es una aproximación sobre cifras DIRECTAS y EMITIDAS. La
    siniestralidad técnica del glosario usa cifras retenidas y devengadas,
    que esta base no trae. Documenta la diferencia al presentar resultados.

    Columnas: prima_mdp, monto_mdp (millones de pesos) y siniestralidad_pct
    (porcentaje: 65.0 = se pagaron 65 centavos de siniestro por peso emitido).
    """
    grupos = _grupos(por, periodo)

    # Ambas son columnas de flujo, ya desacumuladas por el pipeline: sumarlas
    # a lo largo del periodo es correcto.
    tabla = df.groupby(grupos)[["PRIMA_EMI", "MONTO_SIN"]].sum().reset_index()
    tabla = tabla.rename(columns={"PRIMA_EMI": "prima_mdp", "MONTO_SIN": "monto_mdp"})

    # Razón de sumas, no promedio de razones: la siniestralidad del grupo es
    # el monto total entre la prima total. Promediar los cocientes mensuales
    # le daría el mismo peso a un mes chico que a uno grande.
    tabla["siniestralidad_pct"] = 100 * _dividir(tabla["monto_mdp"], tabla["prima_mdp"])

    tabla[["prima_mdp", "monto_mdp"]] /= MDP
    return tabla.sort_values(grupos, ignore_index=True)


def frecuencia_severidad(df, por=(INSTITUCION, "DESC_RAMO"), periodo="ANIO"):
    """
    Descompone el costo de siniestros en sus dos factores:

        frecuencia = NUM_SIN_O_RECLAMACION / RIESGOS_ASEG_VIG
        severidad  = MONTO_SIN / NUM_SIN_O_RECLAMACION

    CUIDADO CON EL DENOMINADOR DE LA FRECUENCIA. RIESGOS_ASEG_VIG es una
    columna de SALDO: cada fila es una foto de los riesgos vigentes a esa
    fecha de corte, no un flujo del mes. Sumar los doce meses cuenta doce
    veces la misma póliza e infla el denominador por un factor de ~12.

    Aquí se usa el PROMEDIO de las fotos mensuales como exposición del
    periodo, que es la aproximación actuarial habitual. Si prefieres la foto
    de cierre, cambia el .mean() por .last() — el resultado cambia poco
    cuando la cartera es estable, y mucho cuando está creciendo rápido.

    Columnas: expuestos (riesgos promedio), siniestros, monto_mdp,
    frecuencia_pct (5.0 = 5 siniestros por cada 100 riesgos) y
    severidad_pesos (costo promedio por siniestro, en pesos).
    """
    grupos = _grupos(por, periodo)

    # Flujos: se suman a lo largo del periodo sin problema.
    tabla = (df.groupby(grupos)[["NUM_SIN_O_RECLAMACION", "MONTO_SIN"]]
               .sum().reset_index()
               .rename(columns={"NUM_SIN_O_RECLAMACION": "siniestros",
                                "MONTO_SIN": "monto_mdp"}))

    # Saldo: primero se suman las fotos del mismo mes (sumar entre entidades o
    # ramos sí es válido: son pólizas distintas), y luego se promedian los
    # meses. Nunca se suman meses entre sí.
    llave_mes = list(dict.fromkeys(grupos + ["ANIO", "MES"]))
    mensual = df.groupby(llave_mes)["RIESGOS_ASEG_VIG"].sum().reset_index()
    expuestos = mensual.groupby(grupos)["RIESGOS_ASEG_VIG"].mean()

    tabla = tabla.merge(expuestos.rename("expuestos"), on=grupos, how="left")

    tabla["frecuencia_pct"] = 100 * _dividir(tabla["siniestros"], tabla["expuestos"])
    # Sin siniestros no hay costo promedio que calcular: queda NaN, no 0.
    tabla["severidad_pesos"] = _dividir(tabla["monto_mdp"], tabla["siniestros"])

    tabla["monto_mdp"] /= MDP
    columnas = grupos + ["expuestos", "siniestros", "monto_mdp",
                         "frecuencia_pct", "severidad_pesos"]
    return tabla[columnas].sort_values(grupos, ignore_index=True)


def crecimiento_anual(df, por=(INSTITUCION, "DESC_RAMO"), meses=None):
    """
    Crecimiento nominal de primas contra el mismo periodo del año anterior.

    Compara periodos equivalentes (ene-jun 2026 contra ene-jun 2025), no
    años completos contra años parciales.

    `meses=None` recorta TODOS los años a los meses disponibles en el año más
    reciente. Como la base llega a junio de 2026, eso significa que todas las
    filas son acumulados ene-jun: comparables entre sí, pero NO son cifras de
    año completo. Pasa meses=range(1, 13) si quieres años cerrados, sabiendo
    que entonces el último año quedará a la mitad y su caída será ficticia.

    Columnas: prima_mdp, prima_previa_mdp y crecimiento_pct.
    """
    por = list(por)

    if meses is None:
        ultimo = df["ANIO"].max()
        meses = sorted(df.loc[df["ANIO"] == ultimo, "MES"].unique())
    df = df[df["MES"].isin(list(meses))]

    tabla = (df.groupby(["ANIO"] + por)["PRIMA_EMI"].sum().reset_index()
               .rename(columns={"PRIMA_EMI": "prima_mdp"})
               .sort_values(por + ["ANIO"], ignore_index=True))
    tabla["prima_mdp"] /= MDP

    # shift(1) toma la fila anterior del grupo, que no siempre es el año
    # anterior: si una aseguradora no reportó en 2023, compararía 2024 contra
    # 2022 y lo etiquetaría como crecimiento anual. Por eso se desplaza también
    # el año y solo se conserva el par cuando de verdad son consecutivos.
    previa = tabla.groupby(por)[["ANIO", "prima_mdp"]].shift(1)
    consecutivos = previa["ANIO"] == tabla["ANIO"] - 1
    tabla["prima_previa_mdp"] = previa["prima_mdp"].where(consecutivos)

    # _dividir exige denominador positivo, y aquí eso importa de más: hay 15
    # grupos con prima anual negativa (cancelaciones que superan lo emitido).
    # Un porcentaje sobre base negativa invierte el signo y miente.
    tabla["crecimiento_pct"] = 100 * _dividir(
        tabla["prima_mdp"] - tabla["prima_previa_mdp"], tabla["prima_previa_mdp"]
    )

    # Queda anotada la ventana usada. Sin esto, quien reciba la tabla no puede
    # saber que las primas son de medio año y las compararía contra umbrales
    # calibrados sobre cifras anuales.
    # Enteros de Python, no de numpy: estos attrs viajan a Streamlit, que los
    # serializa a JSON y no sabe qué hacer con un np.int32.
    tabla.attrs["meses"] = [int(m) for m in meses]
    return tabla


def comparar_vs_mercado(df, institucion, metrica_fn, por=("DESC_RAMO",), **kwargs):
    """
    Pone lado a lado el indicador de una institución y el del mercado total.

    Es la función que produce la tabla central del benchmarking: para cada
    ramo, el valor de la institución, el del mercado, y la diferencia.

        comparar_vs_mercado(filtrar(df, anio=2025), "Seguros Sura", siniestralidad)

    El truco es que las métricas agregan lo que reciban: la misma función,
    corrida sobre el subconjunto de una institución y sobre el DataFrame
    completo, produce las dos mitades de la comparación. Por eso `por` NO
    lleva la institución: es la dimensión contra la que se compara.

    El mercado INCLUYE a la institución, que es la convención del sector
    (participación sobre el total, no sobre los competidores). En una
    aseguradora dominante eso diluye la diferencia; tenlo presente.

    Solo salen los grupos donde la institución opera. Las columnas terminan en
    _inst, _mercado y _dif. Ojo: la diferencia entre dos columnas _pct está en
    PUNTOS porcentuales, no en porcentaje de cambio.
    """
    if metrica_fn is participacion_mercado:
        raise ValueError(
            "participacion_mercado ya es una comparación contra el mercado: "
            "úsala directo y filtra el resultado con filtrar(part, institucion=...)."
        )

    por = list(por)
    if INSTITUCION in por:
        raise ValueError(
            f"{INSTITUCION} es el eje de la comparación: no lo pases en `por`."
        )

    lado_inst = metrica_fn(filtrar(df, institucion=institucion), por=por, **kwargs)
    lado_mercado = metrica_fn(df, por=por, **kwargs)

    # Las llaves son las columnas de agrupación; todo lo demás son los
    # indicadores que calcula la métrica, sean los que sean.
    llaves = [c for c in _grupos(por, kwargs.get("periodo", "ANIO"))
              if c in lado_inst.columns and c in lado_mercado.columns]
    valores = [c for c in lado_inst.columns
               if c not in llaves and c in lado_mercado.columns]

    tabla = lado_inst[llaves + valores].merge(
        lado_mercado[llaves + valores], on=llaves,
        how="left", suffixes=("_inst", "_mercado"),
    )

    # merge descarta attrs, así que la anotación de la métrica se vuelve a
    # poner a mano; si no, se pierde la ventana de meses en el camino.
    tabla.attrs.update(lado_inst.attrs)

    for col in valores:
        tabla[f"{col}_dif"] = tabla[f"{col}_inst"] - tabla[f"{col}_mercado"]

    # Las tres versiones de cada indicador quedan juntas, en vez de dispersas.
    orden = llaves + [f"{c}{s}" for c in valores
                      for s in ("_inst", "_mercado", "_dif")]
    return tabla[orden]


def alerta_siniestralidad(df, institucion, periodo="ANIO", volumen_min=VOLUMEN_MIN):
    """
    Marca los ramos donde la siniestralidad de una institución es preocupante.

    POR QUÉ NO UN UMBRAL FIJO EN PUNTOS. La dispersión de la siniestralidad
    cambia por completo entre ramos: medido sobre 2025, el rango intercuartil
    va de 0.8 puntos en Terremoto a 71 en Incendio. Estar 20 puntos arriba del
    mercado es catastrófico en el primero y perfectamente ordinario en el
    segundo. Un solo número en puntos marca de más en unos ramos y de menos en
    otros.

    Por eso la diferencia se mide en RANGOS INTERCUARTILES del propio ramo:
    cuántas veces la dispersión típica de ese mercado se separa la institución
    de su mediana. 1.5 es la convención de Tukey para señalar un valor atípico;
    3.0 ya es un extremo.

    POR QUÉ HAY COMPUERTA DE VOLUMEN. Una cartera chica produce cocientes
    salvajes: la diferencia mediana absoluta es de 64 puntos en carteras de
    menos de 1 mdp y de 10.5 puntos en las de más de 1,000. Marcar carteras
    diminutas es marcar ruido, así que por debajo de `volumen_min` se devuelve
    "sin volumen" en vez de una bandera.

    La dispersión del ramo también se estima solo con carteras que pasan la
    compuerta, para que el ruido de las chicas no la infle.

    SON DOS SEÑALES DISTINTAS, EN DOS COLUMNAS.

    `bandera` es relativa: qué tan lejos está la institución de lo que hacen
    sus competidores en ese ramo. Valores: "grave" (>= 3 IQR), "atención"
    (>= 1.5 IQR), "normal", "sin volumen" y "no comparable" —esta última
    cuando la siniestralidad del mercado no es positiva y comparar contra ella
    no significa nada, como en Cascos Embarcaciones 2025.

    `sobre_prima` es absoluta: True cuando la siniestralidad pasa de 100%, es
    decir cuando se pagó más en siniestros que lo que se emitió en prima. Es un
    hecho financiero que no depende del mercado.

    `causa_dominante` responde la pregunta siguiente: el resultado se desvía,
    ¿por el riesgo o por la tarifa? Vale para todos los ramos, no solo para
    los que salen "ninguno". Hace falta porque `diagnostico` puede apuntar al
    lugar equivocado: Sura en Vida 2025 sale "severidad" —1.33x, apenas sobre
    la tolerancia— cuando su verdadero problema es que cobra 0.23x la prima
    del mercado. Ahí `causa_dominante` dice "precio".

    Se separan porque no son la misma pregunta y colapsarlas invierte la
    escala. FM Global tuvo 174.9% en Incendio 2025 —pérdida técnica clara— pero
    a solo 1.9 IQR de sus competidores, porque Incendio es un ramo muy disperso
    (IQR de 71 puntos). Es "sobre_prima" sin ser "grave", y las dos cosas son
    ciertas a la vez. Para marcar en un reporte, combínalas según lo que
    quieras destacar.
    """
    grupos = _grupos(("DESC_RAMO",), periodo)

    de_todos = siniestralidad(df, por=("DESC_RAMO",), periodo=periodo).rename(
        columns={"siniestralidad_pct": "mercado_pct"})[grupos + ["mercado_pct"]]
    por_institucion = siniestralidad(df, por=(INSTITUCION, "DESC_RAMO"), periodo=periodo)

    tabla = por_institucion.merge(de_todos, on=grupos)
    tabla["dif"] = tabla["siniestralidad_pct"] - tabla["mercado_pct"]

    # Escala robusta del ramo: mediana e intercuartil de las diferencias, sobre
    # las carteras con volumen. Mediana e IQR y no media y desviación porque
    # unos pocos valores de 400% arrastrarían cualquier estadístico no robusto.
    con_volumen = tabla[tabla["prima_mdp"] >= volumen_min]
    escala = con_volumen.groupby(grupos)["dif"].agg(
        centro="median", iqr=lambda s: s.quantile(0.75) - s.quantile(0.25))

    mia = tabla[tabla[INSTITUCION] == institucion].merge(escala, on=grupos, how="left")

    # Un IQR de cero (todas las instituciones en el mismo punto) haría explotar
    # la división; ahí no hay dispersión que medir y la señal queda indefinida.
    mia["iqrs"] = (mia["dif"] - mia["centro"]) / mia["iqr"].where(mia["iqr"] > 0)

    def bandera(fila):
        if fila["prima_mdp"] < volumen_min:
            return "sin volumen"
        if not fila["mercado_pct"] > 0:
            return "no comparable"
        if pd.isna(fila["iqrs"]):
            return "normal"         # el ramo no tiene dispersión que medir
        if fila["iqrs"] >= UMBRAL_GRAVE:
            return "grave"
        if fila["iqrs"] >= UMBRAL_ATENCION:
            return "atención"
        return "normal"

    mia["bandera"] = mia.apply(bandera, axis=1)
    mia["sobre_prima"] = mia["siniestralidad_pct"] >= SINIESTRALIDAD_CRITICA

    columnas = grupos + ["prima_mdp", "siniestralidad_pct", "mercado_pct",
                         "dif", "iqr", "iqrs", "bandera", "sobre_prima"]
    return mia[columnas].sort_values("dif", ascending=False, ignore_index=True)


def diagnostico_frecuencia_severidad(df, institucion, por=("DESC_RAMO",),
                                     periodo="ANIO", tolerancia=TOLERANCIA):
    """
    Separa, ramo por ramo, si el costo del riesgo viene de frecuencia o severidad.

    Compara los dos factores de la institución contra los del mercado como
    razones (1.0 = igual al mercado) y clasifica:

        "frecuencia"  tiene más siniestros de lo normal, no más caros
        "severidad"   los siniestros son más caros, no más
        "ambos"       las dos cosas
        "ninguno"     ambos factores dentro de la tolerancia o por debajo

    `tolerancia` define qué tan lejos de 1.0 hay que estar para contar como
    diferencia; sin ella un ramo 3% arriba saldría diagnosticado.

    OJO: esto describe el COSTO DEL RIESGO, no la rentabilidad. Un ramo puede
    salir "ambos" y estar perfectamente bien si la prima lo refleja. Sura en
    Automóviles 2025 tiene costo técnico 1.47x el del mercado y prima por
    riesgo 1.44x: su siniestralidad queda en línea. Por eso se devuelve también
    `razon_siniestralidad`, que es la que dice si el sobrecosto está cobrado.

    La razón de primas puras (frecuencia x severidad) va en `razon_costo`.
    """
    grupos = _grupos(por, periodo)
    mias = filtrar(df, institucion=institucion)

    lado = frecuencia_severidad(mias, por=por, periodo=periodo)
    mercado = frecuencia_severidad(df, por=por, periodo=periodo)
    tabla = lado.merge(mercado, on=grupos, suffixes=("_inst", "_mercado"))

    # prima_mdp solo existe de un lado, así que el merge no le pone sufijo:
    # se renombra a mano para que quede claro de quién es.
    sin_inst = (siniestralidad(mias, por=por, periodo=periodo)
                [grupos + ["prima_mdp", "siniestralidad_pct"]]
                .rename(columns={"prima_mdp": "prima_mdp_inst"}))
    sin_mkt = siniestralidad(df, por=por, periodo=periodo)[grupos + ["siniestralidad_pct"]]
    tabla = tabla.merge(sin_inst.merge(sin_mkt, on=grupos, suffixes=("_inst", "_mercado")),
                        on=grupos)

    # Solo se dividen magnitudes positivas: un mercado con severidad negativa
    # (monto de siniestros negativo por reversas) no es una referencia válida.
    tabla["razon_frecuencia"] = _dividir(tabla["frecuencia_pct_inst"],
                                         tabla["frecuencia_pct_mercado"])
    tabla["razon_severidad"] = _dividir(tabla["severidad_pesos_inst"],
                                        tabla["severidad_pesos_mercado"])
    tabla["razon_costo"] = tabla["razon_frecuencia"] * tabla["razon_severidad"]
    tabla["razon_siniestralidad"] = _dividir(tabla["siniestralidad_pct_inst"],
                                             tabla["siniestralidad_pct_mercado"])

    alta_f = tabla["razon_frecuencia"] > 1 + tolerancia
    alta_s = tabla["razon_severidad"] > 1 + tolerancia
    tabla["diagnostico"] = np.select(
        [alta_f & alta_s, alta_f, alta_s],
        ["ambos", "frecuencia", "severidad"],
        default="ninguno",
    )
    # Sin referencia válida no hay diagnóstico que dar.
    tabla.loc[tabla[["razon_frecuencia", "razon_severidad"]].isna().any(axis=1),
              "diagnostico"] = "no comparable"

    # `sobrecosto_cobrado` responde la pregunta que sigue: el riesgo sale más
    # caro, ¿lo compensa la prima? Si la siniestralidad queda en línea o por
    # debajo del mercado, sí.
    tabla["sobrecosto_cobrado"] = tabla["razon_siniestralidad"] <= 1 + tolerancia

    # Prima cobrada por riesgo expuesto, contra la del mercado. Sale de la
    # identidad, no de un cálculo aparte:
    #     razón de siniestralidad = razón de costo / razón de prima
    tabla["razon_prima"] = _dividir(tabla["razon_costo"],
                                    tabla["razon_siniestralidad"])

    # ¿El desajuste viene del riesgo o de la tarifa? Las tres razones se
    # multiplican y dividen entre sí, así que restarlas no dice nada: 17x de
    # costo contra 3x de precio no se comparan en crudo. En logaritmos la
    # división se vuelve resta y los dos aportes quedan en la misma escala,
    # sumando exactamente el desajuste total.
    positivo = lambda c: np.log(tabla[c].where(tabla[c] > 0))
    tabla["aporte_costo"] = positivo("razon_costo")
    tabla["aporte_precio"] = -positivo("razon_prima")
    desajuste = positivo("razon_siniestralidad")

    tabla["causa_dominante"] = np.select(
        [tabla["aporte_costo"].isna() | tabla["aporte_precio"].isna(),
         desajuste.abs() <= np.log(1 + tolerancia),
         tabla["aporte_costo"].abs() > tabla["aporte_precio"].abs()],
        ["sin dato", "en línea", "costo"],
        default="precio",
    )

    columnas = grupos + ["prima_mdp_inst", "razon_frecuencia", "razon_severidad",
                         "razon_costo", "razon_prima", "razon_siniestralidad",
                         "aporte_costo", "aporte_precio", "diagnostico",
                         "sobrecosto_cobrado", "causa_dominante"]
    return tabla[columnas].sort_values("razon_costo", ascending=False, ignore_index=True)


def _titulares(tema, signo, tabla, columna, formato, n, ascendente=False):
    """Convierte el top-n de una tabla en filas de resumen, ya redactadas."""
    if tabla.empty:
        return []
    orden = tabla.nsmallest(n, columna) if ascendente else tabla.nlargest(n, columna)
    return [
        {"tema": tema, "signo": signo, "posicion": i,
         "DESC_RAMO": f["DESC_RAMO"], "valor": f[columna],
         "prima_mdp": f.get("prima_mdp", float("nan")),
         "detalle": formato(f)}
        for i, (_, f) in enumerate(orden.iterrows(), start=1)
    ]


def _ranking(tema, tabla, columna, texto_alto, texto_bajo, n):
    """
    Cabeza y cola de un orden, sin que se toquen.

    Con pocos ramos, el top-n y la cola-n son el MISMO ramo, y el resumen lo
    presenta como fortaleza y como problema a la vez. No es un caso raro: 60 de
    las 95 aseguradoras de 2025 operan en tres ramos o menos.

    Con un solo ramo no hay orden que hacer —no es el mejor ni el peor, es el
    único—, así que sale como dato informativo y no como veredicto.
    """
    if len(tabla) <= 1:
        return _titulares(tema, "informativo", tabla, columna, texto_alto, 1)
    corte = min(n, len(tabla) // 2)
    return (_titulares(tema, "favorable", tabla, columna, texto_alto, corte)
            + _titulares(tema, "desfavorable", tabla, columna, texto_bajo, corte,
                         ascendente=True))


def resumen(df, institucion, anio=None, n=3, volumen_min=VOLUMEN_MIN):
    """
    Titulares de una aseguradora: lo que hay que decir de ella en una página.

    Recorre las métricas del módulo y se queda con el top `n` de cada una, en
    los dos sentidos cuando tiene sentido (dónde gana y dónde pierde).

    Devuelve un DataFrame largo, una fila por titular, con `tema` y `signo`
    para filtrar. Es la forma reciclable: si solo quieres el crecimiento,
    `resumen(...).query("tema == 'crecimiento'")`; si quieres lo malo,
    filtra por `signo == "desfavorable"`. La columna `detalle` ya viene
    redactada para pegarse en un reporte.

    OJO CON LAS VENTANAS. Todo se mide sobre los meses que el año elegido
    tenga en la base. Si ese año está a medias —2026 llega a junio— las cifras
    son de medio año y la función avisa con un warning; los umbrales de
    volumen se escalan a esa misma ventana. El periodo queda anotado en
    attrs["meses"]. Los titulares de crecimiento además lo dicen en su texto,
    porque ahí la ventana la decide crecimiento_anual y puede no coincidir.

    Los ramos por debajo de `volumen_min` no producen titulares de
    siniestralidad ni de diagnóstico: son los que dan porcentajes salvajes
    sobre carteras diminutas y coparían el resumen.
    """
    anio = int(anio if anio is not None else df["ANIO"].max())
    mercado = filtrar(df, anio=anio)
    mias = filtrar(mercado, institucion=institucion)
    if mias.empty:
        raise ValueError(f"{institucion!r} no tiene datos en {anio}.")

    # El último año de la base suele estar a medias (llega a junio de 2026).
    # Todo lo que sigue se mide sobre esa ventana, así que la compuerta de
    # volumen —calibrada en primas anuales— hay que escalarla igual que en
    # crecimiento. Sin esto, medio año se juzga con la vara de un año entero.
    meses_anio = sorted(int(m) for m in mercado["MES"].unique())
    cobertura_anio = len(meses_anio) / 12
    corte = volumen_min * cobertura_anio
    if cobertura_anio < 1:
        warnings.warn(
            f"{anio} solo tiene {len(meses_anio)} meses en la base: las cifras "
            f"del resumen son de ese periodo, no del año completo.",
            stacklevel=2)

    filas = []
    part = filtrar(participacion_mercado(mercado), institucion=institucion)
    total = part["prima_mdp"].sum()

    filas += _titulares(
        "cartera", "informativo", part, "prima_mdp",
        lambda f: (f"{nombre_ramo(f.DESC_RAMO)}: {f.prima_mdp:,.0f} mdp"
                   f" ({100 * f.prima_mdp / total:.0f}% de su prima)"), n)

    con_volumen = part[part["prima_mdp"] >= corte]
    filas += _ranking(
        "participación", con_volumen, "participacion_pct",
        lambda f: f"{nombre_ramo(f.DESC_RAMO)}: {f.participacion_pct:.2f}% del ramo",
        lambda f: f"{nombre_ramo(f.DESC_RAMO)}: solo {f.participacion_pct:.2f}% del ramo",
        n)

    # --- crecimiento: ventana recortada, hay que decirlo ---
    cre = comparar_vs_mercado(df, institucion, crecimiento_anual)
    ventana = cre.attrs.get("meses")
    cobertura = len(list(ventana)) / 12 if ventana else 1.0
    cre = cre[cre["ANIO"] == anio].copy()
    cre["brecha"] = cre["crecimiento_pct_inst"] - cre["crecimiento_pct_mercado"]
    cre = cre[cre["prima_mdp_inst"] >= volumen_min * cobertura].dropna(subset=["brecha"])
    etiqueta_ventana = "ene-jun" if cobertura < 1 else "año completo"

    def texto_crecimiento(f):
        return (f"{nombre_ramo(f.DESC_RAMO)}: {f.crecimiento_pct_inst:+.0f}% contra "
                f"{f.crecimiento_pct_mercado:+.0f}% del mercado "
                f"({etiqueta_ventana})")

    # Aquí no hace falta partir el orden: crecer más que el mercado o menos es
    # un hecho con signo, no una posición relativa. Un ramo con brecha positiva
    # nunca puede ser también el "peor".
    filas += _titulares("crecimiento", "favorable", cre[cre["brecha"] > 0],
                        "brecha", texto_crecimiento, n)
    filas += _titulares("crecimiento", "desfavorable", cre[cre["brecha"] < 0],
                        "brecha", texto_crecimiento, n, ascendente=True)

    # --- siniestralidad: solo ramos evaluables ---
    al = alerta_siniestralidad(mercado, institucion, volumen_min=corte)
    evaluados = al[~al["bandera"].isin(("sin volumen", "no comparable"))].dropna(subset=["iqrs"])

    def texto_siniestralidad(f):
        aviso = "  [sobre 100%]" if f.sobre_prima else ""
        return (f"{nombre_ramo(f.DESC_RAMO)}: {f.siniestralidad_pct:.0f}% contra "
                f"{f.mercado_pct:.0f}% del mercado ({f.iqrs:+.1f} IQR){aviso}")

    # Desfavorable exige estar por ARRIBA de la mediana del ramo. Sin esto, una
    # aseguradora con todo en orden igual produciría tres "peores".
    filas += _titulares("siniestralidad", "desfavorable",
                        evaluados[evaluados["iqrs"] > 0], "iqrs",
                        texto_siniestralidad, n)
    # Un titular favorable tiene que serlo de verdad. Ordenar por iqrs y tomar
    # los tres más bajos siempre devuelve tres, aunque el mejor esté apenas en
    # la mediana de su ramo: Sura 2025 no baja de -0.2 IQR, y presentar eso
    # como fortaleza es inventarla. Medio IQR es el mínimo para contarlo.
    destacan = evaluados[evaluados["iqrs"] <= -0.5]
    filas += _titulares("siniestralidad", "favorable", destacan, "iqrs",
                        texto_siniestralidad, n, ascendente=True)

    # --- diagnóstico: de dónde viene el costo, solo donde no está cobrado ---
    diag = diagnostico_frecuencia_severidad(mercado, institucion)
    diag = diag[(~diag["sobrecosto_cobrado"])
                & diag["diagnostico"].ne("no comparable")
                & (diag["prima_mdp_inst"] >= corte)].rename(
        columns={"prima_mdp_inst": "prima_mdp"})
    def texto_diagnostico(f):
        # La causa dominante es lo accionable: dice si hay que suscribir mejor
        # o cobrar más, que son departamentos distintos.
        if f.causa_dominante == "precio":
            causa = f"domina el PRECIO: cobra {f.razon_prima:.2f}x el mercado"
        else:
            causa = f"domina el COSTO: el riesgo cuesta {f.razon_costo:.1f}x"
        return (f"{nombre_ramo(f.DESC_RAMO)}: {f.diagnostico} "
                f"(frecuencia {f.razon_frecuencia:.1f}x, "
                f"severidad {f.razon_severidad:.1f}x) — {causa}")

    filas += _titulares("diagnóstico", "desfavorable", diag,
                        "razon_siniestralidad", texto_diagnostico, n)

    salida = pd.DataFrame(filas, columns=["tema", "signo", "posicion", "DESC_RAMO",
                                          "valor", "prima_mdp", "detalle"])
    # Queda anotado sobre qué periodo se midió: sin esto, un resumen de medio
    # año es indistinguible de uno anual al leerlo.
    salida.attrs["anio"] = anio
    salida.attrs["meses"] = meses_anio
    return salida


def concentracion_cartera(df, por=("DESC_RAMO",), periodo="ANIO"):
    """
    Qué tan repartida está la prima de cada institución entre sus ramos.

    Contar ramos no basta: dice en cuántos opera, no cuánto pesa cada uno. Sura
    y AXA operan las dos en 13 ramos de 2025 y el conteo las iguala, pero Sura
    reparte su prima como si tuviera 6 y AXA como si tuviera 3.4. Quálitas
    aparece con 2 ramos siendo monoproducto: su segundo son 2 mdp de 73,474.

    Se mide con el índice de Herfindahl-Hirschman sobre la cartera propia:

        HHI = suma de s_i al cuadrado,   s_i = prima del ramo i / prima total

    Va de 1/n (todo repartido parejo entre n ramos) a 1 (todo en uno solo). Su
    inverso, 1/HHI, son los RAMOS EFECTIVOS: el número de ramos de igual tamaño
    que daría la misma concentración, y es la cifra que se lee sin explicar.

    `por` permite medir otra dimensión: con ("DESC_ENTIDADFEDERATIVA",) sale la
    concentración geográfica, que para primas sí es válida —a diferencia de la
    siniestralidad por entidad, que está rota porque la póliza se emite en un
    estado y el siniestro se registra en otro—.

    Las primas negativas (cancelaciones que superan lo emitido) se llevan a
    cero: una cuota negativa no es una porción de la cartera y al elevarla al
    cuadrado contaría como si fuera positiva.
    """
    llave = ([periodo] if periodo else []) + [INSTITUCION]

    prima = (df.groupby(llave + list(por))["PRIMA_EMI"].sum()
               .clip(lower=0).rename("prima").reset_index())
    total = prima.groupby(llave)["prima"].transform("sum")

    prima["cuota"] = _dividir(prima["prima"], total)
    tabla = prima.groupby(llave).agg(
        prima_mdp=("prima", "sum"),
        grupos=("prima", lambda s: int((s > 0).sum())),
        hhi=("cuota", lambda s: (s ** 2).sum()),
    ).reset_index()

    # Sin prima no hay cartera que repartir: el HHI queda indefinido, no en 0.
    tabla["hhi"] = tabla["hhi"].where(tabla["prima_mdp"] > 0)
    tabla["efectivos"] = _dividir(1, tabla["hhi"])

    # Cuánta de la prima entró de verdad al cálculo. groupby descarta los nulos
    # de la columna agrupadora sin avisar, y DESC_ENTIDADFEDERATIVA tiene
    # 11,341: Aseguradora Aserta no trae entidad en NINGUNA fila, así que su
    # concentración geográfica saldría de un subconjunto vacío. Con esta
    # columna, quien la use puede descartar los casos sin respaldo.
    completa = (df.groupby(llave)["PRIMA_EMI"].sum().clip(lower=0)
                  .rename("prima_total").reset_index())
    tabla = tabla.merge(completa, on=llave, how="left")
    tabla["cobertura"] = _dividir(tabla["prima_mdp"], tabla["prima_total"])

    tabla["prima_mdp"] /= MDP
    return tabla.drop(columns="prima_total").sort_values(
        "prima_mdp", ascending=False, ignore_index=True)
