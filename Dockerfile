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

# Puerto fijo 8080. Razon: la variable $PORT no se expone en este servicio
# de Railway (verificado en su panel de Variables), asi que cualquier intento
# de expandirla resulta en literal "$PORT" y revienta streamlit. Con puerto
# fijo + EXPOSE, Railway sabe enrutar correctamente sin depender de $PORT.
EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
