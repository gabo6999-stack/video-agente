# Proyecto: Guion → Video automático

Este proyecto convierte un guion en texto plano en un video terminado,
usando **ElevenLabs** (voz) y **Grok Imagine / xAI** (clips animados).

## Flujo cuando el usuario diga "haz el video" / "convierte el guion"

Sigue EXACTAMENTE estos pasos, sin preguntar de más:

1. **Lee `guion.txt`** (el guion en texto plano que pegó el usuario).

2. **Divídelo en escenas.** Cada escena = una frase o idea completa de la
   narración, de **máximo ~25 palabras** (≈10 segundos hablados). No más,
   porque Grok genera clips de hasta 10 s.

3. **Para cada escena escribe un prompt visual cinematográfico** en inglés,
   con esta estructura: sujeto + acción + ambiente + tipo de plano +
   movimiento de cámara + estilo (ej: "photorealistic, 35mm film grain") +
   aspect ratio.
   - Si un personaje, lugar u objeto aparece en varias escenas, **repite su
     descripción palabra por palabra** en cada prompt para mantener
     consistencia (Grok pierde la coherencia si la cambias).
   - Respeta el `aspect_ratio` configurado abajo y añádelo al final de cada
     prompt ("vertical 9:16" o "horizontal 16:9").

4. **Genera `guion.json`** con esta forma:
   ```json
   {
     "config": { "aspect_ratio": "9:16", "resolution": "720p",
                 "voice_id": "TxGEqnHWrfWFTfGW9XjX", "burn_subtitles": true,
                 "output_file": "video_final.mp4" },
     "escenas": [
       { "narracion": "<texto de la escena>", "visual": "<prompt en ingles>" }
     ]
   }
   ```

5. **Verifica las claves API** antes de correr:
   ```bash
   echo "XAI=${XAI_API_KEY:+ok}  ELEVEN=${ELEVENLABS_API_KEY:+ok}"
   ```
   Si falta alguna, pídesela al usuario y recuérdale:
   `export XAI_API_KEY="..."` y `export ELEVENLABS_API_KEY="..."`

6. **Ejecuta el pipeline:**
   ```bash
   python3 make_video.py guion.json
   ```

7. **Muestra el resultado:** confirma que se creó `video_final.mp4` y di su
   duración. Si una escena falla, reintenta solo esa escena.

## Preferencias por defecto (cámbialas si el usuario pide otra cosa)

- Formato: **vertical 9:16** (TikTok/Reels/Shorts). Si dice "YouTube" → 16:9.
- Idioma de la voz: **español** (el modelo `eleven_multilingual_v2` ya lo cubre).
- Subtítulos: **activados**.
- Tono visual: cinematográfico y fotorrealista, salvo que el usuario pida otro
  estilo (animado 2D, cartoon, anime, etc.) — en ese caso aplícalo a TODOS los
  prompts para que el video sea coherente.

## Notas

- `make_video.py` ya maneja toda la sincronía voz↔video, mezcla de audio,
  concatenación y subtítulos. No lo reescribas salvo que el usuario lo pida.
- Costos aprox.: Grok ~30–40 créditos por clip; ElevenLabs por caracteres.
