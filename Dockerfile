FROM python:3.13-slim

# ffmpeg via apt - el paquete 'ffmpeg' de Debian incluye TANTO ffmpeg
# como ffprobe en /usr/bin/, los dos binarios que make_video.py necesita.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps Python primero para cachear esta capa cuando solo cambia el codigo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto (respeta .dockerignore)
COPY . .

# Puerto fijo 8080. Razon: $PORT no se expone en este servicio de Railway.
# Ademas, Railway/Railpack inyecta STREAMLIT_SERVER_PORT como env var con
# valor literal "$PORT", lo cual streamlit lee como prioridad sobre los
# flags CLI. Por eso usamos sh -c para hacer 'unset' defensivo de todos
# los STREAMLIT_* relevantes antes de lanzar streamlit, garantizando que
# los flags --server.* del CMD sean los unicos que cuenten.
EXPOSE 8080

CMD ["sh", "-c", "unset STREAMLIT_SERVER_PORT STREAMLIT_SERVER_ADDRESS STREAMLIT_SERVER_HEADLESS STREAMLIT_BROWSER_GATHERUSAGESTATS && exec streamlit run app.py --server.port=8080 --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
