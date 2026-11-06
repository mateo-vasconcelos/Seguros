# Imagen para desplegar el dashboard en Dokploy (tipo de build: Dockerfile).
# Solo instala requirements.txt: la app lee el parquet ya procesado y no
# necesita el stack de Jupyter ni openpyxl.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Código y datos que usa la app. Lo demás queda fuera por .dockerignore.
COPY .streamlit/ .streamlit/
COPY src/ src/
COPY data/processed/ data/processed/
COPY data/geo/ data/geo/
COPY dashboard.py graficas.py metricas.py ./

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)" || exit 1

# Opciones de servidor por línea de comandos para no alterar
# .streamlit/config.toml, que también se usa en local.
CMD ["streamlit", "run", "dashboard.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
