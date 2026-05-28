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

# Streamlit en el puerto que asigna Railway. CMD en shell form para que
# $PORT se expanda en runtime (Railway lo inyecta como variable de entorno).
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
