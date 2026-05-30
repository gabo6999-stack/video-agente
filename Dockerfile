FROM python:3.13-slim

# ffmpeg via apt - el paquete 'ffmpeg' de Debian incluye TANTO ffmpeg
# como ffprobe en /usr/bin/, los dos binarios que make_video.py necesita.
# Tambien curl/ca-certificates (para bajar Piper) y libstdc++6/libgomp1
# (librerias que necesita el binario de Piper en Debian slim).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates libstdc++6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# --- Piper: voz local GRATIS (TTS neuronal open-source, corre en CPU) ---
# Binario self-contained (incluye onnxruntime + espeak-ng) + 4 voces neutras
# en espanol. Todo va a /opt/piper. Se descarga en el build (NO en el repo).
# Esta capa se cachea: solo se rehace si cambian estas lineas, no con el codigo.
ENV PIPER_DIR=/opt/piper
ENV LD_LIBRARY_PATH=/opt/piper
RUN curl -fsSL -o /tmp/piper.tar.gz \
        https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
    && tar -xzf /tmp/piper.tar.gz -C /opt \
    && rm /tmp/piper.tar.gz \
    && mkdir -p /opt/piper/voices \
    && PV="https://huggingface.co/rhasspy/piper-voices/resolve/main" \
    && for V in \
        "es/es_ES/davefx/medium/es_ES-davefx-medium" \
        "es/es_MX/ald/medium/es_MX-ald-medium" \
        "es/es_ES/sharvard/medium/es_ES-sharvard-medium" \
        "es/es_MX/claude/high/es_MX-claude-high" ; do \
        N=$(basename "$V") ; \
        curl -fsSL -o "/opt/piper/voices/${N}.onnx"      "${PV}/${V}.onnx" ; \
        curl -fsSL -o "/opt/piper/voices/${N}.onnx.json" "${PV}/${V}.onnx.json" ; \
    done

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
