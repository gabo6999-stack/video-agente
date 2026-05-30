# HANDOFF — Video Agente

Documento de continuidad. **Lee este archivo entero antes de tocar nada.**
Sirve para retomar el proyecto desde una sesión nueva de Claude Code o desde un chat nuevo de Claude web.

- Última actualización: 2026-05-30
- Último commit en `main`: **`b661328`** (`estilo: nueva interfaz con identidad de marca PyS (temática video/marketing), responsive`)
- URL pública activa: **https://videoagenterafa.up.railway.app**
- Repo: **https://github.com/gabo6999-stack/video-agente** (privado, rama `main`)

---

## 1. Resumen ejecutivo

- **Qué es la app**: generador automático de videos cortos (Reels/TikTok/Shorts/YouTube) que orquesta Claude (guion e ideas) + voz + imágenes + FFmpeg (animación, montaje y subtítulos). Frontend Streamlit con persistencia multi-cliente.
- **GRAN CAMBIO (2026-05-30): el sistema pasó a GRATIS por defecto.** Antes dependía de 3 APIs de pago (ElevenLabs voz + fal.ai Vidu video + Anthropic). Ahora:
  - **Voz** → **Piper** (TTS local, gratis). ElevenLabs queda como respaldo detrás de un interruptor.
  - **Imágenes** (escenas sin foto del usuario) → **Pollinations.ai** (gratis, sin llave) + animación Ken Burns. fal.ai Vidu queda como respaldo detrás de un interruptor.
  - **Animación de imágenes propias** → **FFmpeg Ken Burns** (local, gratis, ya estaba).
  - **Único costo que queda**: la **API de Claude (Anthropic)**, que escribe los guiones (unos centavos por video).
- **REDISEÑO VISUAL (2026-05-30): la interfaz ahora usa la identidad de marca "Péptidos y Suplementos (PyS)"** — fondo oscuro casi-negro con resplandores turquesa/fucsia, acento turquesa `#00E5C4` + secundario fucsia `#F7007A`, tipografía Optima (títulos) + Inter (cuerpo), tarjetas glassmorphism, botones tipo píldora. ⚠️ Los **adornos/íconos son de VIDEO/MARKETING** (cámara, claqueta, play), NO de péptidos/salud (es una herramienta de producción de video, no la tienda). Solo cambió la apariencia; la funcionalidad y el flujo son idénticos.
- **Estado**: DESPLEGADA en Railway. Todos los cambios nuevos están **probados en local** (incluida una corrida completa de 2 escenas: voz Piper + imágenes Pollinations + Ken Burns + subtítulos + montaje → MP4 9:16 correcto). **Falta validar en el deploy de Railway** (sobre todo: que el Dockerfile descargue bien Piper y que la calidad de voz/imágenes convenza).

---

## 2. Interruptores (cómo volver al modo de pago)

Todo el código de ElevenLabs y fal sigue intacto. Para reactivarlos, el equipo técnico pone variables de entorno en Railway (NO hace falta tocar código):

| Variable de entorno | Valores | Por defecto | Efecto |
|---|---|---|---|
| `TTS_ENGINE` | `piper` / `elevenlabs` | `piper` | Motor de voz. `elevenlabs` requiere `ELEVENLABS_API_KEY`. |
| `IMAGE_ENGINE` | `pollinations` / `fal` | `pollinations` | Imágenes de escenas sin foto. `fal` (video real Vidu) requiere `FAL_KEY`. |

También se pueden fijar por video en el `config` del `guion.json` (`tts_engine`, `image_engine`), pero la variable de entorno **tiene prioridad**.

---

## 3. Arquitectura y stack

- **Frontend**: Streamlit (1.57.0) con **identidad visual PyS** (tema oscuro + acento turquesa, glassmorphism, tipografía Optima/Inter, botones píldora; ver `_PYS_CSS` en `app.py` y `.streamlit/config.toml`). Sidebar con marca (logo SVG cámara/play), un **hero** por página con íconos de video, y 3 grupos (píldoras de color de marca: turquesa / menta / fucsia):
  - 🎬 **PRODUCIR** (turquesa `#00E5C4`) — Crear video, Usar mis imágenes
  - 💡 **IDEAS Y CLIENTES** (menta `#8EF3E4`) — Ideas desde keywords, Repositorio / calendario
  - ⚙️ **SISTEMA** (fucsia `#F7007A`) — Biblioteca de videos, Configuración (llaves)
  - Cabecera del sidebar: si la voz es Piper (default) muestra "Voz e imágenes: gratis ✓"; solo muestra saldo de ElevenLabs si `TTS_ENGINE=elevenlabs`.
  - **Estilo aplicado vía CSS inyectado** (`st.markdown(unsafe_allow_html=True)`) + tema nativo en `.streamlit/config.toml`. Responsive (móvil/escritorio). Componente que Streamlit no recolorea bien por CSS: el toggle/slider — resuelto con `primaryColor` en el config.toml.
- **Backend**: Python 3.13. SDKs: `anthropic`, `fal-client` (solo si se reactiva fal). ElevenLabs y Pollinations vía REST (`requests`). FFmpeg + ffprobe vía subprocess. **Piper** vía subprocess (binario en `/opt/piper`).
- **Motores por defecto**:
  - **Claude**: `claude-sonnet-4-6` para guiones e ideas. Caching ephemeral sobre el system prompt. **(de pago, único costo)**
  - **Voz — Piper** (gratis, local, CPU): catálogo curado de 4 voces neutras en español (ver `generar.PIPER_VOCES`):
    - Femeninas: `es_ES-sharvard-medium` (Sara·España, speaker 1), `es_MX-claude-high` (Carla·México)
    - Masculinas: `es_ES-davefx-medium` (David·España, **default**), `es_MX-ald-medium` (Alberto·México)
    - El usuario solo ESCOGE la voz en "Crear video" (separadas femeninas/masculinas). No se "educa" por texto.
  - **Imágenes — Pollinations.ai** (gratis, sin llave): `https://image.pollinations.ai/prompt/{prompt}?width=&height=&model=flux&nologo=true&seed=`. Se pide al doble del tamaño de salida para que el Ken Burns tenga resolución. Reintentos con espera (límite ~1 img/15s).
  - **fal.ai Vidu Q3 Turbo** (respaldo de pago): `fal-ai/vidu/q3/text-to-video/turbo` ($0.035/s). Solo si `IMAGE_ENGINE=fal`.
- **Deploy**: Railway con **Dockerfile** propio. Puerto fijo **8080**, sin password.

---

## 4. Archivos del proyecto

### Código y configuración activos

| Archivo | Función |
|---|---|
| `app.py` | Frontend Streamlit. "Crear video" tiene: nº escenas, **selector de formato** (9:16 / 16:9 / 1:1), toggle subtítulos, **selector de voz Piper** (femeninas/masculinas), expander para subir imágenes propias + logo. Cálculo de costo que muestra **"gratis"** por defecto. Orquesta `generar.py` y `make_video.py`. Página Configuración solo muestra la llave de Claude. **Estilo PyS**: constantes `_PYS_CSS` (CSS de marca), `_PYS_LOGO_SVG`/`_PYS_HERO_SVG` (íconos video), `_inyectar_estilos_pys()`, `_hero_pys()`, `_pill()` (chips de sección). **Toda la lógica/flujo intactos; solo apariencia.** |
| `.streamlit/config.toml` | Tema nativo de Streamlit con la marca PyS: `base="dark"`, `primaryColor="#00E5C4"` (turquesa), fondos oscuros. Recolorea los componentes que el CSS no alcanza (toggle, slider, foco de inputs). |
| `make_video.py` | Pipeline core. Por escena: **voz** (`generar_narracion()` → Piper por defecto / ElevenLabs); **clip mudo**: si hay foto del usuario → `generar_clip_kenburns()`; si no y `IMAGE_ENGINE=pollinations` → `generar_imagen_pollinations()` + Ken Burns; si `=fal` → `generar_clip()` (Vidu). Monta respetando "la voz manda" (`-t voz_dur` + `tpad`). Persistencia en `.trabajo_<output>/` con reanudación (voz, imagen IA `imgia_N.png`, clip y escena se reutilizan si son válidos). Outro opcional con logo. Subtítulos pequeños. `cargar_llaves()` ya NO aborta si faltan ElevenLabs/fal. |
| `generar.py` | "Cerebro" Claude API. `cargar_llaves()` (solo exige Anthropic), `obtener_voces_elevenlabs()`, `pedir_guion_a_claude(..., aspect_ratio=)` (acepta formato, fuerza aspect_ratio en el config), `proponer_ideas()`, `generar_script_para_idea()`, `calcular_costo()`, `calcular_costo_mixto()`, catálogo `PIPER_VOCES` + `FORMATOS`. `validar_guion()` omite el voice_id de ElevenLabs cuando se usa Piper. |
| `clientes.py` | Persistencia por cliente (keywords, ideas, scripts). Sin cambios recientes. |
| `Dockerfile` | `FROM python:3.13-slim`, instala `ffmpeg curl ca-certificates libstdc++6 libgomp1`, **descarga el binario Piper + 4 voces es a `/opt/piper`** (env `PIPER_DIR=/opt/piper`, `LD_LIBRARY_PATH=/opt/piper`), pip install, `COPY . .`, `CMD` con `unset STREAMLIT_*` + streamlit en puerto 8080. |
| `railway.json` | Forza `builder: "DOCKERFILE"`. |
| `.dockerignore` / `.gitignore` | Excluyen `claves.txt`, `clientes/`, `.uploads/`, `.trabajo_*/`, `*.mp4`, y **`piper/`** (binario+voces locales ~90 MB; en el deploy se bajan al build). |
| `requirements.txt` | `streamlit==1.57.0`, `anthropic==0.104.1`, `requests==2.34.2`, `pandas==2.2.3`, `openpyxl==3.1.5`, `fal-client==1.0.0`. |
| `CLAUDE.md` | Instrucciones del flujo CLI viejo. **Parcialmente desactualizado** (el flujo real es Streamlit). |

### Secundarios
| Archivo | Función |
|---|---|
| `prueba_fal.py` | Prueba standalone de fal (solo útil si se reactiva el modo de pago). |
| `piper/` (local, gitignored) | Binario Piper Windows + voces para pruebas locales. NO va al repo. |
| `nixpacks.toml.bak`, `Procfile.bak` | Configs muertas. No se usan. |

---

## 5. Configuración de Railway

| Campo | Valor |
|---|---|
| Workspace | **gabo6999-stack** (plan PRO) |
| Proyecto | **optimistic-enthusiasm** |
| Servicio | **web** · URL **videoagenterafa.up.railway.app** |
| Builder | **DOCKERFILE** (forzado vía `railway.json`) · Puerto **8080** |
| **Custom Start Command** | **VACÍO** — ⚠️ CRÍTICO: NO volver a llenarlo |
| Variables de entorno | `ANTHROPIC_API_KEY` (única **obligatoria**). `ELEVENLABS_API_KEY` y `FAL_KEY` ahora son OPCIONALES (solo si se reactiva el modo de pago con `TTS_ENGINE`/`IMAGE_ENGINE`). |
| `APP_PASSWORD` | NO configurada (sin login). |
| Disco | **EFÍMERO**: todo lo generado se borra en cada redeploy/restart. |

---

## 6. Configuración de GitHub

- Cuenta/Org: **gabo6999-stack** · Repo: **gabo6999-stack/video-agente** (privado) · Rama: `main`
- `gh` CLI 2.93.0 autenticado como `gabo6999-stack` (no requiere re-login para push).
- Identidad de commits del repo: `Video Agente <enlace@grupoptm.com>` (configurada en el repo).

---

## 7. Funcionalidades implementadas

- **Crear video** (texto): describes el tema, Claude redacta guion y prompts visuales; las escenas se generan con imágenes gratis (Pollinations) animadas con Ken Burns; voz Piper.
- **Usar mis imágenes**: subes 1 imagen por escena; se animan GRATIS con Ken Burns (zoom/paneo variado por escena). Las escenas sin foto se completan con imágenes IA gratis.
- **Selector de formato**: Vertical 9:16 (default), Horizontal 16:9 (YouTube), Cuadrado 1:1. Se respeta en clips, Ken Burns y subtítulos.
- **Selector de voz** (Piper): femeninas / masculinas, neutras. El usuario elige.
- **Subtítulos** estilo Reels, **pequeños** (FontSize 7, outline 1.0, MarginV 45) — no tapan el centro. Toggle ON por defecto.
- **Logo outro opcional**: PNG como cierre de 2.5s sobre negro.
- **"Ideas desde keywords"** y **Repositorio / calendario**: por cliente, igual que antes.
- **Biblioteca de videos**: lista los .mp4 con preview y descarga.
- **"La voz manda"**: `voz_dur` define la duración de cada escena (`-t voz_dur` + `tpad`).
- **Persistencia y reanudación**: `.trabajo_<slug>/` guarda `voz_N.mp3`, `imgia_N.png`, `clip_N.mp4`, `escena_N.mp4`. Si algo falla, lo bueno se conserva y se reintenta solo lo que falta. (Útil con Pollinations: la imagen IA se reutiliza y no se vuelve a pedir.)
- **Identidad visual PyS** (solo apariencia): tema oscuro con resplandores turquesa/fucsia, glassmorphism, tipografía Optima/Inter, botones píldora, marca + hero con íconos de video/marketing. Responsive. Verificado con capturas reales (escritorio y móvil). El único componente que Streamlit no recolorea por CSS (toggle/slider) se resolvió con `primaryColor` en `.streamlit/config.toml`.

---

## 8. Estado de pruebas

| Cosa | Estado |
|---|---|
| App arranca/renderiza (probado con `streamlit.testing` AppTest) | ✅ local |
| Voz Piper genera MP3, "la voz manda" | ✅ local |
| Imágenes Pollinations en vivo + Ken Burns | ✅ local |
| Los 3 formatos (9:16/16:9/1:1) con subtítulos | ✅ local |
| **Corrida completa 2 escenas (Piper+Pollinations+KenBurns+subs+montaje)** | ✅ local → MP4 540×960, 7.6s |
| Config oculta ElevenLabs/fal, solo muestra Claude | ✅ local |
| **Dockerfile baja Piper+voces en Railway** | ⚠️ **PENDIENTE validar en el deploy** |
| **Calidad real de voz Piper y de imágenes Pollinations** | ⚠️ **PENDIENTE oír/ver en producción** |

---

## 9. Siguiente paso inmediato

1. Hacer **redeploy en Railway** (el push ya está en `main`). Vigilar en **Deploy Logs** que el build descargue Piper + las 4 voces sin error (líneas de `curl` a github/huggingface) y que aparezcan los `[startup] ffmpeg/ffprobe`.
2. Abrir la app → **Crear video** → tema corto, 3 escenas → el botón debe decir **"gratis"** → Generar.
3. Validar: que la **voz Piper** suene bien, que las **imágenes Pollinations** sean aceptables, que el formato/subtítulos estén ok. **Descargar el MP4 antes de cerrar** (disco efímero).
4. Si la voz/imagen no convencen: se puede cambiar la voz Piper por defecto, o reactivar el modo de pago con `TTS_ENGINE`/`IMAGE_ENGINE`.

---

## 10. Filosofía y preferencias del usuario (Rafa, GrupoPTM)

- **Sin password** (equipo interno). No habilitar `APP_PASSWORD` salvo pedido explícito.
- **Sencillez sobre todo**: Rafa no es técnico. Mensajes claros, en español, sin jerga. Los errores deben decir qué hacer.
- **Costo siempre visible** antes de generar. Ahora por defecto: **gratis**.
- **Trabajo progresivo**: un cambio a la vez, probarlo, commit+push individual. En cambios delicados, parar y avisar antes.
- **Calidad cinematográfica** en los prompts visuales (evitar manos/textos/rostros hablando en primer plano; cierre técnico realista; paleta consistente).
- **Sincronía**: 14–16 palabras por escena (~6s de voz).
- **Salud**: cierre responsable, sin promesas médicas.

---

## 11. Advertencias para el futuro

- ⚠️ **NUNCA llenar el *Custom Start Command*** en Railway (debe estar VACÍO).
- ⚠️ **El build descarga Piper desde GitHub releases y las voces desde Hugging Face.** Si esas URLs cambian o caen, el build falla. URLs en el `Dockerfile`. (Verificadas vigentes el 2026-05-30.)
- ⚠️ **Pollinations es un servicio externo gratis best-effort**: puede ir lento o devolver 429/5xx. Hay reintentos con espera (~16s). Si falla mucho, reactivar fal (`IMAGE_ENGINE=fal`) o cambiar de proveedor.
- ⚠️ **Calidad**: Piper es bueno pero un escalón debajo de ElevenLabs; las imágenes Pollinations son menores que el video real de Vidu (son imagen fija animada). Es el trade-off por ser gratis (decisión del equipo).
- ⚠️ **NO borrar el código de ElevenLabs ni de fal** ni las funciones `generar_voz()`, `generar_clip()`, etc. Son el respaldo de pago detrás de los interruptores.
- ⚠️ **Disco efímero en Railway**: lo generado se pierde en cada redeploy/restart. Descargar los MP4 al momento.
- ⚠️ **Builder forzado a DOCKERFILE** (`railway.json`). Si Railway cambia a Railpack/Nixpacks, rompe.
- ⚠️ **`piper/` local (~90 MB)** está gitignored y dockerignored. NO subirlo.

---

## Apéndice — Cómo retomar en una sesión nueva

### Claude Code en `C:\Users\Admin\Downloads\mi-videos\`:
1. Lee este archivo entero.
2. `git log --oneline -10` (deberías ver `d117541` o más nuevo).
3. Archivos clave: `app.py`, `make_video.py`, `generar.py`, `clientes.py`, `Dockerfile`.
4. Probar local: `streamlit run app.py` (necesita `claves.txt` con `ANTHROPIC_API_KEY` y `ffmpeg` en PATH; para voz Piper en local, descargar el binario Windows + una voz en `./piper/`).

### Llaves necesarias
- **Anthropic** (`sk-ant-api03-...`) — **obligatoria** (Claude).
- ElevenLabs / fal — **opcionales**, solo si se reactiva el modo de pago.
- Local: `claves.txt` (gitignored). Railway: Variables del servicio.
