Análisis de benchmarking del sector asegurador mexicano con datos públicos de la CNSF, para comparar el desempeño de una aseguradora contra el mercado

Análisis comparativo del sector asegurador en México a partir de la información pública que publica la Comisión Nacional de Seguros y Fianzas (CNSF). El objetivo es calcular métricas de mercado —participación por ramo, siniestralidad, frecuencia y severidad, crecimiento— que permitan comparar el desempeño de una aseguradora contra el resto del sector.
Proyecto en desarrollo. Autor: Mateo Vasconcelos.

Datos:
URL de DataBase tendencias seguros: https://sio.cnsf.gob.mx/ORS, dar click en "Tendencias de Seguros", scrollear hasta abajo y dar click en "Descargar Base Completa"
El sitio ignora cualquier filtro a la hora de descargar, descarga la base completa desde 2021
Constultado el 14/08/2026 12:45 pm
La base de datos es muy grande por lo que la puse en .gitignore, se tendrá que descargar para que corran los códigos

Requisitos y entorno:
Python 3.x
Entorno virtual con las dependencias del proyecto:
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt

Forma de DataBase:
Cuanta con más de 800,000 filas y 9 columnas
Granularidad: una fila por institución × ramo × entidad federativa × fecha de corte.
Las columnas son: FECHA_CORTE	NOMBRE_CORTO	DESC_RAMO	DESC_ENTIDADFEDERATIVA (estado de la república)	RIESGOS_ASEG_VIG (riesgos en vigor)	NUM_SIN_O_RECLAMACION (frecuencia)	PRIMA_EMI (prima emitida)	SUMA_ASEG (suma asegurada)	MONTO_SIN (monto de siniestros)
Cubre el historial desde 2021-04-30 hasta 2026-06-30 en  formato str con cortes mensuales 
Tenemos 100 instituiciones distintas y 21 ramos: 
Responsabilidad Civil, Transportes de Mercancías, Incendio, Terremoto, Fenómenos Hidrometeorológicos, Agrícola, Diversos Misceláneos, Diversos Ramos Técnicos, Pensiones, Pecuario, Automóviles, Vida, Accidentes Personales (incluye Ind, Gpo y Col), Gastos Médicos (incluye Ind, Gpo y Col), Crédito a la Vivienda, Cascos Aeronaves, Cascos Embarcaciones,Salud (incluye Individual, Grupo y Colectivo), Caución, Crédito, Garantía Financiera

Advertencias sobre los datos:
Los montos están en pesos (mxn), no en millones de pesos
Los montos se van acumulando durante el año, no es lo que se ganó en el mes individualmente (excepto por enero). Habrá que restar los montos de meses consecutivos
SUMA_ASEG es cero en Pensiones, porque esas instituciones se dedican a administrar pagos mensuales (nota de la fuente).
SUMA_ASEG es cero en Automóviles, por las múltiples coberturas con distinta suma asegurada que puede tener un mismo auto (nota de la fuente).

Glosario: 
El vocabulario fue sacado de: Vocabulario aseguradora .docx