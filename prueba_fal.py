#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueba minima de fal Vidu Q3 Turbo: genera UN solo clip de 6s a 540p 9:16 mudo.
Costo esperado: 6 * $0.035 = ~$0.21.

Uso: python prueba_fal.py
Sale: test_clip.mp4 + reporte de tamaño/duracion/costo.
"""
import os
import sys
import time
import requests


CLIP_DURATION = 6   # segundos
RESOLUTION    = "540p"
ASPECT        = "9:16"
PRECIO_X_SEG  = 0.035  # USD a 360p/540p (Vidu Q3 Turbo)
MODEL_ID      = "fal-ai/vidu/q3/text-to-video/turbo"

PROMPT_DEMO = (
    "Two sleek modern medical injection pens, white with blue accents, "
    "resting on a clean white table, glowing golden hormone molecules slowly "
    "floating around them, slow dolly-in shot, photorealistic, cinematic "
    "medical documentary style, soft natural lighting, 35mm film grain, vertical 9:16"
)


def cargar_fal_key():
    # env primero
    for n in ("FAL_KEY", "FAL_API_KEY", "FAI_API_KEY"):
        v = os.environ.get(n)
        if v:
            return v
    # claves.txt despues
    candidatos = ["claves.txt",
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "claves.txt")]
    for path in candidatos:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("FAL_KEY", "FAL_API_KEY", "FAI_API_KEY"):
                    return v.strip().strip('"').strip("'")
    sys.exit("ERROR: no encuentro FAL_KEY/FAL_API_KEY/FAI_API_KEY (env ni claves.txt)")


def main():
    key = cargar_fal_key()
    os.environ["FAL_KEY"] = key
    import fal_client

    print(f"== Prueba fal Vidu Q3 Turbo ==")
    print(f"   modelo:   {MODEL_ID}")
    print(f"   duracion: {CLIP_DURATION}s")
    print(f"   resol:    {RESOLUTION}")
    print(f"   aspect:   {ASPECT}")
    print(f"   audio:    False")
    print(f"   costo esperado: ${CLIP_DURATION * PRECIO_X_SEG:.3f}\n")

    def _on_update(status):
        n = type(status).__name__
        if n == "InProgress":
            print("   ... InProgress", flush=True)
        elif n == "Queued":
            pos = getattr(status, "position", "?")
            print(f"   ... Queued (pos={pos})", flush=True)

    t0 = time.monotonic()
    result = fal_client.subscribe(
        MODEL_ID,
        arguments={
            "prompt": PROMPT_DEMO,
            "duration": CLIP_DURATION,
            "resolution": RESOLUTION,
            "aspect_ratio": ASPECT,
            "audio": False,
        },
        with_logs=False,
        on_queue_update=_on_update,
        client_timeout=300,
    )
    elapsed = time.monotonic() - t0

    video_url = (result or {}).get("video", {}).get("url")
    if not video_url:
        sys.exit(f"ERROR: respuesta sin video.url. Raw: {result}")

    salida = "test_clip.mp4"
    print(f"\nDescargando -> {salida}")
    r = requests.get(video_url, timeout=120)
    if r.status_code != 200:
        sys.exit(f"ERROR: descarga fallo HTTP {r.status_code}")
    with open(salida, "wb") as f:
        f.write(r.content)

    tam_mb = os.path.getsize(salida) / (1024 * 1024)
    costo_estimado = CLIP_DURATION * PRECIO_X_SEG
    print(f"\n== Resultado ==")
    print(f"   archivo:        {os.path.abspath(salida)}")
    print(f"   tamano:         {tam_mb:.2f} MB")
    print(f"   tiempo total:   {elapsed:.1f}s")
    print(f"   costo (estim.): ${costo_estimado:.3f}")
    print(f"   request_id:     {result.get('request_id', 'n/a')}")


if __name__ == "__main__":
    main()
