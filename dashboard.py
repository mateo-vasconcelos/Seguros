"""
Dashboard de benchmarking sobre la base de Tendencias del Seguro (SIO - CNSF).

No calcula nada por su cuenta: todo sale de metricas.py y graficas.py, que son
las mismas funciones del notebook. Aquí solo se cablean a controles y se
acomodan en pantalla.

Se corre con:   streamlit run dashboard.py
"""

import warnings

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from graficas import (alerta_ramos, carrera_contra_mercado, dispersion_cartera,
                      mapa_frecuencia_severidad)
from metricas import (INSTITUCION, alerta_siniestralidad, comparar_vs_mercado, concentracion_cartera,
                      crecimiento_anual, diagnostico_frecuencia_severidad, filtrar,
                      participacion_mercado, resumen, siniestralidad)
from src.pipeline import RUTA_LIMPIA

st.set_page_config(page_title="Benchmarking de seguros", layout="wide")

SIN_COMPARAR = "— ninguna —"
LADO_A_LADO = "Lado a lado"
APILADAS = "Una sobre otra (más grandes)"

# El grueso del tema vive en .streamlit/config.toml. Aquí solo va lo que la
# configuración no alcanza: traer la tipografía y dar forma a las tarjetas.
ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;600;700&display=swap');

/* El sitio de referencia respira: menos margen superior, más aire entre bloques. */
[data-testid="stMain"] .block-container { padding-top: 2.6rem; max-width: 1500px; }

/* Los KPIs como tarjetas sobre el azul claro, con la esquina de 5px del sitio. */
[data-testid="stMetric"] {
    background: #fff4ee;                 /* lavado naranja muy claro */
    border: 1px solid #ffd9c7;
    border-left: 3px solid #ff5d22;      /* el filete de marca, como en el sitio */
    border-radius: .3rem;
    padding: .9rem 1.1rem;
    /* Altura común y rótulo pegado arriba: con seis tarjetas, algunos rótulos
       ocupan dos líneas y sin esto las cifras quedarían a distinta altura. */
    min-height: 6.1rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
[data-testid="stMetricValue"] { color: #221638; }
[data-testid="stMetricLabel"] p {
    font-size: .72rem; font-weight: 600; letter-spacing: .01em;
    text-transform: uppercase; color: #c2481a;
    /* Streamlit le pone nowrap al <p> del rótulo: con tarjetas angostas eso
       desborda en vez de saltar de línea. Se permite el salto, pero nunca a
       media palabra: "SINIESTRA / LIDAD" es peor que una tarjeta más ancha. */
    white-space: normal !important;
    overflow-wrap: normal;
    word-break: keep-all;
}

/* La fila de KPIs se reacomoda en dos renglones cuando no caben seis tarjetas.
   El :has() limita la regla a las filas que contienen métricas, para no tocar
   las columnas de las gráficas. */
[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) { flex-wrap: wrap; }
[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div {
    min-width: 170px;
}

/* Recuadro de ayuda al pie de una pestaña. */
.clave { background: #f1f8fb; border: 1px solid #e4ecf1; border-left: 3px solid #ff5d22;
         border-radius: .3rem; padding: 1rem 1.3rem; margin-top: 1.2rem; }
.clave h4 { margin: 0 0 .6rem; font-weight: 600; font-size: 1rem; color: #221638; }
.clave ol { margin: 0; padding-left: 1.2rem; }
.clave li { margin-bottom: .35rem; line-height: 1.5; }
.clave ul { margin: .3rem 0 .1rem; padding-left: 1.1rem; list-style: none; }
.clave ul li { color: #4a4a4a; font-size: .93rem; }
.clave ul li::before { content: "→"; color: #ff5d22; margin-right: .45rem; }

/* La pestaña activa en naranja, como el menú del sitio. */
[data-testid="stTabs"] [role="tablist"] { gap: 1.9rem; border-bottom: 1px solid #e4ecf1; }
[data-testid="stTabs"] [role="tab"] { font-size: 1rem; padding-bottom: .55rem; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #ff5d22; font-weight: 600; }

/* Título principal: el peso ligero es lo que más marca el parecido. */
[data-testid="stMain"] h1 { font-weight: 300; letter-spacing: -.02em; margin-bottom: .2rem; }

/* Barra lateral oscura: los rótulos de los controles necesitan aclararse.
   La regla se acota a stWidgetLabel: antes alcanzaba a TODO label del panel,
   incluidas las opciones del radio, que acababan con pinta de rótulo —en
   mayúsculas y apagadas— en vez de parecer algo que se puede elegir. */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #c9c2d8 !important; font-weight: 600;
    font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; }

/* Opciones del radio: la no elegida tiene que verse disponible, no apagada.
   Lleva marco propio y se enciende al pasar el cursor; la elegida se queda
   con el lavado naranja y el texto en blanco. */
[data-testid="stRadioOption"] {
    padding: .4rem .6rem; margin-bottom: .3rem; border-radius: .3rem;
    border: 1px solid rgba(255,255,255,.30);
    cursor: pointer; transition: background .15s, border-color .15s;
}
[data-testid="stRadioOption"] p { color: #d8d2e4; font-size: .92rem; }
[data-testid="stRadioOption"]:hover { background: rgba(255,93,34,.14);
    border-color: #ff5d22; }
[data-testid="stRadioOption"]:hover p { color: #ffffff; }
[data-testid="stRadioOption"][data-selected="true"] {
    background: rgba(255,93,34,.16); border-color: #ff5d22; }
[data-testid="stRadioOption"][data-selected="true"] p {
    color: #ffffff; font-weight: 600; }
[data-testid="stSidebar"] h1 { font-weight: 300; color: #ffffff; margin-bottom: .1rem; }

/* El naranja también vive aquí: filete superior, subrayado del título y
   borde de la nota final. Sobre el marino es el único color que resalta. */
[data-testid="stSidebar"] > div:first-child { border-top: 4px solid #ff5d22; }
.marca-linea { width: 46px; height: 3px; background: #ff5d22; border-radius: 2px;
               margin: .1rem 0 .9rem; }
.nota-lateral { border-left: 3px solid #ff5d22; padding: .1rem 0 .1rem .7rem;
                color: #c9c2d8; font-size: .86rem; line-height: 1.45; }
/* El control enfocado y el seleccionado se marcan en naranja. */
[data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
    border-color: #ff5d22 !important; box-shadow: 0 0 0 1px #ff5d22 !important; }
[data-testid="stSidebar"] [role="option"][aria-selected="true"] { color: #ff5d22 !important; }

/* Texto de entrada: es lo único que se lee antes de elegir, así que va
   un punto más grande que el cuerpo. */
.entrada { font-size: 1.18rem; line-height: 1.6; color: #4a4a4a; max-width: 62ch; }

/* Un filete naranja a la izquierda de cada rótulo del resumen. */
.rotulo { border-left: 3px solid #ff5d22; padding-left: .6rem; margin: 1.1rem 0 .4rem;
          font-weight: 600; letter-spacing: .03em; }
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)


@st.cache_data
def cargar():
    """
    Lee el parquet una sola vez.

    Streamlit vuelve a ejecutar el script entero en cada clic, así que sin
    caché se releerían 694 mil filas cada vez que muevas un selector. Las
    métricas en sí tardan centésimas y no vale la pena cachearlas.
    """
    return pd.read_parquet(RUTA_LIMPIA)


def pintar(ax):
    """Manda la figura a la página y la cierra: si no, matplotlib las acumula."""
    st.pyplot(ax.figure, width="stretch")
    plt.close(ax.figure)


def paneles(aseguradoras, disposicion):
    """
    Un contenedor por aseguradora, en columnas o apilados.

    Apilado cada gráfica ocupa el ancho completo, que es la diferencia entre
    poder leer las etiquetas de los ramos y no poder. Lado a lado se compara
    de un vistazo pero todo queda a la mitad de tamaño.
    """
    if disposicion == LADO_A_LADO and len(aseguradoras) > 1:
        contenedores = st.columns(len(aseguradoras))
    else:
        contenedores = [st.container() for _ in aseguradoras]
    if len(aseguradoras) > 1:
        for c, nombre in zip(contenedores, aseguradoras):
            c.markdown(f"##### {nombre}")
    return contenedores


def juntar(tablas, aseguradoras, columna, llave="DESC_RAMO"):
    """
    Pone la misma columna de varias aseguradoras lado a lado, por ramo.

    Es el complemento honesto de las gráficas: cada panel tiene su propia
    escala, así que comparar dos puntos entre paneles engaña. Los números sí
    se comparan directo.
    """
    juntas = None
    for tabla, nombre in zip(tablas, aseguradoras):
        trozo = tabla[[llave, columna]].rename(columns={columna: nombre})
        juntas = trozo if juntas is None else juntas.merge(trozo, on=llave, how="outer")
    return juntas.set_index(llave).round(2)


# ------------------------------------------------------------------ controles
df = cargar()
anios = sorted(df["ANIO"].unique())
meses_por_anio = df.groupby("ANIO")["MES"].nunique()
completos = [a for a in anios if meses_por_anio[a] == 12]

with st.sidebar:
    st.title("Benchmarking")
    st.markdown("<div class='marca-linea'></div>", unsafe_allow_html=True)
    st.caption("Tendencias del Seguro · SIO – CNSF")

    anio = st.selectbox("Año", anios,
                        index=anios.index(max(completos)) if completos else len(anios) - 1)

    nombres = sorted(filtrar(df, anio=anio)["NOMBRE_CORTO"].unique())
    # Sin valor por defecto: que la elección sea del usuario y no una que
    # arrastre sin darse cuenta.
    principal = st.selectbox("Aseguradora", nombres, index=None,
                             placeholder="Elige una aseguradora")
    contra = SIN_COMPARAR
    disposicion = LADO_A_LADO
    if principal:
        contra = st.selectbox("Comparar contra",
                              [SIN_COMPARAR] + [n for n in nombres if n != principal])
        if contra != SIN_COMPARAR:
            disposicion = st.radio("Disposición", [LADO_A_LADO, APILADAS],
                                   horizontal=False)

    st.divider()
    st.markdown("<div class='nota-lateral'>El mercado siempre es el total del "
                "ramo, incluidas las aseguradoras seleccionadas.</div>",
                unsafe_allow_html=True)

mercado = filtrar(df, anio=anio)

# Pantalla de entrada: sin aseguradora elegida no hay nada que comparar, pero
# sí vale la pena decir contra qué se va a comparar.
if principal is None:
    st.title("Benchmarking de aseguradoras")
    st.markdown("<div class='entrada'>Elige una aseguradora en el panel de la "
                "izquierda para ver su posición contra el mercado. Puedes añadir "
                "una segunda para comparar las dos.</div>",
                unsafe_allow_html=True)
    st.divider()
    st.markdown(f"##### El mercado en {anio}")
    a, b, c = st.columns(3)
    a.metric("Prima emitida del sector (mdp)", f"{mercado['PRIMA_EMI'].sum() / 1e6:,.0f}")
    b.metric("Aseguradoras", f"{mercado['NOMBRE_CORTO'].nunique()}")
    c.metric("Ramos", f"{mercado['DESC_RAMO'].nunique()}")
    st.stop()

aseguradoras = [principal] + ([contra] if contra != SIN_COMPARAR else [])

# El último año de la base suele estar a medias y eso cambia cómo se leen
# todas las cifras, así que se avisa antes de mostrar nada.
meses = int(meses_por_anio[anio])
if meses < 12:
    st.warning(f"**{anio} solo tiene {meses} meses en la base.** Todas las cifras son de "
               f"ese periodo, no de un año completo, y los umbrales de volumen se ajustan "
               f"en la misma proporción.")

st.title(" vs ".join(aseguradoras) if len(aseguradoras) > 1 else principal)

# ---------------------------------------------------------------------- KPIs
part_mercado = participacion_mercado(mercado)
total_mercado = participacion_mercado(mercado, por=())
conc_mercado = concentracion_cartera(mercado)
geo_mercado = concentracion_cartera(mercado, por=("DESC_ENTIDADFEDERATIVA",))
COBERTURA_MIN = 0.9   # por debajo, el dato geográfico no tiene respaldo

for nombre in aseguradoras:
    perfil = filtrar(part_mercado, institucion=nombre)
    cuota = filtrar(total_mercado, institucion=nombre)["participacion_pct"]
    sin_global = siniestralidad(filtrar(mercado, institucion=nombre), por=())
    conc = conc_mercado[conc_mercado[INSTITUCION] == nombre]
    geo = geo_mercado[geo_mercado[INSTITUCION] == nombre]

    # La concentración geográfica solo vale si casi toda la prima trae entidad.
    # Hay aseguradoras que no la reportan nunca —Aserta, en el 100% de sus
    # filas— y el groupby las deja fuera sin avisar.
    geo_fiable = len(geo) and geo["cobertura"].iloc[0] >= COBERTURA_MIN

    if len(aseguradoras) > 1:
        st.markdown(f"**{nombre}**")
    a, b, c, d, e, f = st.columns(6)
    a.metric("Prima emitida (mdp)", f"{perfil['prima_mdp'].sum():,.0f}")
    b.metric("Ramos", f"{len(perfil)}", help="Ramos donde emite prima.")
    c.metric("Cuota de mercado",
             f"{cuota.iloc[0]:.2f}%" if len(cuota) else "—")
    d.metric("Siniestralidad",
             f"{sin_global['siniestralidad_pct'].iloc[0]:.1f}%" if len(sin_global) else "—",
             help="De toda la compañía junta: siniestros totales entre primas "
                  "totales, no el promedio de los ramos.")
    e.metric("Ramos efectivos",
             f"{conc['efectivos'].iloc[0]:.1f}" if len(conc) else "—",
             help="Cuántos ramos de igual tamaño darían la misma concentración "
                  "que su cartera real. Siempre es menor o igual al número de "
                  "ramos; la distancia entre los dos es lo concentrada que está.")
    f.metric("Estados efectivos",
             f"{geo['efectivos'].iloc[0]:.1f}" if geo_fiable else "—",
             help="El mismo índice, aplicado a los 32 estados en vez de a los "
                  "ramos. Sale en blanco cuando la aseguradora no reporta "
                  "entidad en al menos el 90% de su prima."
                  + (f"  Cobertura: {geo['cobertura'].iloc[0]:.0%}."
                     if len(geo) else ""))

with st.expander("¿Qué son los *ramos efectivos*?"):
    izq, der = st.columns([3, 2])
    with izq:
        st.markdown("""
Contar ramos dice en **cuántos** opera una aseguradora, no **cuánto pesa** cada
uno. Dos aseguradoras con 13 ramos pueden estar muy diversificadas o depender
casi por completo de uno.

Se mide con el **índice de Herfindahl-Hirschman (HHI)** sobre la cartera
propia: la suma de los cuadrados de las cuotas internas.
""")
        st.latex(r"HHI=\sum_i s_i^{\,2}\qquad "
                 r"s_i=\frac{\text{prima del ramo } i}{\text{prima total}}")
        st.markdown("""
Va de **1/n** (todo repartido parejo entre n ramos) a **1** (todo en uno solo).
Los *ramos efectivos* son su inverso, **1/HHI**: cuántos ramos de igual tamaño
darían esa misma concentración.

El mismo índice que ramos efectivos, aplicado a los **32 estados** da los *estados efectivos*, y las
dos lecturas no van juntas: Quálitas es la más concentrada por ramo (1.0) y la
más repartida por geografía (15.5). Vender un solo producto en todo el país es
un perfil de riesgo distinto al de vender muchos productos en pocos estados.

Solo sirve para primas. La siniestralidad por entidad está rota, porque la
póliza se emite en un estado y el siniestro se registra donde ocurre.
""")
    with der:
        st.markdown("**Cómo se lee**")
        st.dataframe(
            pd.DataFrame({
                "Cartera": ["Todo en un ramo", "Mitad y mitad",
                            "4 ramos iguales", "70% en uno, 30% repartido"],
                "HHI": [1.00, 0.50, 0.25, 0.52],
                "Efectivos": [1.0, 2.0, 4.0, 1.9],
            }), hide_index=True, width="stretch")
        st.caption("Importa porque condiciona el resto: la siniestralidad "
                   "global de una monoproducto *es* la de su único ramo, "
                   "mientras que la de una diversificada es una mezcla.")

st.divider()

# --------------------------------------------------------------------- pestañas
tabs = st.tabs(["Resumen", "Participación", "Siniestralidad",
                "Frecuencia y severidad", "Crecimiento"])

# --- Resumen --------------------------------------------------------------
with tabs[0]:
    st.caption("Top 3 de cada métrica, en los dos sentidos. Si una sección "
               "favorable no aparece, es que ningún ramo destaca lo suficiente.")
    for col, nombre in zip(paneles(aseguradoras, disposicion), aseguradoras):
        with col:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # el aviso del año parcial ya se dio arriba
                titulares = resumen(df, nombre, anio=anio, n=3)
            for (tema, signo), grupo in titulares.groupby(["tema", "signo"], sort=False):
                # El signo va en palabra además de color: un filete de color no
                # se lee si el lector no distingue rojo de verde.
                color = {"favorable": "#0ca30c", "desfavorable": "#d03b3b"}.get(signo, "#6b6b84")
                etiqueta = {"favorable": "favorable", "desfavorable": "a revisar"}.get(signo, "")
                st.markdown(
                    f"<div class='rotulo' style='border-color:{color}'>{tema.upper()}"
                    f"<span style='color:{color};font-weight:400;font-size:.82rem'>"
                    f"  {etiqueta}</span></div>", unsafe_allow_html=True)
                for linea in grupo["detalle"]:
                    st.markdown(f"<div style='margin:0 0 4px 18px'>· {linea}</div>",
                                unsafe_allow_html=True)
            faltan = {"siniestralidad", "participación", "crecimiento"} - set(
                titulares.query("signo == 'favorable'")["tema"])
            if faltan:
                st.caption(f"Sin titulares favorables de: {', '.join(sorted(faltan))}")
            st.download_button("Descargar CSV", titulares.to_csv(index=False),
                               f"resumen_{nombre}_{anio}.csv", key=f"csv_{nombre}")

# --- Participación --------------------------------------------------------
with tabs[1]:
    st.caption("Tamaño de cartera contra peso en el ramo. Los ejes pasan a "
               "escala logarítmica cuando los valores abarcan más de un orden "
               "de magnitud, que es lo normal al comparar dos aseguradoras.")
    perfiles = [filtrar(part_mercado, institucion=n) for n in aseguradoras]
    # Una sola gráfica con las dos aseguradoras y leyenda de color: en dos
    # paneles cada escala es distinta y dos puntos en la misma posición son
    # cifras diferentes, que es justo lo que uno cree estar comparando.
    pintar(dispersion_cartera(dict(zip(aseguradoras, perfiles)),
                              " vs ".join(aseguradoras) + f" — {anio}"))
    if len(aseguradoras) > 1:
        st.markdown("**Participación por ramo (%)**")
        st.dataframe(juntar(perfiles, aseguradoras, "participacion_pct"),
                     width="stretch")

# --- Siniestralidad -------------------------------------------------------
with tabs[2]:
    st.caption("La distancia se mide en rangos intercuartiles del propio ramo, "
               "no en puntos porcentuales: la dispersión va de 0.8 puntos en "
               "Terremoto a 71 en Incendio.")
    alertas = [alerta_siniestralidad(mercado, n) for n in aseguradoras]
    for col, alerta, nombre in zip(paneles(aseguradoras, disposicion), alertas, aseguradoras):
        with col:
            pintar(alerta_ramos(alerta, f"{nombre} {anio}"))
    st.markdown("**Detalle**")
    for alerta, nombre in zip(alertas, aseguradoras):
        with st.expander(f"{nombre} — tabla completa"):
            st.dataframe(alerta.round(2), width="stretch", hide_index=True)

# --- Frecuencia y severidad -----------------------------------------------
with tabs[3]:
    st.caption("El cuadrante es el diagnóstico. El color dice si el sobrecosto "
               "está cobrado; `causa_dominante`, si el problema es el riesgo o la tarifa.")
    diags = [diagnostico_frecuencia_severidad(mercado, n) for n in aseguradoras]
    for col, diag, nombre in zip(paneles(aseguradoras, disposicion), diags, aseguradoras):
        with col:
            pintar(mapa_frecuencia_severidad(diag, f"{nombre} {anio}"))
    st.markdown("**Detalle**")
    for diag, nombre in zip(diags, aseguradoras):
        with st.expander(f"{nombre} — tabla completa"):
            st.dataframe(
                diag[["DESC_RAMO", "prima_mdp_inst", "razon_frecuencia", "razon_severidad",
                      "razon_costo", "razon_prima", "diagnostico", "causa_dominante",
                      "sobrecosto_cobrado"]].round(2),
                width="stretch", hide_index=True)

    st.markdown("""
<div class="clave">
  <h4>Clave para leer la gráfica</h4>
  <ol>
    <li><b>¿Rojo o gris?</b> → ¿hay problema de rentabilidad, sí o no?</li>
    <li><b>Si es rojo, ¿dónde cayó?</b> → ¿el problema es el riesgo o el precio?
      <ul>
        <li>Fuera de las bandas → el riesgo es más caro; ataca frecuencia o
            severidad según el cuadrante</li>
        <li>Dentro de la banda → el riesgo es normal; ataca la tarifa</li>
      </ul>
    </li>
    <li><b>¿Qué tan grande es el punto?</b> → cuánto dinero está en juego</li>
  </ol>
</div>
""", unsafe_allow_html=True)

# --- Crecimiento ----------------------------------------------------------
with tabs[4]:
    st.caption("Compara periodos equivalentes contra el año anterior. Mientras "
               "el último año de la base esté incompleto, la ventana es ene–jun.")
    creces = []
    for nombre in aseguradoras:
        c = comparar_vs_mercado(df, nombre, crecimiento_anual)
        atributos = c.attrs
        c = c[c["ANIO"] == anio]
        c.attrs.update(atributos)       # el filtrado por máscara pierde attrs
        creces.append(c)

    if all(c.empty for c in creces):
        st.info(f"No hay año previo con el que comparar {anio}.")
    else:
        for col, c, nombre in zip(paneles(aseguradoras, disposicion), creces, aseguradoras):
            with col:
                if c.empty:
                    st.info("Sin datos comparables.")
                else:
                    pintar(carrera_contra_mercado(c, f"{nombre} {anio}"))
        if len(aseguradoras) > 1:
            st.markdown("**Crecimiento contra el año anterior (%)**")
            st.dataframe(juntar(creces, aseguradoras, "crecimiento_pct_inst"),
                         width="stretch")
