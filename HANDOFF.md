# HANDOFF — Video Agente

Documento de continuidad. **Lee este archivo entero antes de tocar nada.**
Sirve para retomar el proyecto desde una sesión nueva de Claude Code o desde un chat nuevo de Claude web.

- Última actualización: 2026-05-30
- Último commit en `main`: **`0b190ed`** (`feat: animar imágenes con FFmpeg Ken Burns gratis, reemplaza Vidu image-to-video`)
- URL pública activa: **https://videoagenterafa.up.railway.app**
- Repo: **https://github.com/gabo6999-stack/video-agente** (privado, rama `main`)

---

## 1. Resumen ejecutivo

- **Qué es la app**: generador automático de videos cortos verticales (Reels/TikTok/Shorts) que orquesta Claude (guion e ideas) + ElevenLabs (voz) + fal.ai Vidu Q3 Turbo (clips) + FFmpeg (montaje y subtítulos). Frontend Streamlit con persistencia multi-cliente.
- **Estado actual**: DESPLEGADA Y FUNCIONANDO en https://videoagenterafa.up.railway.app. La app carga, las 3 APIs responden, falta solo validar la generación completa en producción.
- **Lo último que se hizo (2026-05-30)**: se reemplazó el modo imagen-a-video. Antes las imágenes del usuario se mandaban a fal.ai Vidu (`image-to-video`, $0.07/s) para animarlas. Ahora se animan **localmente y GRATIS con FFmpeg** (efecto Ken Burns: zoom/paneo suave, movimiento variado por escena, salida 9:16 con la duración de la voz). Costo de animación de esas escenas = $0. El modo texto-a-video (fal Vidu Turbo) quedó intacto. Se actualizaron los textos y el cálculo de costo en la app. (Antes de esto: se borró el campo *Custom Start Command* del dashboard de Railway, que sobrescribía el `CMD` del Dockerfile.)

---

## 2. Arquitectura y stack

- **Frontend**: Streamlit (1.57.0). Sidebar con 3 grupos visualmente diferenciados por píldoras de color:
  - 🔵 **PRODUCIR** — Crear video, Usar mis imágenes
  - 🟢 **IDEAS Y CLIENTES** — Ideas desde keywords, Repositorio / calendario
  - 🟠 **SISTEMA** — Biblioteca de videos, Configuración (llaves)
  - Cabecera del sidebar con el saldo de ElevenLabs (1 sola API expone saldo público; fal y Anthropic no).
- **Backend**: Python 3.13, librerías ancladas en `requirements.txt`. SDKs: `anthropic`, `fal-client`. ElevenLabs vía REST (`requests`). FFmpeg + ffprobe vía subprocess.
- **Modelos por defecto**:
  - **Claude**: `claude-sonnet-4-6` para guiones (a partir de descripción libre) y para ideas + scripts (a partir de keywords). Caching ephemeral sobre el system prompt.
  - **ElevenLabs**: cualquier voice_id de la cuenta. Claude la elige automáticamente según el tono pedido consultando `GET /v1/voices` en vivo. Modelo TTS: `eleven_multilingual_v2`.
  - **fal.ai Vidu Q3 Turbo 540p**: `fal-ai/vidu/q3/text-to-video/turbo` ($0.035/s, ~$0.21 por clip de 6s). Solo se usa para **texto-a-video** (escenas sin imagen propia).
  - **Imagen-a-video (animar imágenes del usuario)**: ⚠️ YA NO usa fal.ai. Ahora se hace **localmente y GRATIS con FFmpeg** (efecto Ken Burns: zoom/paneo suave sobre la imagen fija). Ver `generar_clip_kenburns()` en `make_video.py`. Costo de animación = **$0** (solo se paga la voz de ElevenLabs).
- **Deploy**: Railway con **Dockerfile** propio (NO Nixpacks, NO Railpack). Puerto fijo **8080**, sin password (equipo interno, link cerrado).

---

## 3. Archivos del proyecto

### Código y configuración activos

| Archivo | Función |
|---|---|
| `app.py` | Frontend Streamlit. Sidebar con 3 grupos, login gate opcional vía `APP_PASSWORD` env, las 6 páginas, descarga de videos generados, diagnóstico de arranque (`[startup]` ffmpeg/ffprobe). Orquesta llamadas a `generar.py` y `make_video.py`. |
| `make_video.py` | Pipeline core. Lee `guion.json`, por escena: genera voz (ElevenLabs), genera clip mudo (si hay imagen propia del usuario → **Ken Burns local con FFmpeg, gratis**, vía `generar_clip_kenburns()`; si no → fal Vidu Q3 texto-a-video), monta con FFmpeg respetando "la voz manda" (`-t voz_dur` + `tpad`). Persistencia en `.trabajo_<output>/` con reanudación y 3 reintentos por clip (los reintentos aplican a t2v; el Ken Burns es local y no reintenta). Outro opcional con logo. Quema subtítulos elegantes. `media_duration()` tiene fallback `ffmpeg -i` si `ffprobe` no está. |
| `generar.py` | "Cerebro" Claude API. Funciones públicas: `cargar_llaves()`, `obtener_voces_elevenlabs()`, `pedir_guion_a_claude()` (descripción libre → guion), `proponer_ideas()` y `generar_script_para_idea()` (desde keywords), `script_a_brief()`, `calcular_costo()`, `calcular_costo_mixto()`. Defaults estándar: 6 escenas × 6s × $0.035/s = **$1.26/video**. |
| `clientes.py` | Persistencia por cliente. `ruta_cliente(name, crear=True/False)` evita crear carpetas fantasma desde lecturas. `leer_keywords_excel()` tolerante a nombres ("palabra clave"/"keyword"/"kw" y "volumen"/"search volume"/etc). `listar_clientes()` filtra solo carpetas con `meta.json`. Guardar/leer keywords, ideas, scripts. |
| `Dockerfile` | `FROM python:3.13-slim`, `apt-get install ffmpeg` (incluye ffprobe), `COPY . .`, `CMD ["sh","-c","unset STREAMLIT_SERVER_* && exec streamlit run app.py --server.port=8080 ..."]`. `EXPOSE 8080`. |
| `railway.json` | Forza Railway a usar `builder: "DOCKERFILE"` y `dockerfilePath: "./Dockerfile"`. Sin esto Railway intenta autodetectar con Railpack y reescribe el CMD. |
| `.dockerignore` | Excluye del contexto Docker: `claves.txt`, `clientes/`, `.uploads/`, `.trabajo_*/`, `*.mp4`, logs, `.git/`, `__pycache__/`. |
| `requirements.txt` | Pins exactos: `streamlit==1.57.0`, `anthropic==0.104.1`, `requests==2.34.2`, `pandas==2.2.3`, `openpyxl==3.1.5`, `fal-client==1.0.0`. |
| `CLAUDE.md` | Instrucciones del proyecto para Claude Code. Define el flujo "haz el video" original (lee `guion.txt`, divide en escenas, genera `guion.json`, ejecuta `make_video.py`). Reglas heredadas: prompts visuales en inglés, vertical 9:16, repetir descripciones de entidades. **Algunas reglas están desactualizadas** (CLAUDE.md asume el flujo CLI viejo; el flujo real ahora es Streamlit + `generar.py`). |
| `.gitignore` | Excluye del repo: `claves.txt`, `clientes/`, `.uploads/`, `.trabajo_*/`, `*.mp4`, `guion.json`, `guion.txt`, `*.log`, `__pycache__/`. |

### Archivos secundarios

| Archivo | Función |
|---|---|
| `prueba_fal.py` | Script standalone para probar la API de fal con un clip de prueba (~$0.21). Útil para diagnosticar si fal responde sin tocar el pipeline. |
| `guion.txt`, `guion.json` | Inputs/outputs efímeros del pipeline. Ignorados por git y docker. |
| `nixpacks.toml.bak`, `Procfile.bak` | Configs muertas de intentos previos con Nixpacks/Railpack. Conservadas como historial, no se usan. Ignoradas en `.dockerignore`. |

---

## 4. Configuración actual de Railway

| Campo | Valor |
|---|---|
| Workspace | **gabo6999-stack** (plan PRO, $20/mes) |
| Proyecto | **optimistic-enthusiasm** (ID empieza con `31beacc3-264a-43eb-a4e4-...`) |
| Servicio | **web** |
| URL pública | **videoagenterafa.up.railway.app** |
| Builder | **DOCKERFILE** (forzado vía `railway.json`) |
| Dockerfile path | `./Dockerfile` |
| Puerto | **8080** (hardcodeado en `Dockerfile`, `EXPOSE 8080`) |
| **Custom Start Command** | **VACÍO** — ⚠️ CRÍTICO: NO volver a llenarlo |
| Variables de entorno | `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `FAL_KEY` |
| `APP_PASSWORD` | NO configurada (sin login, decisión del equipo) |
| Disco | **EFÍMERO**: `clientes/`, `.uploads/`, `*.mp4`, `.trabajo_*/` se borran en cada redeploy o restart del contenedor |

---

## 5. Configuración de GitHub

| Campo | Valor |
|---|---|
| Cuenta/Org | **gabo6999-stack** |
| Repo | **gabo6999-stack/video-agente** |
| Visibilidad | Privado (el equipo decidió privado finalmente; se creó público y se cambió a privado desde Settings) |
| Rama default | `main` |
| Último commit | **`42a3d84`** — `fix(railway): force DOCKERFILE builder + unset injected STREAMLIT_SERVER_PORT` |
| Commit del puerto fijo | `e00bc16` — `fix(railway): hardcode port 8080, drop $PORT expansion` (este es el que importa funcionalmente; los siguientes fueron intentos que no aplicaron porque el bug real estaba en el dashboard) |

Autenticación en este proyecto: `gh` CLI 2.93.0 instalado en `C:\Program Files\GitHub CLI\gh.exe`. Sesión activa como `gabo6999-stack` (token guardado por gh; no se necesita re-login para push).

---

## 6. Cronología de problemas resueltos (ya superados, NO repetir)

1. **"Connection error" con Claude API en sesiones iniciales**
   - Causa: la llave inicial era inválida.
   - Solución: se reemplazó por una nueva válida en `claves.txt` (local) y en Railway → Variables (producción).

2. **`ffprobe` no encontrado en Railway** (loop "[Errno 2] No such file or directory: 'ffprobe'")
   - Causa: primero usamos `nixpacks.toml` con `aptPkgs = ["ffmpeg"]`; los binarios quedaban en `/usr/bin` pero el PATH del runtime no los exponía. Después se descubrió que Railway estaba usando **Railpack autodetect** que ignoraba el `nixpacks.toml`.
   - Solución: switch a **Dockerfile propio** con `FROM python:3.13-slim` + `apt-get install ffmpeg` (el paquete apt incluye `ffprobe` en el mismo bin/). Forzado vía `railway.json` con `builder: "DOCKERFILE"`.

3. **`Error: Invalid value for '--server.port': '$PORT' is not a valid integer`** (loop infinito)
   - Causa raíz: el dashboard de Railway (Settings → Deploy → **Custom Start Command**) tenía pegado un comando literal `streamlit run ... --server.port=$PORT ...` que sobrescribía el `CMD` del Dockerfile, y `$PORT` no se expandía porque la variable PORT no estaba expuesta en este servicio (verificado en Variables).
   - Intentos previos que NO solucionaron: shell-form CMD, exec-form, `sh -c`, hardcode 8080 en Dockerfile, `unset STREAMLIT_SERVER_PORT`. Todos quedaron pisados por el Custom Start Command.
   - **Solución definitiva**: borrar manualmente el contenido del campo *Custom Start Command* del dashboard. Sin commit, sin código. Solo dejar ese campo vacío.

---

## 7. Funcionalidades implementadas

Todas probadas en local. Estado en nube indicado entre paréntesis.

- **Modo texto-a-video** (default): describes el tema, Claude redacta el guion y los prompts visuales, fal Vidu Q3 Turbo genera los clips.
- **Modo "usar mis imágenes"** (mixto): subes hasta N imágenes propias en la sección opcional; las primeras N escenas se animan **GRATIS en local con FFmpeg Ken Burns** (zoom/paneo suave, movimiento variado por escena, salida 9:16 que calza con el resto); las restantes usan texto-a-video. **Costo de animación de esas escenas = $0** (solo se paga la voz). El costo se recalcula en vivo y el botón muestra "gratis" cuando todas las escenas usan tus fotos.
- **Logo outro opcional**: subes un PNG (con transparencia ok), se agrega como pantalla final de 2.5s sobre fondo negro. No cuesta API.
- **Toggle de subtítulos**: ON por defecto, estilo Reels (Arial 14, bold, borde 1.4px, margen V=60, máximo 2 líneas con wrap balanceado por palabras).
- **Defaults estándar**: 6 escenas × 6s × $0.035/s = **$1.26/video**. Si pides más escenas, calcula y pide confirmación.
- **"Ideas desde keywords"**: por cliente, sube un Excel con `palabra clave` + `volumen de búsqueda` (acepta variantes), Claude propone 5–10 ideas; cada idea tiene botón "Generar script" (escribe el guion completo de 6 escenas siguiendo las reglas) y luego "Enviar al generador" (precarga la descripción en "Crear video" vía `session_state`, NO genera nada hasta que el usuario pulse Generar manualmente).
- **Repositorio / calendario**: por cliente, vista listado de últimas ideas + scripts guardados, cada uno expandible con "Enviar al generador".
- **Biblioteca de videos**: lista los `.mp4` de la carpeta del proyecto con preview inline y botón de descarga.
- **Sincronía "la voz manda"**: `voz_dur = media_duration(voz_mp3)` define la duración exacta del scene. `-t voz_dur` + `tpad=stop_mode=clone:stop_duration=...` rellena con frame congelado si el clip es más corto.
- **Persistencia y reanudación**: `.trabajo_<output_slug>/` guarda `voz_N.mp3`, `clip_N.mp4`, `escena_N.mp4` por escena. Si una escena falla tras 3 reintentos, las demás se conservan y el script avisa cuáles faltan; basta re-correr el mismo comando para reintentar solo ésas.

---

## 8. Estado de pruebas en producción

| Cosa | Estado |
|---|---|
| App carga en internet (https://videoagenterafa.up.railway.app) | ✅ |
| Llaves leídas desde Railway env vars (las 3) | ✅ |
| ElevenLabs responde (lista 23 voces) | ✅ |
| Claude API responde (genera ideas y guiones) | ✅ |
| Generación de video COMPLETA en producción | ⚠️ NO probada después del fix final del Custom Start Command. **Es lo siguiente que toca probar.** |

---

## 9. Filosofía y preferencias del usuario (Rafa, GrupoPTM)

- **Sin password**: equipo interno, link cerrado por confianza. No habilitar `APP_PASSWORD` salvo pedido explícito.
- **Cada cliente pone sus llaves**: las llaves en producción son las del workspace del equipo, pero la idea es que cuando le pasen el link a un cliente, ese cliente edite sus propias llaves desde la pestaña Configuración (no que el equipo gaste sus créditos por cada cliente).
- **Sencillez sobre todo**: Rafa no es técnico. Los mensajes en la UI deben ser claros, en español, sin jerga. Los errores deben decir qué hacer, no solo qué pasó.
- **6 escenas como estándar**, costo siempre visible antes de generar (`~$1.26 — 6 escenas` en el botón).
- **Calidad cinematográfica exigente**: evitar manos en primer plano, textos/letreros en pantalla y rostros en close-up con diálogo (la IA falla ahí). Cierre técnico literal en cada prompt: `"photorealistic, highly detailed, sharp focus, professional cinematography, 35mm film grain, color graded, shallow depth of field"`. Paleta consistente entre las 6 escenas.
- **Sincronía**: 14–16 palabras por escena, nunca más de 18 → ~6 segundos de voz → calza con clip de 6s.
- **Si toca salud**: cierre responsable invitando a consultar a un profesional. Nada de promesas médicas ni curas garantizadas.

---

## 10. Siguiente paso inmediato

Generar un video de prueba CORTO (3 escenas, ~$0.63) en https://videoagenterafa.up.railway.app para validar el pipeline completo en la nube ahora que el `Custom Start Command` está borrado.

Pasos:
1. Abrir https://videoagenterafa.up.railway.app
2. Ir a **Crear video** → escribir cualquier tema corto (ej. "video sobre los beneficios de tomar agua") → cambiar el selector de escenas a **3** → revisar el costo `~$0.63 — 3 escenas` → pulsar Generar
3. Esperar ~3-5 min (3 escenas × ~60s cada una en Vidu Q3 Turbo, más voz + montaje)
4. Cuando termine: **descargar el .mp4 inmediatamente con el botón ⬇️** antes de cerrar la pestaña — el disco de Railway es efímero y se pierde al próximo redeploy/restart.

Si la prueba funciona: la app está lista para producción real.
Si falla: revisar logs en Railway → Deployments → Active deployment → Deploy Logs. Buscar las líneas `[startup]` y mensajes de Claude/fal/ElevenLabs.

---

## 11. Advertencias para el futuro

- ⚠️ **NUNCA volver a llenar el campo *Custom Start Command*** en Railway → Settings → Deploy. Mantenerlo VACÍO. Si vuelve a aparecer un error de `--server.port=$PORT`, lo primero que hay que revisar es ese campo.
- ⚠️ **NUNCA cambiar el puerto 8080** del Dockerfile sin actualizar también `EXPOSE` y verificar que Railway enrute al nuevo puerto.
- ⚠️ **SIEMPRE excluir `claves.txt` y `clientes/`** del contexto Docker (`.dockerignore`) y del repo (`.gitignore`). Las llaves de producción viven en Railway → Variables, no en el repo.
- ⚠️ **Si el deploy "Active" deja de responder y los logs no muestran errores claros**: revisar (en este orden) (a) Custom Start Command vuelto a pegarse, (b) cambios manuales en variables de entorno, (c) commit reciente que rompa el build.
- ⚠️ **Disco efímero en Railway**: los videos generados, las imágenes subidas, las carpetas de cliente (`clientes/<slug>/`), las cachés de reanudación (`.trabajo_*/`) **se borran en cada redeploy o restart**. Para datos persistentes hay que mover a un Railway Volume o a S3 (fuera del scope actual; se puede agregar cuando haya volumen real de uso).
- ⚠️ **Builder forzado a DOCKERFILE**: si en algún momento Railway/Railpack se actualizan y empiezan a ignorar `railway.json`, hay que verificar en Settings → Build que el builder siga siendo "Dockerfile". Si cambia a "Railpack" o "Nixpacks", todo el sistema rompe.

---

## Apéndice — Cómo retomar en una sesión nueva

### Si abres Claude Code en `C:\Users\Admin\Downloads\mi-videos\`:
1. Lee este archivo entero.
2. Lee `CLAUDE.md` (algunas reglas están desactualizadas pero el contexto es útil).
3. Ejecuta `git log --oneline -10` para ver los últimos commits y confirmar que sigues en `42a3d84` (o más nuevo).
4. Si quieres probar localmente: `streamlit run app.py` (necesita `claves.txt` con las 3 llaves y `ffmpeg` en PATH).

### Si abres un chat nuevo de Claude web:
1. Comparte este HANDOFF.md en el chat.
2. Comparte también la URL del repo: https://github.com/gabo6999-stack/video-agente
3. Si la conversación va sobre código, indícale que `app.py`, `make_video.py`, `generar.py` y `clientes.py` son los 4 archivos clave.

### Llaves API necesarias para reproducir el setup
- **Anthropic** (`sk-ant-api03-...`) — para Claude
- **ElevenLabs** (`sk_...`) — para voz
- **fal.ai** (formato `<id>:<secret>`) — para clips de video
- Local: ponerlas en `claves.txt` (gitignored)
- Railway: ponerlas en Variables del servicio
