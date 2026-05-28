#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  AUTO-VIDEO  -  Script -> Voz (ElevenLabs) + Clips (fal / Vidu Q3) -> Video MP4
================================================================================

QUE HACE:
  Lee un guion (guion.json). Por cada escena:
    1. Genera la narracion con ElevenLabs.
    2. Genera el clip MUDO con fal.ai (Vidu Q3 Turbo), con hasta 3 reintentos.
    3. Ajusta el clip a la voz (la voz es el unico audio).
  Al final concatena todo y quema subtitulos.

PERSISTENCIA + REANUDACION:
  Cada escena se guarda en .trabajo_<nombre_output>/. Si una escena (o su
  voz / clip intermedio) ya existe de una corrida anterior, se reutiliza.
  La carpeta NO se borra si algo falla; solo se borra cuando el video final
  se genera con exito.

LLAVES:
  Se leen primero de las variables de entorno y si faltan, de claves.txt.
  Acepta FAL_KEY, FAL_API_KEY o FAI_API_KEY como nombres equivalentes.

USO:
    python make_video.py guion.json
================================================================================
"""

import os
import re
import sys
import json
import time
import glob
import subprocess
import shutil
import requests


def _ensure_ffmpeg_on_path():
    """Asegura que ffmpeg Y ffprobe sean encontrables.
    - Linux/Railway: si ffmpeg esta y ffprobe no, busca ffprobe en la misma carpeta.
    - Windows post-winget: si ninguno esta, intenta la carpeta de winget.
    """
    have_ffmpeg  = shutil.which("ffmpeg")
    have_ffprobe = shutil.which("ffprobe")
    if have_ffmpeg and have_ffprobe:
        return

    # Caso comun en imagenes Linux: ffmpeg esta en PATH pero ffprobe no
    # (o viceversa). Ambos suelen vivir en la misma carpeta.
    if have_ffmpeg and not have_ffprobe:
        bin_dir = os.path.dirname(have_ffmpeg)
        for nombre in ("ffprobe", "ffprobe.exe"):
            if os.path.exists(os.path.join(bin_dir, nombre)):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return

    # Fallback Windows winget
    patrones = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_*\ffmpeg-*\bin"),
    ]
    for pat in patrones:
        for d in glob.glob(pat):
            if os.path.exists(os.path.join(d, "ffmpeg.exe")):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                return


_ensure_ffmpeg_on_path()

# Diagnostico al arrancar el subprocess (queda en log de Railway via streamlit)
for _name in ("ffmpeg", "ffprobe"):
    _p = shutil.which(_name)
    print(f"[make_video startup] {_name}: {_p or '(NO ENCONTRADO)'}", flush=True)


def _bin(name):
    """Resuelve el path absoluto de un binario externo (ffmpeg/ffprobe) usando
    PATH. Si no se encuentra, devuelve el nombre simple como fallback."""
    return shutil.which(name) or name


# ==============================================================================
#  CONFIGURACION  (cambia aqui los valores por defecto si quieres)
# ==============================================================================
CONFIG = {
    # --- fal.ai (clips MUDOS) ---
    "fal_model":         "fal-ai/vidu/q3/text-to-video/turbo",   # text-to-video
    "fal_model_i2v":     "fal-ai/vidu/q3/image-to-video",        # image-to-video (sin turbo)
    "fal_resolution":    "540p",  # "360p"|"540p"|"720p"|"1080p" (720p+ cuesta 2.2x)
    "aspect_ratio":      "9:16",  # "16:9"|"9:16"|"4:3"|"3:4"|"1:1" (solo aplica a t2v)

    # --- Outro con logo ---
    "outro_seconds":     2.5,     # duracion de la pantalla final con logo
    "outro_bg_color":    "black", # fondo de la pantalla final
    "outro_logo_scale":  0.6,     # logo ocupa este % del ancho del video

    # --- ElevenLabs (voz) ---
    "voice_id":         "TxGEqnHWrfWFTfGW9XjX",
    "tts_model":        "eleven_multilingual_v2",
    "voice_stability":   0.40,
    "voice_similarity":  0.75,
    "voice_style":       0.0,

    # --- Subtitulos (estilo Reels/TikTok elegante) ---
    "burn_subtitles":   True,
    "sub_fontname":     "Arial",
    "sub_fontsize":     10,
    "sub_bold":         1,
    "sub_outline":      1.4,    # grosor del borde negro (sutil pero legible)
    "sub_margin_v":     60,     # margen comodo desde el borde inferior
    "sub_margin_h":     40,     # margen lateral (fuerza wrap antes del borde)
    "sub_max_chars":    44,     # corte por linea para garantizar maximo 2 lineas

    # --- General ---
    "max_clip_seconds":    6,    # default del sistema: clips cortos de ~6s (Vidu Q3 soporta hasta 16)
    "poll_interval":       5,    # segundos entre consultas de estado a fal
    "poll_timeout":      300,    # segundos maximo POR INTENTO
    "fal_max_intentos":    3,    # reintentos por clip antes de marcar la escena fallida
    "output_file":      "video_final.mp4",
}

ELEVEN_KEY = None
FAL_KEY = None

ELEVEN_BASE = "https://api.elevenlabs.io/v1"


# ==============================================================================
#  UTILIDADES
# ==============================================================================
def log(msg):
    print(f"  >> {msg}", flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Comando fallo:\n{' '.join(cmd)}\n\n{r.stderr[-1500:]}")
    return r.stdout


def media_duration(path):
    """Duracion en segundos. Prefiere ffprobe (rapido, limpio).
    Fallback: parsea la salida de 'ffmpeg -i' por si ffprobe no esta disponible
    (caso visto en algunas imagenes de Railway/Nixpacks)."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        out = run([ffprobe, "-v", "quiet", "-show_entries", "format=duration",
                   "-of", "csv=p=0", path])
        try:
            return float(out.strip())
        except ValueError:
            pass  # cae al fallback de abajo
    # Fallback: ffmpeg -i <path>; ffmpeg escribe info a stderr aunque no haya
    # output, y dentro encontramos "Duration: HH:MM:SS.ss".
    ffmpeg = _bin("ffmpeg")
    r = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    blob = (r.stderr or "") + "\n" + (r.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", blob)
    if not m:
        raise RuntimeError(
            f"No pude obtener duracion de '{path}' (ni ffprobe ni ffmpeg -i la entregaron).\n"
            f"--- ffmpeg salida (recortada) ---\n{blob[:800]}"
        )
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def fmt_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ==============================================================================
#  CARGA DE LLAVES (env vars primero, despues claves.txt)
# ==============================================================================
_FAL_ALIASES = ("FAL_KEY", "FAL_API_KEY", "FAI_API_KEY")


def _leer_claves_txt():
    """Devuelve dict {nombre: valor} de claves.txt si existe."""
    candidatos = [
        "claves.txt",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "claves.txt"),
    ]
    claves_path = next((p for p in candidatos if os.path.exists(p)), None)
    if not claves_path:
        return {}
    out = {}
    with open(claves_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cargar_llaves():
    archivo = _leer_claves_txt()
    eleven = os.environ.get("ELEVENLABS_API_KEY") or archivo.get("ELEVENLABS_API_KEY")
    fal = None
    for alias in _FAL_ALIASES:
        fal = os.environ.get(alias) or archivo.get(alias)
        if fal:
            break
    if not eleven:
        sys.exit("ERROR: falta ELEVENLABS_API_KEY (env o claves.txt)")
    if not fal:
        sys.exit("ERROR: falta FAL_KEY/FAL_API_KEY/FAI_API_KEY (env o claves.txt)")
    # fal_client lee FAL_KEY de env; lo seteamos para que la libreria lo encuentre
    os.environ["FAL_KEY"] = fal
    return eleven, fal


# ==============================================================================
#  ELEVENLABS  ->  MP3 de narracion
# ==============================================================================
def generar_voz(texto, salida_mp3):
    log(f"ElevenLabs: generando voz ({len(texto)} caracteres)...")
    url = f"{ELEVEN_BASE}/text-to-speech/{CONFIG['voice_id']}"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": texto,
        "model_id": CONFIG["tts_model"],
        "voice_settings": {
            "stability": CONFIG["voice_stability"],
            "similarity_boost": CONFIG["voice_similarity"],
            "style": CONFIG["voice_style"],
            "use_speaker_boost": True,
        },
    }
    r = requests.post(url, headers=headers, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:400]}")
    with open(salida_mp3, "wb") as f:
        f.write(r.content)
    dur = media_duration(salida_mp3)
    log(f"ElevenLabs: voz lista ({dur:.1f}s)")
    return dur


# ==============================================================================
#  FAL (Vidu Q3 Turbo)  ->  un solo intento
# ==============================================================================
class CreditosInsuficientes(Exception):
    pass


def _es_error_creditos(mensaje):
    m = (mensaje or "").lower()
    return any(p in m for p in ("credit", "balance", "spending limit", "quota",
                                "billing", "402", "insufficient"))


def _pedir_clip_una_vez(prompt, dur, salida_mp4):
    """Hace UN intento contra fal Vidu Q3 Turbo. Lanza si timeout o falla."""
    import fal_client  # se importa aqui para evitar costo de import si solo se reutilizan

    arguments = {
        "prompt": prompt,
        "duration": int(dur),
        "resolution": CONFIG["fal_resolution"],
        "aspect_ratio": CONFIG["aspect_ratio"],
        "audio": False,
    }
    log(f"fal {CONFIG['fal_model']}: encolando clip {dur}s {CONFIG['fal_resolution']} {CONFIG['aspect_ratio']}...")

    _ult_log = [0.0]
    _t0 = time.monotonic()

    def _on_update(status):
        nombre = type(status).__name__
        ahora = time.monotonic()
        # Limito a un log cada 15s para no spamear con InProgress
        if ahora - _ult_log[0] < 15 and nombre == "InProgress":
            return
        _ult_log[0] = ahora
        seg = int(ahora - _t0)
        if nombre == "Queued":
            pos = getattr(status, "position", "?")
            log(f"   ... status=Queued (pos={pos}, {seg}s)")
        else:
            log(f"   ... status={nombre} ({seg}s)")

    try:
        result = fal_client.subscribe(
            CONFIG["fal_model"],
            arguments=arguments,
            with_logs=False,
            on_queue_update=_on_update,
            client_timeout=CONFIG["poll_timeout"],
        )
    except fal_client.FalClientTimeoutError as e:
        raise RuntimeError(f"fal: timeout {CONFIG['poll_timeout']}s esperando el clip.") from e
    except fal_client.FalClientHTTPError as e:
        if _es_error_creditos(str(e)):
            raise CreditosInsuficientes(f"fal sin creditos: {str(e)[:300]}") from e
        raise RuntimeError(f"fal HTTP error: {str(e)[:300]}") from e
    except Exception as e:
        if _es_error_creditos(str(e)):
            raise CreditosInsuficientes(f"fal sin creditos: {str(e)[:300]}") from e
        raise

    video_url = (result or {}).get("video", {}).get("url")
    if not video_url:
        raise RuntimeError(f"fal: respuesta sin video.url: {str(result)[:300]}")

    log("fal: descargando clip...")
    vid = requests.get(video_url, timeout=120)
    if vid.status_code != 200:
        raise RuntimeError(f"fal: descarga fallo {vid.status_code}")
    with open(salida_mp4, "wb") as f:
        f.write(vid.content)
    log("fal: clip listo.")


# ==============================================================================
#  FAL  ->  con reintentos (texto-a-video)
# ==============================================================================
def generar_clip(prompt, segundos, salida_mp4):
    dur = min(CONFIG["max_clip_seconds"], max(2, int(segundos) + 1))
    log(f"fal t2v: pidiendo clip de {dur}s...")

    max_intentos = CONFIG["fal_max_intentos"]
    ultimo_error = None
    for intento in range(1, max_intentos + 1):
        try:
            _pedir_clip_una_vez(prompt, dur, salida_mp4)
            return
        except CreditosInsuficientes:
            raise
        except Exception as e:
            ultimo_error = e
            if intento < max_intentos:
                log(f"Intento {intento}/{max_intentos} fallo ({e}). Reintentando...")
                time.sleep(3)
    raise RuntimeError(f"fal agoto {max_intentos} intentos. Ultimo error: {ultimo_error}")


# ==============================================================================
#  FAL  ->  IMAGEN A VIDEO (un solo intento)
# ==============================================================================
def _pedir_clip_i2v_una_vez(image_path, prompt, dur, salida_mp4):
    """Sube la imagen a fal, llama al modelo image-to-video, descarga MP4."""
    import fal_client

    if not os.path.exists(image_path):
        raise RuntimeError(f"Imagen local no existe: {image_path}")

    log(f"fal i2v: subiendo imagen {os.path.basename(image_path)}...")
    try:
        image_url = fal_client.upload_file(image_path)
    except Exception as e:
        if _es_error_creditos(str(e)):
            raise CreditosInsuficientes(f"fal upload sin creditos: {e}") from e
        raise RuntimeError(f"fal upload fallo: {e}") from e

    arguments = {
        "image_url": image_url,
        "prompt": prompt or "",
        "duration": int(dur),
        "resolution": CONFIG["fal_resolution"],
        "audio": False,
    }
    log(f"fal i2v: encolando clip {dur}s {CONFIG['fal_resolution']}...")

    _ult_log = [0.0]
    _t0 = time.monotonic()

    def _on_update(status):
        nombre = type(status).__name__
        ahora = time.monotonic()
        if ahora - _ult_log[0] < 15 and nombre == "InProgress":
            return
        _ult_log[0] = ahora
        seg = int(ahora - _t0)
        if nombre == "Queued":
            pos = getattr(status, "position", "?")
            log(f"   ... status=Queued (pos={pos}, {seg}s)")
        else:
            log(f"   ... status={nombre} ({seg}s)")

    try:
        result = fal_client.subscribe(
            CONFIG["fal_model_i2v"],
            arguments=arguments,
            with_logs=False,
            on_queue_update=_on_update,
            client_timeout=CONFIG["poll_timeout"],
        )
    except fal_client.FalClientTimeoutError as e:
        raise RuntimeError(f"fal i2v: timeout {CONFIG['poll_timeout']}s.") from e
    except fal_client.FalClientHTTPError as e:
        if _es_error_creditos(str(e)):
            raise CreditosInsuficientes(f"fal i2v sin creditos: {str(e)[:300]}") from e
        raise RuntimeError(f"fal i2v HTTP error: {str(e)[:300]}") from e
    except Exception as e:
        if _es_error_creditos(str(e)):
            raise CreditosInsuficientes(f"fal i2v sin creditos: {str(e)[:300]}") from e
        raise

    video_url = (result or {}).get("video", {}).get("url")
    if not video_url:
        raise RuntimeError(f"fal i2v: respuesta sin video.url: {str(result)[:300]}")

    log("fal i2v: descargando clip...")
    vid = requests.get(video_url, timeout=120)
    if vid.status_code != 200:
        raise RuntimeError(f"fal i2v: descarga fallo {vid.status_code}")
    with open(salida_mp4, "wb") as f:
        f.write(vid.content)
    log("fal i2v: clip listo.")


def generar_clip_i2v(image_path, prompt, segundos, salida_mp4):
    """Image-to-video con reintentos (misma estrategia que t2v)."""
    dur = min(CONFIG["max_clip_seconds"], max(2, int(segundos) + 1))
    log(f"fal i2v: pidiendo clip de {dur}s sobre imagen del usuario...")

    max_intentos = CONFIG["fal_max_intentos"]
    ultimo_error = None
    for intento in range(1, max_intentos + 1):
        try:
            _pedir_clip_i2v_una_vez(image_path, prompt, dur, salida_mp4)
            return
        except CreditosInsuficientes:
            raise
        except Exception as e:
            ultimo_error = e
            if intento < max_intentos:
                log(f"Intento i2v {intento}/{max_intentos} fallo ({e}). Reintentando...")
                time.sleep(3)
    raise RuntimeError(f"fal i2v agoto {max_intentos} intentos. Ultimo error: {ultimo_error}")


# ==============================================================================
#  COMPONER ESCENA  ->  sincroniza clip mudo + voz
# ==============================================================================
def componer_escena(clip_mp4, voz_mp3, voz_dur, salida_mp4):
    log("Montando escena (clip + voz)...")
    clip_dur = media_duration(clip_mp4)

    vfilter = (
        f"[0:v]tpad=stop_mode=clone:stop_duration={max(0, voz_dur - clip_dur):.2f},"
        f"trim=duration={voz_dur:.2f},setpts=PTS-STARTPTS[v0]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_mp4,
        "-i", voz_mp3,
        "-filter_complex", vfilter,
        "-map", "[v0]",
        "-map", "1:a",
        "-t", f"{voz_dur:.2f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        salida_mp4,
    ]
    run(cmd)
    log("Escena montada.")


# ==============================================================================
#  REANUDACION  ->  reusa archivos validos de corridas anteriores
# ==============================================================================
def _es_media_valido(path):
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    try:
        return media_duration(path) > 0.1
    except Exception:
        return False


def procesar_escena(idx, esc, work):
    voz_mp3   = os.path.join(work, f"voz_{idx}.mp3")
    clip_mp4  = os.path.join(work, f"clip_{idx}.mp4")
    esc_mp4   = os.path.join(work, f"escena_{idx}.mp4")

    # REANUDACION: si la escena ya esta montada y valida, la reutilizo entera
    if _es_media_valido(esc_mp4):
        voz_dur = media_duration(esc_mp4)
        log(f"REANUDACION: escena {idx} ya estaba montada, la reutilizo.")
        return esc_mp4, voz_dur

    # Voz: reutilizar si vale, regenerar si no
    if _es_media_valido(voz_mp3):
        voz_dur = media_duration(voz_mp3)
        log(f"REANUDACION: voz {idx} ya existia, la reutilizo.")
    else:
        if os.path.exists(voz_mp3):
            os.remove(voz_mp3)
        voz_dur = generar_voz(esc["narracion"], voz_mp3)

    # Clip: reutilizar si vale, pedir a fal si no
    if _es_media_valido(clip_mp4):
        log(f"REANUDACION: clip {idx} ya existia, lo reutilizo.")
    else:
        if os.path.exists(clip_mp4):
            os.remove(clip_mp4)
        imagen_local = esc.get("imagen_local")
        if imagen_local and os.path.exists(imagen_local):
            generar_clip_i2v(imagen_local, esc["visual"], voz_dur, clip_mp4)
        else:
            generar_clip(esc["visual"], voz_dur, clip_mp4)

    componer_escena(clip_mp4, voz_mp3, voz_dur, esc_mp4)
    return esc_mp4, voz_dur


# ==============================================================================
#  OUTRO  ->  pantalla final con logo (opcional)
# ==============================================================================
def _probar_resolucion(scene_mp4):
    out = run(["ffprobe", "-v", "quiet", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0", scene_mp4])
    w, h = out.strip().split(",")
    return int(w), int(h)


def generar_outro(logo_path, dur_sec, ancho, alto, salida_mp4):
    if not os.path.exists(logo_path):
        raise RuntimeError(f"Logo no existe: {logo_path}")
    log(f"Generando outro {dur_sec}s con logo en {ancho}x{alto}...")
    escala = CONFIG["outro_logo_scale"]
    color = CONFIG["outro_bg_color"]
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", f"{dur_sec}",
        "-i", f"color=c={color}:s={ancho}x{alto}:r=30",
        "-f", "lavfi", "-t", f"{dur_sec}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-loop", "1", "-t", f"{dur_sec}", "-i", logo_path,
        "-filter_complex",
        (f"[2:v]scale='min(iw,{int(ancho * escala)})':-1[lg];"
         f"[0:v][lg]overlay=(W-w)/2:(H-h)/2:format=auto,format=yuv420p[vout]"),
        "-map", "[vout]",
        "-map", "1:a",
        "-t", f"{dur_sec}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        salida_mp4,
    ]
    run(cmd)
    log("Outro listo.")


# ==============================================================================
#  SUBTITULOS
# ==============================================================================
def _wrap_subtitulo(texto, max_chars):
    """Reparte el texto en 1 o 2 lineas equilibradas. Nunca mas de 2."""
    texto = texto.strip()
    if len(texto) <= max_chars:
        return texto
    palabras = texto.split()
    if len(palabras) <= 1:
        return texto
    mejor_corte, mejor_diff = 1, 10**9
    for i in range(1, len(palabras)):
        l1 = len(" ".join(palabras[:i]))
        l2 = len(" ".join(palabras[i:]))
        diff = abs(l1 - l2)
        if diff < mejor_diff:
            mejor_diff, mejor_corte = diff, i
    return " ".join(palabras[:mejor_corte]) + "\n" + " ".join(palabras[mejor_corte:])


def construir_srt(escenas_info, salida_srt):
    t = 0.0
    max_chars = CONFIG.get("sub_max_chars", 44)
    with open(salida_srt, "w", encoding="utf-8") as f:
        for i, (texto, dur) in enumerate(escenas_info, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt_srt_time(t)} --> {fmt_srt_time(t + dur)}\n")
            f.write(f"{_wrap_subtitulo(texto, max_chars)}\n\n")
            t += dur


# ==============================================================================
#  CONCATENAR
# ==============================================================================
def concatenar(lista_mp4, srt, salida):
    log("Concatenando todas las escenas...")
    tmp_list = salida + ".list.txt"
    with open(tmp_list, "w") as f:
        for p in lista_mp4:
            f.write(f"file '{os.path.abspath(p)}'\n")

    if CONFIG["burn_subtitles"] and srt and os.path.exists(srt):
        srt_fwd = srt.replace("\\", "/")
        estilo = (
            f"Fontname={CONFIG['sub_fontname']},"
            f"FontSize={CONFIG['sub_fontsize']},"
            f"Bold={CONFIG['sub_bold']},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=1,"
            f"Outline={CONFIG['sub_outline']},"
            f"Shadow=0,"
            f"Alignment=2,"
            f"MarginV={CONFIG['sub_margin_v']},"
            f"MarginL={CONFIG['sub_margin_h']},"
            f"MarginR={CONFIG['sub_margin_h']}"
        )
        sub = f"subtitles={srt_fwd}:force_style='{estilo}'"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", tmp_list,
             "-vf", sub, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", salida])
    else:
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", tmp_list,
             "-c", "copy", salida])
    os.remove(tmp_list)
    log(f"VIDEO FINAL LISTO: {salida}")


# ==============================================================================
#  MAIN
# ==============================================================================
def main():
    global ELEVEN_KEY, FAL_KEY
    ELEVEN_KEY, FAL_KEY = cargar_llaves()

    guion_path = sys.argv[1] if len(sys.argv) > 1 else "guion.json"
    if not os.path.exists(guion_path):
        sys.exit(f"ERROR: no encuentro el guion '{guion_path}'")

    with open(guion_path, encoding="utf-8") as f:
        guion = json.load(f)

    CONFIG.update(guion.get("config", {}))
    escenas = guion["escenas"]

    base = os.path.splitext(os.path.basename(CONFIG["output_file"]))[0]
    work = f".trabajo_{base}"
    os.makedirs(work, exist_ok=True)

    print(f"\n=== AUTO-VIDEO  -  {len(escenas)} escenas (carpeta: {work}) ===\n", flush=True)

    escenas_montadas = [None] * len(escenas)
    info_subs = [None] * len(escenas)
    fallos = []

    for idx, esc in enumerate(escenas, 1):
        print(f"--- Escena {idx}/{len(escenas)} ---", flush=True)
        try:
            esc_mp4, voz_dur = procesar_escena(idx, esc, work)
            escenas_montadas[idx - 1] = esc_mp4
            info_subs[idx - 1] = (esc["narracion"], voz_dur)
        except CreditosInsuficientes as e:
            print(f"\n!!! FAL SIN CREDITOS - me detengo: {e}", flush=True)
            print(f"!!! Las escenas exitosas siguen guardadas en '{work}'.\n", flush=True)
            sys.exit(2)
        except Exception as e:
            log(f"FALLO escena {idx}: {e}")
            fallos.append(idx)
        print(flush=True)

    if fallos:
        print(f"!!! Faltaron {len(fallos)} escena(s): {fallos}", flush=True)
        print(f"!!! Las escenas exitosas se quedaron en '{work}'.", flush=True)
        print(f"!!! Vuelve a correr `python make_video.py {guion_path}` para reintentar solo las que faltan.\n", flush=True)
        sys.exit(1)

    srt = os.path.join(work, "subs.srt")
    construir_srt(info_subs, srt)

    # Outro opcional con logo
    logo_local = CONFIG.get("logo_local") or guion.get("config", {}).get("logo_local")
    if logo_local and os.path.exists(logo_local):
        outro_mp4 = os.path.join(work, "outro.mp4")
        if not _es_media_valido(outro_mp4):
            ancho, alto = _probar_resolucion(escenas_montadas[0])
            generar_outro(logo_local, CONFIG["outro_seconds"], ancho, alto, outro_mp4)
        escenas_montadas.append(outro_mp4)

    salida = CONFIG["output_file"]
    concatenar(escenas_montadas, srt, salida)
    print(f"\n*** Duracion total: {media_duration(salida):.1f}s ***", flush=True)
    print(f"*** Video final: {os.path.abspath(salida)} ***\n", flush=True)

    # Limpieza SOLO si el video final salio bien
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
