"""
Gráficas del benchmarking.

Reciben un DataFrame ya calculado por metricas.py y devuelven un eje de
matplotlib. No calculan indicadores ni filtran: eso ya pasó antes.

La paleta es fija y está pensada para fondo claro. Los colores de serie salen
de una escala validada para daltonismo; el texto siempre va en tinta, nunca
en el color de la serie.
"""

import math
import warnings

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter

# --- paleta -----------------------------------------------------------------
# Tomada de reporteregulatorio.mx para que las gráficas y el dashboard se lean
# como una sola cosa. El naranja de marca (#ff5d22) NO se usa aquí a propósito:
# queda reservado para los controles de la interfaz. Si además pintara datos,
# el lector no sabría si un punto naranja es una alerta o solo el color de la
# casa. Los datos van en el marino de marca, que sobre este fondo da 14:1 de
# contraste —mejor que el azul que traían antes—.
SUPERFICIE = "#fefcf8"   # blanco cálido del sitio
SERIE = "#221638"        # marino de marca: la serie de datos
TINTA = "#212529"        # títulos
SECUNDARIA = "#4a4a4a"   # etiquetas de datos y de ejes
MUTED = "#6b6b84"        # marcas de eje, anotaciones auxiliares
RETICULA = "#e4ecf1"
EJE = "#c8d5de"

# Paleta de estado, reservada: nunca se usa para distinguir series. Va siempre
# acompañada de la palabra ("atención", "grave"), nunca sola: sobre fondo claro
# estos tonos quedan por debajo de 3:1 de contraste, y el texto es la garantía
# de que la señal se lee aunque el color no se distinga.
ESTADO = {
    "grave": "#d03b3b",      # critical
    "atención": "#ec835a",   # serious
    "normal": MUTED,         # gris de discreción: evaluado y sin novedad
}
NO_EVALUADO = ("sin volumen", "no comparable")

# Verde de estado (good), para el lado positivo de una comparación.
BUENO = "#0ca30c"

# Colores para comparar aseguradoras dentro de UNA gráfica. Son los dos de la
# marca y se distinguen sobre todo por luminosidad (muy oscuro contra claro y
# saturado), no por tono: así siguen siendo distinguibles con cualquier tipo de
# daltonismo. Aun así nunca van solos — hay leyenda y etiquetas directas.
SERIES = ["#221638", "#ff5d22"]

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]


def _nombre_ventana(meses):
    """'ene–jun' para un tramo continuo; 'el año completo' si son los doce."""
    if not meses:
        return "el año completo"
    m = sorted(int(v) for v in meses)
    if len(m) == 12:
        return "el año completo"
    if m == list(range(m[0], m[-1] + 1)):
        return f"{MESES_CORTOS[m[0] - 1]}–{MESES_CORTOS[m[-1] - 1]}"
    return ", ".join(MESES_CORTOS[v - 1] for v in m)

# Nombres de ramo abreviados para que quepan como etiqueta en la gráfica.
# Solo afecta a lo que se dibuja; los datos conservan el nombre completo.
CORTOS = {
    "Accidentes Personales (incluye Ind, Gpo y Col)": "Accidentes Personales",
    "Gastos Médicos (incluye Ind, Gpo y Col)": "Gastos Médicos",
    "Fenómenos Hidrometeorológicos": "F. Hidrometeorológicos",
    "Transportes de Mercancías": "Transportes",
    "Diversos Ramos Técnicos": "Div. Ramos Técnicos",
    "Diversos Misceláneos": "Div. Misceláneos",
    "Cascos Embarcaciones": "Cascos Embarc.",
}


# Nombre legible de cada columna para los ejes. Las métricas comparadas traen
# sufijo (_inst, _mercado, _dif), que se traduce aparte para no repetir filas.
ETIQUETAS_EJE = {
    "prima_mdp": "Prima emitida (mdp)",
    "mercado_mdp": "Prima total del mercado (mdp)",
    "monto_mdp": "Monto de siniestros (mdp)",
    "participacion_pct": "Participación de mercado (%)",
    "siniestralidad_pct": "Siniestralidad (%)",
    "frecuencia_pct": "Frecuencia (siniestros por cada 100 riesgos)",
    "severidad_pesos": "Severidad (pesos por siniestro)",
    "crecimiento_pct": "Crecimiento contra el año anterior (%)",
    "expuestos": "Riesgos expuestos (promedio del periodo)",
    "siniestros": "Número de siniestros",
}
SUFIJOS_EJE = {"_inst": " — institución", "_mercado": " — mercado",
               "_dif": " — diferencia (puntos)"}


def _nombre_eje(columna):
    """Traduce el nombre de columna a algo legible, respetando los sufijos."""
    for sufijo, cola in SUFIJOS_EJE.items():
        if columna.endswith(sufijo):
            base = columna[: -len(sufijo)]
            return ETIQUETAS_EJE.get(base, base) + cola
    return ETIQUETAS_EJE.get(columna, columna)


def _vacia(ax, mensaje):
    """Deja el eje limpio con un aviso, en vez de reventar al fijar límites."""
    ax.set_axis_off()
    ax.text(0.5, 0.5, mensaje, ha="center", va="center", fontsize=10,
            color=MUTED, style="italic", transform=ax.transAxes)
    ax.figure.tight_layout()
    return ax


def _ticks_log(lo, hi):
    """Marcas 1-2-5 por década dentro del rango, para un eje logarítmico."""
    decadas = range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1)
    candidatos = [m * 10 ** e for e in decadas for m in (1, 2, 5)]
    return [t for t in candidatos if lo <= t <= hi]


def _colocar_etiquetas(ax, puntos, textos, fontsize=8.5, reservado=(), radios=None,
                       colores=None):
    """
    Escribe una etiqueta por punto, buscando un hueco libre.

    Prueba cuatro posiciones (derecha, izquierda, arriba, abajo) y se queda con
    la primera que no choque ni con otra etiqueta ni con un punto ya dibujado.
    Sin esto, dos ramos con participación parecida se pisan las etiquetas: es
    el defecto típico de un scatter con nombres, y aquí pasa de verdad entre
    Incendio y Diversos Ramos Técnicos.

    Las etiquetas llevan fondo del color de la superficie para que las líneas
    de mediana y la retícula no las crucen.
    """
    fig = ax.figure
    # draw() deja la figura con un renderer utilizable; a partir de ahí
    # get_window_extent() sin argumento funciona en cualquier backend.
    # Pedirlo con fig.canvas.get_renderer() rompía en producción: ese método
    # solo existe en el canvas de Agg, y la nube resuelve otro backend.
    fig.canvas.draw()

    # Los propios puntos ocupan lugar: una etiqueta no debe caer encima de uno.
    if radios is None:
        radios = [7] * len(puntos)
    if colores is None:
        colores = [SECUNDARIA] * len(puntos)
    ocupadas = [
        (x - r, y - r, x + r, y + r)
        for (x, y), r in zip((ax.transData.transform(p) for p in puntos), radios)
    ]
    ocupadas += list(reservado)   # p.ej. la caja con el coeficiente

    def choca(caja):
        return any(
            not (caja[2] < o[0] or caja[0] > o[2] or caja[3] < o[1] or caja[1] > o[3])
            for o in ocupadas
        )

    # De mayor a menor: los ramos grandes son los que más importa leer, así que
    # eligen lugar primero y los chicos se acomodan alrededor.
    for i in sorted(range(len(puntos)), key=lambda i: -puntos[i][0]):
        colocada = False
        # Anillos de distancia creciente. Con un solo anillo, dos puntos casi
        # superpuestos se quedan sin hueco y acaban con las etiquetas encimadas;
        # alejando la segunda un poco más, las dos caben.
        for anillo in (1.0, 1.9, 2.9):
            # El texto arranca fuera del punto, no a una distancia fija: con
            # burbujas de tamaño variable, 9 px caen dentro de las más grandes.
            sep = (radios[i] + 4) * anillo
            diag = sep * 0.72
            posiciones = [(sep, 0, "left", "center"), (-sep, 0, "right", "center"),
                          (0, sep + 4, "center", "bottom"), (0, -sep - 4, "center", "top"),
                          (diag, diag, "left", "bottom"), (diag, -diag, "left", "top"),
                          (-diag, diag, "right", "bottom"), (-diag, -diag, "right", "top")]
            for dx, dy, ha, va in posiciones:
                etiqueta = ax.annotate(
                    textos[i], puntos[i], textcoords="offset points", xytext=(dx, dy),
                    ha=ha, va=va, fontsize=fontsize, color=colores[i], zorder=4,
                    bbox=dict(fc=SUPERFICIE, ec="none", pad=1.2),
                )
                fig.canvas.draw()
                bb = etiqueta.get_window_extent()
                caja = (bb.x0 - 2, bb.y0 - 2, bb.x1 + 2, bb.y1 + 2)
                if choca(caja):
                    etiqueta.remove()
                    continue
                # Lejos del punto, el texto ya no se asocia solo: hace falta guía.
                if anillo > 1.0:
                    etiqueta.set_arrowprops = None
                    ax.annotate("", puntos[i], textcoords="offset points",
                                xytext=(dx * 0.92, dy * 0.92), zorder=2,
                                arrowprops=dict(arrowstyle="-", color=EJE,
                                                lw=0.8, shrinkA=0, shrinkB=radios[i]))
                ocupadas.append(caja)
                colocada = True
                break
            if colocada:
                break
        if not colocada:
            # Ningún hueco libre: se dibuja a la derecha y se acepta el traslape.
            ax.annotate(textos[i], puntos[i], textcoords="offset points",
                        xytext=(radios[i] + 4, 0), ha="left", va="center",
                        fontsize=fontsize, color=colores[i], zorder=4,
                        bbox=dict(fc=SUPERFICIE, ec="none", pad=1.2))


def dispersion_cartera(perfiles, titulo="", ax=None, etiquetar=6):
    """
    Prima emitida contra participación de mercado, un punto por ramo.

    `perfiles` es la salida de participacion_mercado() ya filtrada a una
    institución, o un diccionario {nombre: perfil} para comparar varias en la
    MISMA gráfica. Necesita las columnas DESC_RAMO, prima_mdp y
    participacion_pct.

    Comparar dentro de una sola gráfica y no en dos paneles es lo que permite
    leer la diferencia: con dos paneles cada uno calcula su propia escala, y
    dos puntos en la misma posición visual son cifras distintas.

    Por qué dispersión y no barras: son dos medidas de escalas muy distintas
    (mdp contra %), y ponerlas como barras y línea sobre dos ejes verticales
    inventaría una correlación que no está en los datos. Aquí cada medida tiene
    su propio eje posicional y la relación entre ambas se lee sola.

    El eje X va en escala logarítmica porque las primas abarcan dos órdenes de
    magnitud: en escala lineal, los ramos chicos se apelmazan contra el cero.

    Las líneas punteadas son las medianas y parten la gráfica en cuadrantes:
    abajo a la derecha están los ramos donde hay mucha prima pero poco peso
    relativo, que es el diagnóstico más accionable. Solo aparecen con una
    aseguradora: la mediana parte SU cartera, y mezclar dos carteras daría una
    línea que no describe a ninguna de las dos.

    Con varias aseguradoras se etiquetan los `etiquetar` ramos más grandes de
    cada una; poner nombre a todos vuelve la gráfica ilegible.
    """
    if not isinstance(perfiles, dict):
        perfiles = {None: perfiles}
    comparando = len(perfiles) > 1

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 6.5), dpi=130)

    fig = ax.figure
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    # Una prima negativa o cero no cabe en un eje logarítmico. Pasa de verdad:
    # hay 41 pares institución x ramo así en 2022, por cancelaciones que superan
    # lo emitido. Se excluyen y se dice cuántos, en vez de que matplotlib
    # ignore el set_xlim en silencio y deje la escala mal.
    fuera = sum(int((d["prima_mdp"] <= 0).sum()) for d in perfiles.values())
    perfiles = {k: d[d["prima_mdp"] > 0] for k, d in perfiles.items()}
    perfiles = {k: d for k, d in perfiles.items() if not d.empty}
    if not perfiles:
        return _vacia(ax, "Sin ramos con prima positiva en este periodo")

    todos_x = [v for d in perfiles.values() for v in d["prima_mdp"]]
    todos_y = [v for d in perfiles.values() for v in d["participacion_pct"]]

    ax.set_xscale("log")
    ax.set_xlim(min(todos_x) * 0.55, max(todos_x) * 2.4)

    # El eje Y pasa a logarítmico cuando la participación abarca más de un
    # orden de magnitud. Comparando Sura (0.27%) contra Quálitas (33%) en
    # escala lineal, los trece ramos de Sura se apelmazan en el 8% inferior y
    # no se distingue ninguno. Es el mismo argumento que ya justificaba el
    # eje X, solo que con una aseguradora sola casi nunca se dispara.
    y_log = min(todos_y) > 0 and max(todos_y) / min(todos_y) > 15
    if y_log:
        ax.set_yscale("log")
        ax.set_ylim(min(todos_y) * 0.6, max(todos_y) * 1.7)
        ax.yaxis.set_major_locator(FixedLocator(_ticks_log(*ax.get_ylim())))
        ax.yaxis.set_minor_locator(FixedLocator([]))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    else:
        ax.set_ylim(0, max(todos_y) * 1.18)

    if not comparando:
        # Los cuadrantes describen el reparto interno de UNA cartera.
        unico = next(iter(perfiles.values()))
        x, y = unico["prima_mdp"], unico["participacion_pct"]
        if len(unico) >= 5 and not y_log:
            ax.axvline(x.median(), color=EJE, lw=1, ls=(0, (4, 3)), zorder=1)
            ax.axhline(y.median(), color=EJE, lw=1, ls=(0, (4, 3)), zorder=1)
            ax.annotate("mediana", (x.median(), ax.get_ylim()[1]),
                        textcoords="offset points", xytext=(4, -11), fontsize=7.5,
                        color=MUTED, style="italic")
            ax.annotate("mediana", (ax.get_xlim()[1], y.median()),
                        textcoords="offset points", xytext=(-4, 4), ha="right",
                        fontsize=7.5, color=MUTED, style="italic")

    puntos, textos, colores = [], [], []
    for i, (nombre, perfil) in enumerate(perfiles.items()):
        color = SERIES[i % len(SERIES)]
        # El borde del color de la superficie separa los puntos que se traslapan.
        ax.scatter(perfil["prima_mdp"], perfil["participacion_pct"], s=110,
                   color=color, edgecolor=SUPERFICIE, linewidth=2, zorder=3,
                   label=nombre)
        visibles = (perfil.nlargest(etiquetar, "prima_mdp") if comparando else perfil)
        puntos += list(zip(visibles["prima_mdp"], visibles["participacion_pct"]))
        textos += [CORTOS.get(r, r) for r in visibles["DESC_RAMO"]]
        colores += [color] * len(visibles)

    # La leyenda se dibuja ANTES y se le reserva el espacio: si se pusiera al
    # final, caería encima de etiquetas ya colocadas.
    reservado = []
    if comparando:
        leyenda = ax.legend(loc="best", frameon=True, fontsize=9,
                            framealpha=1, edgecolor=RETICULA, borderpad=0.7)
        leyenda.get_frame().set_facecolor(SUPERFICIE)
        for t in leyenda.get_texts():
            t.set_color(SECUNDARIA)
        fig.canvas.draw()
        bb = leyenda.get_window_extent()
        reservado = [(bb.x0 - 4, bb.y0 - 4, bb.x1 + 4, bb.y1 + 4)]

    # Una sola llamada con todo: si se llamara por serie, las etiquetas de la
    # segunda no verían las de la primera y se encimarían.
    _colocar_etiquetas(ax, puntos, textos, colores=colores, reservado=reservado)

    # Ticks en cifras legibles: en escala log, matplotlib pondría 10^2 y 10^3.
    # Se generan a partir del rango real, no de una lista fija: las primas van
    # de 2 mdp a 176,000 mdp según la aseguradora, y una lista fija dejaría al
    # eje sin marcas en los extremos.
    ax.xaxis.set_major_locator(FixedLocator(_ticks_log(*ax.get_xlim())))
    ax.xaxis.set_minor_locator(FixedLocator([]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))

    ax.set_xlabel("Prima emitida en el año (mdp, escala logarítmica)",
                  fontsize=9, color=SECUNDARIA)
    ax.set_ylabel("Participación de mercado del ramo (%)", fontsize=9, color=SECUNDARIA)
    if titulo:
        ax.set_title(titulo, fontsize=12.5, color=TINTA, pad=24, loc="left")

    nota = ("Cada punto es un ramo. Arriba = pesa más en ese mercado; "
            "a la derecha = más prima.")
    if comparando:
        nota += f"  Se etiquetan los {etiquetar} ramos mayores de cada una."
    if fuera:
        nota += f"  ({fuera} ramo(s) con prima negativa quedan fuera.)"
    ax.annotate(nota, (0, 1), xycoords="axes fraction", xytext=(0, 10),
                textcoords="offset points", fontsize=8.5, color=SECUNDARIA)

    ax.grid(True, axis="y", color=RETICULA, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EJE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    fig.tight_layout()
    return ax


def dispersion(datos, x, y, etiqueta=None, titulo="", nota=None,
               log_x=False, log_y=False, etiquetar=15, tendencia=False, ax=None):
    """
    Dispersión de dos métricas cualesquiera, con su correlación de rangos.

    `datos` es un DataFrame que ya trae ambas columnas; `x` e `y` son sus
    nombres y `etiqueta` la columna con el nombre de cada punto.

    Los puntos pueden ser instituciones (un ramo, muchas aseguradoras) o ramos
    (una aseguradora, muchos ramos), según lo que hayas agregado antes. La
    función no lo sabe ni le importa.

    CUIDADO CON LO QUE CORRELACIONAS. Si las dos métricas comparten un término,
    la correlación aparece sola y no significa nada: es aritmética, no un
    hallazgo. La función avisa en los casos que ya conocemos (ver
    PARES_ESPURIOS), pero la lista no puede ser exhaustiva — piénsalo antes.

    Con muchos puntos solo se etiquetan los `etiquetar` más extremos: poner
    nombre a los 34 competidores de Automóviles no deja leer nada.

    `tendencia=False` por defecto y a propósito. Una recta sobre una nube sin
    relación (rho cercano a cero) le sugiere al ojo un patrón que los números
    no respaldan. Actívala solo cuando la correlación ya justifique dibujarla.
    """
    aviso = PARES_ESPURIOS.get(frozenset((x, y)))
    if aviso:
        warnings.warn(f"'{x}' y '{y}' {aviso}: la correlación es espuria.",
                      stacklevel=2)

    datos = datos[[c for c in {x, y, etiqueta} if c]].dropna(subset=[x, y])
    if ax is None:
        _, ax = plt.subplots(figsize=(9.5, 6.2), dpi=130)

    fig = ax.figure
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")

    ax.scatter(datos[x], datos[y], s=90, color=SERIE,
               edgecolor=SUPERFICIE, linewidth=2, zorder=3)

    if tendencia:
        # El ajuste va en el espacio en que se dibuja: una recta ajustada en
        # pesos se vería curva sobre un eje logarítmico.
        import numpy as np
        vx = np.log10(datos[x]) if log_x else datos[x]
        vy = np.log10(datos[y]) if log_y else datos[y]
        m, b = np.polyfit(vx, vy, 1)
        rejilla = np.linspace(vx.min(), vx.max(), 50)
        ax.plot(10 ** rejilla if log_x else rejilla,
                10 ** (m * rejilla + b) if log_y else m * rejilla + b,
                color=EJE, lw=1.5, ls=(0, (5, 3)), zorder=2)

    # El coeficiente se dibuja primero para poder reservarle el espacio: si se
    # pusiera al final, una etiqueta ya colocada quedaría debajo de la caja.
    rho, n = correlacion_rangos(datos, x, y)
    caja_rho = ax.annotate(f"rho de Spearman = {rho:.2f}   (n = {n})",
                           (1, 0), xycoords="axes fraction", xytext=(-6, 10),
                           textcoords="offset points", ha="right", fontsize=9,
                           color=SECUNDARIA, zorder=5,
                           bbox=dict(fc=SUPERFICIE, ec=RETICULA, pad=4))
    fig.canvas.draw()
    bb = caja_rho.get_window_extent()

    if etiqueta:
        sub = datos.loc[_puntos_notables(datos, x, y, etiquetar)]
        _colocar_etiquetas(ax, list(zip(sub[x], sub[y])), list(sub[etiqueta]),
                           reservado=[(bb.x0 - 4, bb.y0 - 4, bb.x1 + 4, bb.y1 + 4)])

    for eje, col, es_log in ((ax.xaxis, x, log_x), (ax.yaxis, y, log_y)):
        if es_log:
            lo, hi = (ax.get_xlim() if eje is ax.xaxis else ax.get_ylim())
            eje.set_major_locator(FixedLocator(_ticks_log(lo, hi)))
            eje.set_minor_locator(FixedLocator([]))
        eje.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"
                                              if abs(v) >= 1000 else f"{v:g}"))

    ax.set_xlabel(_nombre_eje(x) + (" — escala logarítmica" if log_x else ""),
                  fontsize=9, color=SECUNDARIA)
    ax.set_ylabel(_nombre_eje(y) + (" — escala log." if log_y else ""),
                  fontsize=9, color=SECUNDARIA)
    if titulo:
        ax.set_title(titulo, fontsize=12.5, color=TINTA,
                     pad=24 if nota else 14, loc="left")
    if nota:
        ax.annotate(nota, (0, 1), xycoords="axes fraction", xytext=(0, 10),
                    textcoords="offset points", fontsize=8.5, color=SECUNDARIA)

    ax.grid(True, color=RETICULA, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EJE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    fig.tight_layout()
    return ax


def alerta_ramos(alerta, titulo="", umbral_atencion=1.5, umbral_grave=3.0, ax=None):
    """
    Marca en qué ramos la siniestralidad se sale de lo normal para ese mercado.

    `alerta` es la salida de metricas.alerta_siniestralidad().

    El eje X son rangos intercuartiles del propio ramo, no puntos porcentuales,
    porque es la unidad en que está definido el umbral. Dibujarlo así hace
    visible la regla: las dos punteadas SON los cortes, y se ve de inmediato
    qué tan lejos quedó cada ramo de ellos. Con puntos porcentuales en el eje,
    los mismos cortes serían trece líneas distintas, una por ramo.

    La diferencia cruda se imprime al margen derecho para que las dos lecturas
    queden a la vista: son las que se contradicen entre sí.

    El color de estado nunca va solo. Los ramos marcados llevan la palabra
    ("atención", "grave") junto al punto, porque sobre fondo claro estos tonos
    no alcanzan 3:1 de contraste y el color por sí mismo no es legible para
    todos. Los ramos sin volumen suficiente van en hueco: no es que estén bien,
    es que no se evaluaron.
    """
    datos = alerta.dropna(subset=["iqrs"]).sort_values("iqrs", ignore_index=True)

    # La escala la marcan los ramos que SÍ se evaluaron. Un ramo sin volumen
    # puede dar 10 IQR de puro ruido (Pecuario 2025, con 1.5 mdp de prima) y
    # comprimiría contra el cero todo lo que de verdad hay que comparar.
    evaluados = datos[~datos["bandera"].isin(NO_EVALUADO)]["iqrs"]
    referencia = evaluados if len(evaluados) else datos["iqrs"]
    tope = max(umbral_grave * 1.3, referencia.max() * 1.35)
    piso = min(-0.6, referencia.min() * 1.15)
    # Franja reservada a la derecha para la columna de diferencias, para que un
    # punto recortado no acabe encima de los números.
    borde = tope + (tope - piso) * 0.17
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 0.42 * len(datos) + 2.4), dpi=130)

    fig = ax.figure
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)
    y = range(len(datos))

    # Los dos rótulos van a distinta altura: los cortes están cerca entre sí
    # (1.5 y 3.0) y con el eje ancho el texto de uno invade al del otro.
    for fila, (corte, nombre) in enumerate(((umbral_atencion, "atención"),
                                            (umbral_grave, "grave"))):
        ax.axvline(corte, color=ESTADO[nombre], lw=1.2, ls=(0, (4, 3)), zorder=1)
        ax.annotate(f"{nombre}  ({corte:g} IQR)", (corte, len(datos) - 0.4),
                    textcoords="offset points", xytext=(4, -13 * fila), fontsize=8,
                    color=ESTADO[nombre], style="italic", zorder=5)
    ax.axvline(0, color=EJE, lw=1, zorder=1)

    for i, fila in datos.iterrows():
        bandera = fila["bandera"]
        evaluado = bandera not in NO_EVALUADO
        color = ESTADO.get(bandera, MUTED)

        # Fuera de escala: se dibuja en el borde con una punta de flecha y el
        # valor real en el texto, para que se vea que sigue más allá en vez de
        # desaparecer sin aviso.
        x = min(max(fila["iqrs"], piso), tope)
        recortado = x != fila["iqrs"]
        por_derecha = recortado and fila["iqrs"] > tope

        # La línea al cero da la referencia: de qué lado del mercado quedó.
        ax.plot([0, x], [i, i], color=RETICULA, lw=1.5, zorder=2)
        ax.scatter(x, i, s=95, zorder=3, linewidth=1.8,
                   marker=(">" if por_derecha else "<") if recortado else "o",
                   color=color if evaluado else SUPERFICIE,
                   edgecolor=SUPERFICIE if evaluado else MUTED)

        # La palabra al lado del punto: la señal no puede depender del color.
        # Si el punto quedó pegado al borde derecho, el texto va del otro lado
        # para no invadir la columna de diferencias.
        texto = bandera + (f" · {fila['iqrs']:.0f} IQR" if recortado else "")
        dx, ha = (-11, "right") if por_derecha else (11, "left")
        if evaluado and bandera != "normal":
            ax.annotate(texto, (x, i), textcoords="offset points",
                        xytext=(dx, 0), va="center", ha=ha, fontsize=8.5,
                        weight="bold", color=color, zorder=4)
        elif not evaluado:
            ax.annotate(texto, (x, i), textcoords="offset points",
                        xytext=(dx, 0), va="center", ha=ha, fontsize=8,
                        color=MUTED, style="italic", zorder=4)

    ax.set_yticks(list(y))
    ax.set_yticklabels([CORTOS.get(r, r) for r in datos["DESC_RAMO"]], fontsize=9)
    ax.set_ylim(-0.7, len(datos) - 0.3)

    # Margen derecho con la lectura en puntos porcentuales, la que engaña.
    ax.set_xlim(piso, borde)
    for i, fila in datos.iterrows():
        marca = " *" if fila["sobre_prima"] else ""
        ax.annotate(f"{fila['dif']:+.0f}{marca}", (1, i), xycoords=("axes fraction", "data"),
                    xytext=(-4, 0), textcoords="offset points", ha="right", va="center",
                    fontsize=8.5, color=SECUNDARIA, family="monospace", zorder=4)
    ax.annotate("dif. en\npuntos", (1, len(datos) - 0.45), xycoords=("axes fraction", "data"),
                xytext=(-4, 0), textcoords="offset points", ha="right", va="center",
                fontsize=7.5, color=MUTED, style="italic")

    ax.set_xlabel("Distancia a la mediana del ramo, en rangos intercuartiles",
                  fontsize=9, color=SECUNDARIA)
    if titulo:
        ax.set_title(titulo, fontsize=12.5, color=TINTA, pad=14, loc="left")

    pie = "Punto hueco = cartera sin volumen suficiente para evaluar."
    if alerta["sobre_prima"].any():
        pie += "   * = siniestralidad sobre 100%: se pagó más de lo que se emitió."
    ax.annotate(pie, (0, 0), xycoords="axes fraction", xytext=(0, -38),
                textcoords="offset points", fontsize=8, color=MUTED)

    ax.grid(True, axis="x", color=RETICULA, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(EJE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.tick_params(axis="y", length=0, colors=SECUNDARIA)
    fig.tight_layout()
    return ax


# Dónde cae cada diagnóstico en el plano. La posición ES el diagnóstico: el
# color solo sirve para la segunda pregunta (si el sobrecosto está cobrado).
CUADRANTES = {
    "ambos":      (0.98, 0.97, "right", "top",    "ambos\nmás y más caros"),
    "frecuencia": (0.02, 0.97, "left",  "top",    "solo frecuencia\nmás siniestros"),
    "severidad":  (0.98, 0.03, "right", "bottom", "solo severidad\nmás caros"),
    "ninguno":    (0.02, 0.03, "left",  "bottom", "ninguno\nen línea o mejor"),
}


def mapa_frecuencia_severidad(diagnostico, titulo="", tolerancia=0.15, ax=None):
    """
    Sitúa cada ramo según de dónde viene su costo: frecuencia, severidad o ambas.

    `diagnostico` es la salida de metricas.diagnostico_frecuencia_severidad().

    Los ejes son razones contra el mercado, así que el punto (1, 1) es "igual
    al mercado" y los cuatro cuadrantes SON los cuatro diagnósticos. No hace
    falta leer una leyenda de color para saber qué le pasa a un ramo: basta
    mirar en qué esquina cayó.

    Escala logarítmica en ambos ejes porque son razones: estar al doble y a la
    mitad deben verse a la misma distancia del centro, y en escala lineal el
    lado de "mejor que el mercado" se aplastaría contra el cero.

    La diagonal es la línea de costo técnico igual al del mercado
    (frecuencia x severidad = 1). Por encima de ella el riesgo cuesta más que
    el promedio del ramo, sin importar de cuál de los dos factores venga.

    El color responde la pregunta que sigue al diagnóstico: el riesgo sale más
    caro, ¿lo compensa la prima? Rojo = no, la siniestralidad también está
    arriba del mercado. Gris = sí, está cobrado. El tamaño es la prima.
    """
    datos = diagnostico.dropna(subset=["razon_frecuencia", "razon_severidad"])
    datos = datos[(datos.razon_frecuencia > 0) & (datos.razon_severidad > 0)]
    excluidos = len(diagnostico) - len(datos)

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 7.4), dpi=130)
    fig = ax.figure
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    ax.set_xscale("log")
    ax.set_yscale("log")
    # Márgenes simétricos en el espacio logarítmico, para que el centro quede
    # en 1.0 y los dos lados pesen igual.
    for eje, col in ((ax.set_xlim, "razon_severidad"), (ax.set_ylim, "razon_frecuencia")):
        v = datos[col]
        extremo = max(v.max(), 1 / v.min()) ** 1.25
        eje(1 / extremo, extremo)

    # Banda de tolerancia: dentro de ella la diferencia no cuenta como problema.
    ax.axvspan(1 - tolerancia, 1 + tolerancia, color=RETICULA, alpha=0.55, zorder=0)
    ax.axhspan(1 - tolerancia, 1 + tolerancia, color=RETICULA, alpha=0.55, zorder=0)
    ax.axvline(1, color=EJE, lw=1.2, zorder=1)
    ax.axhline(1, color=EJE, lw=1.2, zorder=1)

    # Diagonal de costo técnico igual al del mercado.
    lo, hi = ax.get_xlim()
    ax.plot([lo, hi], [1 / lo, 1 / hi], color=EJE, lw=1, ls=(0, (5, 4)), zorder=1)
    # El rótulo se ancla DENTRO del tramo visible de la diagonal. Anclarlo al
    # borde no sirve: con rotación, matplotlib acomoda la caja de texto
    # alrededor del punto y el rótulo termina fuera del recuadro.
    ylo, yhi = ax.get_ylim()
    x1, x2 = max(lo, 1 / yhi), min(hi, 1 / ylo)
    x_rotulo = x1 * (x2 / x1) ** 0.18     # un quinto del tramo, en escala log
    rotulo = ax.annotate("mismo costo técnico que el mercado",
                         (x_rotulo, 1 / x_rotulo), textcoords="offset points",
                         xytext=(3, -3), ha="left", va="top", fontsize=7.5,
                         color=MUTED, style="italic", rotation=-32)
    fig.canvas.draw()
    # El rótulo va rotado, y get_window_extent devuelve su caja alineada a los
    # ejes: para un texto largo en diagonal esa caja es muchísimo más grande
    # que la tinta y bloquearía media gráfica al colocar las etiquetas. Se
    # reserva encogida hacia el centro, que aproxima la franja que ocupa.
    bb = rotulo.get_window_extent()
    cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
    ancho, alto = bb.width * 0.25, bb.height * 0.25
    bb_rotulo = (cx - ancho, cy - alto, cx + ancho, cy + alto)

    for clave, (fx, fy, ha, va, texto) in CUADRANTES.items():
        ax.annotate(texto, (fx, fy), xycoords="axes fraction", ha=ha, va=va,
                    fontsize=9, color=MUTED, linespacing=1.4, zorder=1)

    # Rojo solo donde el sobrecosto NO está cobrado: es la señal accionable.
    colores = [MUTED if ok else ESTADO["grave"] for ok in datos["sobrecosto_cobrado"]]
    # El área es proporcional a la prima (s de matplotlib ya es área), que es
    # la relación que el ojo lee bien. Con alfa, porque en una aseguradora
    # diversificada un ramo grande tapa por completo a dos chicos.
    tamanos = 40 + 230 * datos["prima_mdp_inst"] / datos["prima_mdp_inst"].max()
    ax.scatter(datos["razon_severidad"], datos["razon_frecuencia"],
               s=tamanos, color=colores, edgecolor=SUPERFICIE, linewidth=1.8,
               alpha=0.85, zorder=3)

    # El radio en puntos de pantalla: s es área en puntos cuadrados.
    radios = [(t / 3.14159) ** 0.5 + 2 for t in tamanos]
    _colocar_etiquetas(ax, list(zip(datos["razon_severidad"], datos["razon_frecuencia"])),
                       [CORTOS.get(r, r) for r in datos["DESC_RAMO"]], radios=radios,
                       reservado=[bb_rotulo])

    for eje in (ax.xaxis, ax.yaxis):
        lo, hi = (ax.get_xlim() if eje is ax.xaxis else ax.get_ylim())
        eje.set_major_locator(FixedLocator(
            [t for t in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20) if lo <= t <= hi]))
        eje.set_minor_locator(FixedLocator([]))
        eje.set_major_formatter(FuncFormatter(
            lambda v, _: f"{v:g}x" if v >= 1 else f"{v:.1f}x"))

    ax.set_xlabel("Severidad contra el mercado  (1x = igual)", fontsize=9, color=SECUNDARIA)
    ax.set_ylabel("Frecuencia contra el mercado  (1x = igual)", fontsize=9, color=SECUNDARIA)
    if titulo:
        ax.set_title(titulo, fontsize=12.5, color=TINTA, pad=24, loc="left")
    ax.annotate("El cuadrante es el diagnóstico. Tamaño = prima emitida.",
                (0, 1), xycoords="axes fraction", xytext=(0, 10),
                textcoords="offset points", fontsize=8.5, color=SECUNDARIA)

    pie = ("Rojo = el sobrecosto NO está cobrado (siniestralidad también arriba "
           "del mercado).   Gris = está cobrado.")
    if excluidos:
        pie += f"   {excluidos} ramo(s) sin referencia válida quedan fuera."
    ax.annotate(pie, (0, 0), xycoords="axes fraction", xytext=(0, -40),
                textcoords="offset points", fontsize=8, color=MUTED)

    ax.grid(True, color=RETICULA, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EJE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    fig.tight_layout()
    return ax


def carrera_contra_mercado(comparacion, titulo="", volumen_min=50, ax=None):
    """
    Crecimiento de la institución contra el de su mercado, ramo por ramo.

    `comparacion` es comparar_vs_mercado(df, institucion, crecimiento_anual)
    ya recortado a un año.

    Lo que importa de la tabla de crecimiento no es la tasa sino la BRECHA:
    crecer 10% donde el mercado creció 20% es perder terreno. Y perder terreno
    es literalmente perder cuota, así que la brecha se traduce al margen
    derecho en puntos de participación ganados o cedidos.

    Esa traducción es exacta, no una estimación: la cuota de cada año se
    calcula con las primas que la propia tabla ya trae, así que la brecha y el
    movimiento de cuota siempre concuerdan en signo.

    El dumbbell muestra las dos tasas además de la distancia entre ellas,
    que una barra de diferencias escondería: caer 19% mientras el mercado
    crece 13% no es lo mismo que crecer 4% mientras el mercado crece 30%,
    aunque la brecha sea parecida.

    Los ramos por debajo de `volumen_min` llevan la barra en gris: con prima
    diminuta, un crecimiento de 98% no significa nada. La advertencia va en la
    barra y no solo en el marcador porque la barra es el elemento que de
    verdad se ve de una fila. El umbral se
    escala a la ventana que cubre la tabla —que crecimiento_anual anota en
    attrs["meses"]— porque 50 mdp está calibrado sobre primas anuales y la
    tabla suele traer medio año.
    """
    # El umbral está calibrado sobre primas ANUALES, pero crecimiento_anual
    # recorta la tabla a los meses comparables (ene-jun mientras 2026 esté a
    # medias). Aplicar 50 mdp a media anualidad es exigir el doble: hay que
    # escalar el corte a la ventana que la tabla realmente cubre.
    meses = comparacion.attrs.get("meses")
    cobertura = len(list(meses)) / 12 if meses else 1.0
    corte = volumen_min * cobertura

    d = comparacion.dropna(subset=["crecimiento_pct_inst", "crecimiento_pct_mercado"]).copy()
    if d.empty:
        # El primer año de la base no tiene año anterior: la tabla llega con
        # filas pero todas sin crecimiento, y calcular límites sobre eso da NaN.
        if ax is None:
            _, ax = plt.subplots(figsize=(10.5, 3), dpi=130)
        return _vacia(ax, "Sin año anterior con el que comparar")
    d["cuota_dif"] = (100 * d["prima_mdp_inst"] / d["prima_mdp_mercado"]
                      - 100 * d["prima_previa_mdp_inst"] / d["prima_previa_mdp_mercado"])
    d["brecha"] = d["crecimiento_pct_inst"] - d["crecimiento_pct_mercado"]
    d["evaluado"] = d["prima_mdp_inst"] >= corte
    d = d.sort_values("brecha", ignore_index=True)

    if ax is None:
        _, ax = plt.subplots(figsize=(10.5, 0.46 * len(d) + 2.6), dpi=130)
    fig = ax.figure
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    # Todos los ramos entran en la escala, incluso los que no se evalúan. Antes
    # se recortaban al borde para que un +99% sobre 3 mdp no comprimiera la
    # gráfica, pero eso dejaba la fila sin barra visible: cuando los dos
    # extremos caían fuera, la brecha medía cero en pantalla y el ramo
    # desaparecía. Se prefiere perder algo de resolución a perder la fila.
    valores = d[["crecimiento_pct_inst", "crecimiento_pct_mercado"]]
    lo, hi = valores.min().min(), valores.max().max()
    margen = (hi - lo) * 0.12
    piso, tope = lo - margen, hi + margen
    borde = tope + (tope - piso) * 0.13        # franja para la columna de cuota

    ax.axvline(0, color=EJE, lw=1.2, zorder=1)

    for i, f in d.iterrows():
        # El color de la barra es la señal principal de la fila, así que es
        # donde va la advertencia: gris significa "esta dirección no es
        # confiable", y pesa mucho más que la forma del marcador.
        if not f["evaluado"]:
            color_barra = EJE
        else:
            color_barra = BUENO if f["brecha"] > 0 else ESTADO["grave"]

        xi, xm = f["crecimiento_pct_inst"], f["crecimiento_pct_mercado"]
        ax.plot([xm, xi], [i, i], color=color_barra, lw=3, alpha=0.55,
                solid_capstyle="round", zorder=2)
        ax.scatter(xm, i, s=70, marker="D", color=SUPERFICIE,
                   edgecolor=MUTED, linewidth=1.8, zorder=3)
        ax.scatter(xi, i, s=110, zorder=4, linewidth=1.8, marker="o",
                   edgecolor=SERIE if not f["evaluado"] else SUPERFICIE,
                   color=SUPERFICIE if not f["evaluado"] else SERIE)

    ax.set_yticks(range(len(d)))
    ax.set_yticklabels([CORTOS.get(r, r) for r in d["DESC_RAMO"]], fontsize=9)
    ax.set_ylim(-0.75, len(d) - 0.25)
    ax.set_xlim(piso, borde)

    # Columna derecha: la consecuencia de la brecha, en puntos de cuota.
    for i, f in d.iterrows():
        signo = "+" if f["cuota_dif"] >= 0 else ""
        color = SECUNDARIA if f["evaluado"] else MUTED
        ax.annotate(f"{signo}{f['cuota_dif']:.2f}", (1, i),
                    xycoords=("axes fraction", "data"), xytext=(-6, 0),
                    textcoords="offset points", ha="right", va="center",
                    fontsize=8.5, color=color, family="monospace", zorder=4)
    ax.annotate("cuota\n(puntos)", (1, len(d) - 0.35), xycoords=("axes fraction", "data"),
                xytext=(-6, 0), textcoords="offset points", ha="right", va="center",
                fontsize=7.5, color=MUTED, style="italic")

    # Con dos series la leyenda es obligatoria: el color no puede ser la única
    # forma de saber cuál punto es quién.
    ax.scatter([], [], s=110, color=SERIE, edgecolor=SUPERFICIE,
               linewidth=1.8, label="la institución")
    ax.scatter([], [], s=70, marker="D", color=SUPERFICIE, edgecolor=MUTED,
               linewidth=1.8, label="su mercado")
    leyenda = ax.legend(loc="lower right", frameon=True, fontsize=8.5,
                        framealpha=1, edgecolor=RETICULA, borderpad=0.7)
    leyenda.get_frame().set_facecolor(SUPERFICIE)
    for t in leyenda.get_texts():
        t.set_color(SECUNDARIA)

    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.set_xlabel("Crecimiento contra el mismo periodo del año anterior",
                  fontsize=9, color=SECUNDARIA)
    if titulo:
        ax.set_title(titulo, fontsize=12.5, color=TINTA, pad=42, loc="left")

    # El periodo comparado no puede quedar implícito: las cifras son de una
    # ventana recortada, no del año completo, y sin decirlo se leen mal.
    # Van como dos anotaciones y no como un texto de dos líneas, para fijar
    # la altura de cada una y que ninguna invada el título.
    ventana_txt = _nombre_ventana(meses)
    anios = sorted(int(a) for a in d["ANIO"].unique())
    periodo = " y ".join(f"{ventana_txt} {a} contra {ventana_txt} {a - 1}" for a in anios)
    for texto, altura, color in (
        (f"Compara {periodo}.", 26, TINTA),
        ("Barra roja = crece menos que su mercado y cede cuota.   Verde = le gana.   "
         "Gris = sin volumen para juzgar.", 10, SECUNDARIA),
    ):
        ax.annotate(texto, (0, 1), xycoords="axes fraction", xytext=(0, altura),
                    textcoords="offset points", fontsize=8.5, color=color)
    ventana = (f"{len(list(meses))} de 12 meses" if meses else "el año completo")
    ax.annotate(f"Barra gris y punto hueco = prima menor a {corte:,.0f} mdp en la "
                f"ventana medida ({ventana}): el porcentaje es ruido.",
                (0, 0), xycoords="axes fraction", xytext=(0, -40),
                textcoords="offset points", fontsize=8, color=MUTED)

    ax.grid(True, axis="x", color=RETICULA, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(EJE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.tick_params(axis="y", length=0, colors=SECUNDARIA)
    fig.tight_layout()
    return ax
