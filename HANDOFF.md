# HANDOFF — Video Agente

Documento de continuidad. **Lee este archivo entero antes de tocar nada.**
Sirve para retomar el proyecto desde una sesión nueva de Claude Code o desde un chat nuevo de Claude web.

- Última actualización: 2026-05-30 (fin de sesión)
- Último commit de código en `main`: **`3d57d5d`** (Kokoro como voz por defecto). Doc: `b7aa952` + este cierre de sesión.
- URL pública activa: **https://videoagenterafa.up.railway.app**
- Repo: **https://github.com/gabo6999-stack/video-agente** (privado, rama `main`)

---

## 0. ⚠️ LO PRIMERO PARA EL PRÓXIMO CHAT (urgente + pendientes)

### PASO 0 — URGENTE: verificar que Kokoro está REALMENTE desplegado en Railway
Cuando Rafa probó en producción, **la voz seguía sonando como PIPER, NO como Kokoro**, aunque en el código Kokoro ya es el motor por defecto (commits `3d57d5d` / `b7aa952`). Sospecha fuerte: **el deploy con Kokoro NO se aplicó de verdad** (build falló, redeploy no se completó, o el deployment activo no es el último commit).

Qué hacer (en orden):
1. En Railway → servicio **web** → **Deployments**: confirmar que el deployment **Active** corresponde al commit **`3d57d5d` o más nuevo** (no a uno viejo).
2. En **Deploy Logs / Build Logs** buscar:
   - Que el build **descargó Kokoro** sin error (líneas `curl` a `github.com/thewh1teagle/kokoro-onnx`), y que `pip install` instaló `kokoro-onnx` (puede tardar/pesar).
   - Al arrancar, las líneas: `[startup] kokoro modelo: /opt/kokoro/kokoro-v1.0.int8.onnx` y `[startup] kokoro voces: /opt/kokoro/voices-v1.0.bin` **sin "(NO ENCONTRADO)"**.
   - Si al generar un video aparece `>> Kokoro: cargando modelo...` y `>> Kokoro (gratis): generando voz...` → está usando Kokoro. Si aparece `>> Piper...` → NO está en Kokoro.
3. Posibles causas si NO es Kokoro:
   - **El build falló** al bajar el modelo o instalar `kokoro-onnx` y Railway dejó **activo un deployment anterior** (Piper). → Revisar Build Logs del intento más reciente; si falló, arreglar y redeployar.
   - **`TTS_ENGINE` está fijado a `piper`** en Variables de Railway (la env var tiene prioridad sobre el default del código). → Quitarla o ponerla en `kokoro`.
   - **Caché de build** sirvió una imagen vieja. → Forzar redeploy/rebuild.
   - **Posible peso/tiempo**: `kokoro-onnx` + onnxruntime + modelo ~115 MB pueden alargar el build; verificar que no se cortó por timeout/memoria.
4. Si Kokoro no arranca por algún error en el contenedor, como **plan B inmediato** se puede poner `TTS_ENGINE=piper` (con su fix de espeak ya aplicado) mientras se resuelve.

### PENDIENTE 1 — Animaciones (Rafa NO conforme) — EN EVALUACIÓN, NO implementado
Las animaciones gratis actuales (FFmpeg **Ken Burns** = zoom/paneo sobre **imagen fija** de Pollinations) se ven como **"diapositivas con movimiento"**, NO video real. A Rafa **no le convencen**. El video real era **fal.ai Vidu (de pago)**, que sigue disponible con `IMAGE_ENGINE=fal`.
- **Tarea próxima**: evaluar (investigación real, no de memoria) si existe una opción **GRATIS con más movimiento real** que el Ken Burns, **viable en Railway SIN GPU** y sin disparar costo/lentitud (p. ej. interpolación de frames, motion presets más ricos, animación procedural, modelos ligeros de image-to-video en CPU…). Ser honesto: probablemente el video IA real gratis en CPU NO sea viable.
- Si no hay opción gratis aceptable → **decidir con Rafa**: quedarse con las "diapositivas animadas" o **reactivar Vidu (de pago)** para video real.

### PENDIENTE 2 — Voz (Rafa NO conforme del todo) — decisión pendiente
La calidad de la **voz gratis** (Piper, y Kokoro cuando se confirme en deploy) **no terminó de convencer** a Rafa.
- **Tarea próxima**: una vez que Kokoro suene de verdad en Railway (Paso 0), que Rafa la escuche y **decida**: aceptar la voz gratis (Kokoro/Piper) o **volver a ElevenLabs (de pago)** con `TTS_ENGINE=elevenlabs` (requiere `ELEVENLABS_API_KEY`).

---

## 1. Resumen ejecutivo

- **Qué es la app**: generador automático de videos cortos (Reels/TikTok/Shorts/YouTube) que orquesta Claude (guion e ideas) + voz + imágenes + FFmpeg (animación, montaje y subtítulos). Frontend Streamlit con persistencia multi-cliente.
- **El sistema es GRATIS por defecto (en el código)**:
  - **Voz** → **Kokoro** (TTS local, gratis, **español latino**, más natural). ⚠️ Ver Paso 0: confirmar que está activo en el deploy.
  - **Imágenes** (escenas sin foto del usuario) → **Pollinations.ai** (gratis, sin llave) + animación **Ken Burns** (zoom/paneo sobre imagen fija → "diapositiva animada").
  - **Animación de imágenes propias del usuario** → **FFmpeg Ken Burns** (local, gratis).
  - **Único costo que queda**: la **API de Claude (Anthropic)**, que escribe los guiones (unos centavos por video).
- **Interfaz**: identidad visual de marca **"Péptidos y Suplementos (PyS)"** — tema oscuro con resplandores **turquesa `#00E5C4`** / **fucsia `#F7007A`**, tipografía Optima (títulos) + Inter (cuerpo), glassmorphism, botones píldora. Adornos/íconos de **VIDEO/MARKETING** (cámara, claqueta, play), NO de péptidos/salud. Responsive (móvil/escritorio).
- **Estado**: DESPLEGADA en Railway. Todo lo nuevo está **probado en LOCAL**. ⚠️ **Falta confirmar en el deploy** que Kokoro realmente esté sonando (Paso 0) y resolver las 2 insatisfacciones pendientes (animaciones y voz).

---

## 2. Interruptores (volver a opciones de pago sin tocar código)

Todo el código de ElevenLabs y fal sigue intacto. Se controla con variables de entorno en Railway (**la env var tiene prioridad** sobre el default del código y sobre el `config` del guion):

| Variable de entorno | Valores | Por defecto | Efecto |
|---|---|---|---|
| `TTS_ENGINE` | `kokoro` / `piper` / `elevenlabs` | `kokoro` | Voz. `kokoro`=gratis español latino; `piper`=gratis español de España; `elevenlabs`=de pago (requiere `ELEVENLABS_API_KEY`). |
| `IMAGE_ENGINE` | `pollinations` / `fal` | `pollinations` | Imágenes de escenas sin foto. `pollinations`=imagen gratis + Ken Burns; `fal`=**video real Vidu (de pago)**, requiere `FAL_KEY`. |

---

## 3. Lo que se hizo en ESTA sesión (con commits)

De más antiguo a más nuevo (rama `main`):

| Commit | Qué |
|---|---|
| `0b190ed` | **Animar imágenes con FFmpeg Ken Burns** (gratis), reemplaza el image-to-video de Vidu para las fotos del usuario. |
| `72ebd19` | **Subtítulos más pequeños** y discretos (FontSize 10→7, outline 1.4→1.0, MarginV 60→45). |
| `1e9d82b` | **Selector de formato** de video: vertical 9:16 / horizontal 16:9 / cuadrado 1:1. |
| `fff278f` | **Voz gratis con Piper** por defecto; ElevenLabs detrás del interruptor. |
| `b342bbe` | **Imágenes gratis con Pollinations** por defecto; fal Vidu detrás del interruptor. |
| `d117541` | **Ocultar del setting** las llaves de ElevenLabs y fal (código intacto; solo se muestra Claude). |
| `b661328` | **Rediseño visual PyS** (tema oscuro turquesa/fucsia, glassmorphism, íconos video/marketing, responsive) + `.streamlit/config.toml`. |
| `09cacbf` | **FIX Piper espeak**: pasar `--espeak_data` explícito; sin esto la voz sonaba "en otro idioma" en Railux/Linux (cwd ≠ carpeta del binario). |
| `3d57d5d` | **Kokoro como voz por defecto** (gratis, español latino, más natural). Piper/ElevenLabs quedan en el interruptor. |
| `b7aa952` | docs: HANDOFF con Kokoro + nota del fix de espeak. |

(Los `docs:` intermedios `d5361ed`, `91de90a`, `02e0435` actualizaron este HANDOFF en cada etapa.)

---

## 4. Arquitectura y stack

- **Frontend**: Streamlit (1.57.0) con identidad **PyS** (`_PYS_CSS` en `app.py` + `.streamlit/config.toml`). Sidebar con marca (logo SVG cámara/play), un **hero** por página con íconos de video, y 3 grupos (píldoras de color):
  - 🎬 **PRODUCIR** (turquesa) — Crear video, Usar mis imágenes
  - 💡 **IDEAS Y CLIENTES** (menta) — Ideas desde keywords, Repositorio / calendario
  - ⚙️ **SISTEMA** (fucsia) — Biblioteca de videos, Configuración (llaves)
  - Estilo vía CSS inyectado + tema nativo en `config.toml` (este recolorea toggle/slider que el CSS no alcanza). Responsive.
- **Backend**: Python 3.13. Deps: `anthropic`, `fal-client` (solo si se reactiva fal), `kokoro-onnx`+`soundfile`+`misaki-fork[en]` (voz Kokoro, **sin PyTorch**). ElevenLabs y Pollinations vía REST (`requests`). FFmpeg + ffprobe vía subprocess. **Kokoro** (modelo ONNX en `/opt/kokoro`), **Piper** (binario en `/opt/piper`).
- **Motores**:
  - **Claude** `claude-sonnet-4-6` (guiones e ideas). **(de pago, único costo)**
  - **Voz — Kokoro** (gratis, CPU, **POR DEFECTO**): TTS neuronal Apache-2.0 vía ONNX, **sin PyTorch**. Español **latino**, más natural que Piper. Catálogo chico (`generar.KOKORO_VOCES`): Femenina `ef_dora` (Dora·Latina), Masculina `em_alex` (Alex·Latino, **default**); se omite `em_santa` (temática). Modelo int8 (~88 MB) + voces (~27 MB) en `KOKORO_DIR` (`/opt/kokoro` deploy, `./kokoro` local). Fonética (espeak-ng) incluida en `espeakng-loader`. Carga única por corrida (singleton `_KOKORO`). `Kokoro(...).create(texto, voice, lang="es")` → 24 kHz → MP3.
  - **Voz — Piper** (gratis, respaldo `TTS_ENGINE=piper`): español de **España**. `generar.PIPER_VOCES`: Fem `es_ES-sharvard-medium` (Sara, speaker 1), `es_MX-claude-high` (Carla); Masc `es_ES-davefx-medium` (David), `es_MX-ald-medium` (Alberto). ⚠️ Requiere `--espeak_data` explícito (fix `09cacbf`). sharvard: M=0, F=1.
  - **Imágenes — Pollinations.ai** (gratis, sin llave): `https://image.pollinations.ai/prompt/{prompt}?width=&height=&model=flux&nologo=true&seed=`. Se pide al doble del tamaño para que el Ken Burns tenga resolución. Reintentos con espera (~1 img/15s). Resultado = **imagen fija** animada con Ken Burns ("diapositiva con movimiento", ver Pendiente 1).
  - **fal.ai Vidu Q3 Turbo** (respaldo de pago, `IMAGE_ENGINE=fal`): `fal-ai/vidu/q3/text-to-video/turbo` ($0.035/s). Es el **video real** que Rafa prefería visualmente.
- **Deploy**: Railway con **Dockerfile** propio. Puerto fijo **8080**, sin password.

---

## 5. Archivos del proyecto

| Archivo | Función |
|---|---|
| `app.py` | Frontend Streamlit. "Crear video": nº escenas, **selector de formato** (9:16/16:9/1:1), toggle subtítulos, **selector de voz por género** (según motor activo: por defecto voces Kokoro), expander para subir imágenes propias + logo. Costo muestra **"gratis"** por defecto. Página Configuración solo muestra la llave de Claude. Estilo PyS: `_PYS_CSS`, `_PYS_LOGO_SVG`/`_PYS_HERO_SVG`, `_inyectar_estilos_pys()`, `_hero_pys()`, `_pill()`. |
| `.streamlit/config.toml` | Tema nativo Streamlit PyS: `base="dark"`, `primaryColor="#00E5C4"`, fondos oscuros. |
| `make_video.py` | Pipeline. Por escena: **voz** (`generar_narracion()` → Kokoro default / Piper / ElevenLabs); **clip mudo**: foto del usuario → `generar_clip_kenburns()`; sin foto y `IMAGE_ENGINE=pollinations` → `generar_imagen_pollinations()`+Ken Burns; `=fal` → `generar_clip()` (Vidu). Voz: `generar_voz_kokoro()` (ONNX, singleton), `generar_voz_piper()` (`--espeak_data` explícito), `generar_voz()` (ElevenLabs). "La voz manda" (`-t voz_dur`+`tpad`). Persistencia `.trabajo_<output>/`. Diagnóstico de arranque imprime ffmpeg/ffprobe/piper/espeak/**kokoro**. `cargar_llaves()` no aborta si faltan ElevenLabs/fal. |
| `generar.py` | "Cerebro" Claude. `cargar_llaves()` (solo exige Anthropic), `pedir_guion_a_claude(..., aspect_ratio=)`, ideas/scripts, costos, catálogos `KOKORO_VOCES`+`PIPER_VOCES`+`FORMATOS`. `validar_guion()` omite voice_id de ElevenLabs si la voz es gratis. |
| `clientes.py` | Persistencia por cliente (keywords, ideas, scripts). Sin cambios recientes. |
| `Dockerfile` | `python:3.13-slim`; apt `ffmpeg curl ca-certificates libstdc++6 libgomp1 libsndfile1`; baja **Piper + 4 voces → /opt/piper** y **Kokoro int8 + voces → /opt/kokoro** (`KOKORO_DIR=/opt/kokoro`); `pip install` (incluye `kokoro-onnx`, sin PyTorch); `COPY . .`; `CMD` `unset STREAMLIT_*` + streamlit puerto 8080. |
| `railway.json` | Forza `builder: "DOCKERFILE"`. |
| `.dockerignore` / `.gitignore` | Excluyen `claves.txt`, `clientes/`, `.uploads/`, `.trabajo_*/`, `*.mp4`, **`piper/`**, **`kokoro/`**. |
| `requirements.txt` | `streamlit==1.57.0`, `anthropic==0.104.1`, `requests==2.34.2`, `pandas==2.2.3`, `openpyxl==3.1.5`, `fal-client==1.0.0`, `kokoro-onnx==0.5.0`, `soundfile==0.13.1`, `misaki-fork[en]`. |
| `CLAUDE.md` | Flujo CLI viejo. Parcialmente desactualizado (el real es Streamlit). |
| `prueba_fal.py` | Prueba standalone de fal (solo si se reactiva el pago). |
| `piper/`, `kokoro/` (local, gitignored) | Binario/modelos para pruebas locales. NO van al repo (se bajan en el build). |

---

## 6. Configuración de Railway

| Campo | Valor |
|---|---|
| Workspace / Proyecto / Servicio | **gabo6999-stack** (PRO) / **optimistic-enthusiasm** / **web** |
| URL | **videoagenterafa.up.railway.app** |
| Builder / Puerto | **DOCKERFILE** (vía `railway.json`) / **8080** |
| **Custom Start Command** | **VACÍO** — ⚠️ CRÍTICO: NO volver a llenarlo |
| Variables de entorno | `ANTHROPIC_API_KEY` (única **obligatoria**). `ELEVENLABS_API_KEY` / `FAL_KEY` opcionales (solo modo de pago). `TTS_ENGINE` / `IMAGE_ENGINE` opcionales (override de motor — **revisar en el Paso 0 que `TTS_ENGINE` no esté en `piper`**). |
| `APP_PASSWORD` | NO configurada (sin login). |
| Disco | **EFÍMERO**: lo generado se borra en cada redeploy/restart. |

---

## 7. Configuración de GitHub

- Cuenta/Org: **gabo6999-stack** · Repo: **gabo6999-stack/video-agente** (privado) · Rama: `main`.
- `gh` CLI 2.93.0 autenticado como `gabo6999-stack` (no requiere re-login para push).
- Identidad de commits: `Video Agente <enlace@grupoptm.com>`.

---

## 8. Funcionalidades implementadas

- **Crear video** (texto): describes el tema → Claude redacta guion + prompts → escenas con imágenes gratis (Pollinations) animadas con Ken Burns → voz Kokoro.
- **Usar mis imágenes**: subes 1 imagen por escena; se animan gratis con Ken Burns. Las escenas sin foto se completan con imágenes IA gratis.
- **Selector de formato**: 9:16 (default) / 16:9 / 1:1. Aplica a clips, Ken Burns y subtítulos.
- **Selector de voz por género**: por defecto voces Kokoro (Dora fem / Alex masc, latino); con `TTS_ENGINE=piper` muestra voces Piper (España).
- **Subtítulos** estilo Reels, pequeños (FontSize 7, outline 1.0, MarginV 45). Toggle ON por defecto.
- **Logo outro opcional** (PNG, cierre 2.5s sobre negro).
- **Ideas desde keywords** y **Repositorio / calendario** (por cliente).
- **Biblioteca de videos** (preview + descarga).
- **"La voz manda"** y **persistencia/reanudación** (`.trabajo_<slug>/`: `voz_N.mp3`, `imgia_N.png`, `clip_N.mp4`, `escena_N.mp4`).
- **Identidad visual PyS** (solo apariencia), responsive, verificada con capturas (escritorio + móvil).

---

## 9. Estado de pruebas

| Cosa | Estado |
|---|---|
| App arranca/renderiza (AppTest); selector muestra voces Kokoro | ✅ local |
| Voz Kokoro genera MP3 español latino + corrida 2 escenas → MP4 540×960 | ✅ local |
| Voz Piper con fix de espeak (fonemas español correctos) | ✅ local |
| Imágenes Pollinations + Ken Burns; 3 formatos con subtítulos | ✅ local |
| Config oculta ElevenLabs/fal, solo Claude | ✅ local |
| **Kokoro realmente activo y sonando en Railway** | ❌ **NO confirmado — Rafa oyó Piper. Ver Paso 0.** |
| **Calidad de voz aceptada por Rafa** | ⚠️ **Pendiente decisión (Pendiente 2)** |
| **Animaciones aceptadas por Rafa** | ❌ **No conforme — "diapositivas con movimiento" (Pendiente 1)** |

---

## 10. Filosofía y preferencias del usuario (Rafa, GrupoPTM)

- **Sin password** (equipo interno). No habilitar `APP_PASSWORD` salvo pedido explícito.
- **Sencillez sobre todo**: Rafa no es técnico. Mensajes claros, en español, sin jerga. Los errores deben decir qué hacer.
- **Costo siempre visible**; por defecto ahora **gratis**.
- **Trabajo progresivo**: un cambio a la vez, probarlo, commit+push individual. En cambios delicados (o no viables), **parar y avisar antes** de implementar.
- **Investigar de verdad** (no de memoria) antes de recomendar opciones técnicas; ser honesto con limitaciones.
- **Calidad cinematográfica** en prompts visuales; **sincronía** 14–16 palabras/escena (~6 s); en salud, cierre responsable.
- **Prioridad de audiencia: LATINOAMÉRICA** (por eso la voz debe ser español latino neutro).

---

## 11. Advertencias para el futuro

- ⚠️ **NUNCA llenar el *Custom Start Command*** en Railway (debe estar VACÍO).
- ⚠️ **`TTS_ENGINE` / `IMAGE_ENGINE` como env var TIENEN PRIORIDAD** sobre el default del código. Si la voz/imagen no es la esperada en producción, **revisar esas variables primero** (esto es candidato nº1 del Paso 0).
- ⚠️ **El build descarga Kokoro (GitHub `thewh1teagle/kokoro-onnx` model-files-v1.0), Piper (GitHub) y voces Piper (Hugging Face).** Si esas URLs caen, el build falla. (Verificadas vigentes 2026-05-30.)
- ⚠️ **Voz Kokoro**: español **latino**, catálogo chico (1 fem + 1 masc neutras); voces es "sin grado de calidad" oficial. Necesita `libsndfile1` (apt) para `soundfile`. Sin PyTorch.
- ⚠️ **Fix Piper espeak (`09cacbf`)**: si Piper suena "en otro idioma", revisar `--espeak_data` y `<PIPER_DIR>/espeak-ng-data`.
- ⚠️ **Pollinations** es servicio externo gratis best-effort (429/5xx posibles; reintentos ~16s). Las imágenes son **fijas** (Ken Burns = diapositiva animada). Para video real → `IMAGE_ENGINE=fal` (de pago).
- ⚠️ **NO borrar el código de ElevenLabs ni de fal** (`generar_voz()`, `generar_clip()`, etc.). Son los respaldos de pago.
- ⚠️ **Disco efímero en Railway**: descargar los MP4 al momento.
- ⚠️ **Builder forzado a DOCKERFILE**; si Railway cambia a Railpack/Nixpacks, rompe.
- ⚠️ **`piper/` y `kokoro/` locales** están gitignored/dockerignored. NO subirlos.

---

## Apéndice — Cómo retomar en una sesión nueva

### Claude Code en `C:\Users\Admin\Downloads\mi-videos\`:
1. Lee este archivo entero (sobre todo la **sección 0**).
2. `git log --oneline -15` (deberías ver `3d57d5d` / `b7aa952` o más nuevo).
3. Archivos clave: `app.py`, `make_video.py`, `generar.py`, `clientes.py`, `Dockerfile`.
4. Probar local: `streamlit run app.py` (necesita `claves.txt` con `ANTHROPIC_API_KEY` y `ffmpeg` en PATH). Voz **Kokoro** local: `pip install kokoro-onnx soundfile "misaki-fork[en]"` + descargar `kokoro-v1.0.int8.onnx` y `voices-v1.0.bin` en `./kokoro/`. Voz **Piper** local: binario Windows + una voz en `./piper/`.

### Llaves necesarias
- **Anthropic** (`sk-ant-api03-...`) — **obligatoria** (Claude).
- ElevenLabs / fal — **opcionales**, solo si se reactiva el modo de pago.
- Local: `claves.txt` (gitignored). Railway: Variables del servicio.
