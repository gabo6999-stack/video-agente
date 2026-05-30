#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar.py - Cerebro del sistema. Convierte una descripcion libre del usuario
en un guion.json listo para make_video.py.

Uso CLI:
    python generar.py

Tambien expone funciones reutilizables (las usa app.py de Streamlit):
    cargar_llaves() -> (anthropic, eleven, fal)
    obtener_voces_elevenlabs(eleven_key) -> list[dict]
    pedir_guion_a_claude(anthro_key, descripcion, n_escenas, voces) -> dict
    escribir_guion(guion, path="guion.json") -> None
    calcular_costo(n_escenas) -> float

Defaults estandar del sistema (ver tabla de costos):
    N_ESCENAS_DEFAULT = 6
    SEG_X_ESCENA      = 6   (clips de 6s en Vidu Q3 Turbo 540p)
    PRECIO_X_SEG      = 0.035  USD
    Costo default     = 6 x 6 x 0.035 = $1.26
"""

import os
import re
import sys
import json
import subprocess


# ==============================================================================
#  CONSTANTES DEL SISTEMA
# ==============================================================================
N_ESCENAS_DEFAULT = 6
SEG_X_ESCENA      = 6
PRECIO_X_SEG      = 0.035
COSTO_DEFAULT     = N_ESCENAS_DEFAULT * SEG_X_ESCENA * PRECIO_X_SEG  # $1.26
MODELO_CLAUDE     = "claude-sonnet-4-6"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
#  CARGA DE LLAVES (env primero, claves.txt despues)
# ==============================================================================
def _leer_claves():
    candidatos = ["claves.txt", os.path.join(_BASE_DIR, "claves.txt")]
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
    # Prioridad: variables de entorno (lo que usa Railway) > claves.txt (local).
    # Asi el deploy lee de env y en local seguimos editando claves.txt.
    arch = _leer_claves()
    anthro = os.environ.get("ANTHROPIC_API_KEY") or arch.get("ANTHROPIC_API_KEY")
    eleven = os.environ.get("ELEVENLABS_API_KEY") or arch.get("ELEVENLABS_API_KEY")
    fal = None
    for alias in ("FAL_KEY", "FAL_API_KEY", "FAI_API_KEY"):
        fal = os.environ.get(alias) or arch.get(alias)
        if fal:
            break
    faltan = []
    if not anthro: faltan.append("ANTHROPIC_API_KEY")
    if not eleven: faltan.append("ELEVENLABS_API_KEY")
    if not fal:    faltan.append("FAL_KEY/FAL_API_KEY/FAI_API_KEY")
    if faltan:
        raise RuntimeError(f"Faltan llaves: {', '.join(faltan)}")
    return anthro, eleven, fal


# ==============================================================================
#  COSTO
# ==============================================================================
def calcular_costo(n_escenas):
    """Costo cuando TODAS las escenas son texto-a-video Turbo."""
    return n_escenas * SEG_X_ESCENA * PRECIO_X_SEG


def calcular_costo_mixto(n_escenas, n_imagenes):
    """Costo cuando las primeras n_imagenes escenas usan imagenes propias del
    usuario y el resto usan texto-a-video Turbo ($0.035/s).

    Las escenas con imagen propia ahora se animan GRATIS en local con FFmpeg
    (efecto Ken Burns): cuestan $0 de animacion. Solo las escenas texto-a-video
    pagan a fal. (La voz de ElevenLabs se cobra aparte, igual que siempre.)"""
    n_img = min(n_imagenes, n_escenas)
    n_t2v = max(0, n_escenas - n_img)
    return n_t2v * SEG_X_ESCENA * PRECIO_X_SEG  # imagenes propias = 0


# ==============================================================================
#  ELEVENLABS  ->  lista de voces de la cuenta
# ==============================================================================
def obtener_voces_elevenlabs(api_key):
    import requests
    r = requests.get("https://api.elevenlabs.io/v1/voices",
                     headers={"xi-api-key": api_key}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs /voices error {r.status_code}: {r.text[:200]}")
    voces = r.json().get("voices", [])
    out = []
    for v in voces:
        out.append({
            "voice_id":    v.get("voice_id"),
            "name":        v.get("name"),
            "labels":      v.get("labels", {}),
            "description": (v.get("description") or "")[:200],
            "category":    v.get("category"),
        })
    return out


# ==============================================================================
#  CLAUDE  ->  genera el guion.json
# ==============================================================================
_SYSTEM_PROMPT = """Eres el cerebro de un sistema que convierte descripciones cortas en lenguaje natural en GUIONES de video de CALIDAD PROFESIONAL.

OBJETIVO: producir un JSON valido (y SOLO JSON, sin texto envolvente, sin markdown, sin triple backtick).

DEFAULTS CUANDO EL USUARIO NO LOS ESPECIFIQUE (rellena tu silenciosamente):
- Numero de escenas:  6
- Aspect ratio:       9:16 vertical
- Voz:                elige la que mejor case con el tono del tema
- Estilo visual:      cinematografico fotorrealista
- Idioma narracion:   espanol
El usuario puede dar SOLO el tema y debe poder generar un video bueno. No le exijas detalles.

REGLAS DE NARRACION (CRITICAS para que voz y clip queden sincronizados):
- Cada escena: ENTRE 14 y 16 palabras en espanol. NUNCA mas de 18.
- Frases CORTAS, al ritmo de un clip de ~6 segundos. Una idea por escena, sin subordinadas largas.
- Tono adaptado al tema (energico, sereno, autoridad, calido, didactico, etc).
- Apertura - desarrollo - cierre en el arco completo de las escenas.
- No uses comillas dobles dentro de la narracion (rompen el JSON). Usa simples o angulares si hace falta.

REGLAS DE PROMPT VISUAL (campo "visual") - CINEMATOGRAFICO Y DETALLADO:
- SIEMPRE en INGLES, en una sola linea, sin saltos.
- Cada prompt debe incluir TODOS estos elementos (no abstracciones genericas):
  1. Sujeto concreto + accion especifica
  2. Setting / entorno con detalle (lugar, hora, atmosfera)
  3. Tipo de plano (wide shot, medium shot, close-up) + movimiento de camara (slow dolly-in, tracking, pan, static, etc)
  4. Iluminacion y mood (golden hour, soft window light, dramatic side light, low-key, etc)
  5. CALIDAD TECNICA EXPLICITA - incluye literalmente al final, antes del aspect ratio:
     "photorealistic, highly detailed, sharp focus, professional cinematography, 35mm film grain, color graded, shallow depth of field"
  6. Aspect ratio explicito al cierre: "vertical 9:16" o "horizontal 16:9".

MODO MIXTO IMAGEN+TEXTO (cuando el usuario sube K imagenes propias):
- Las primeras K escenas usan esas imagenes del usuario. Esas imagenes se animan LOCALMENTE
  con FFmpeg (efecto Ken Burns: zoom y paneo suave); NO se generan con IA. Por eso, para esas
  K escenas, el campo "visual" NO se usa para generar nada: pon solo una nota breve de
  movimiento (ej "Gentle Ken Burns zoom, vertical 9:16"). No te esfuerces en describir el
  contenido: la imagen del usuario ya lo muestra y el movimiento lo aplica FFmpeg.
- Las escenas K+1..N (sin imagen) siguen las reglas normales (sujeto + accion + setting + ...).
- La narracion sigue las MISMAS reglas (14-16 palabras) para TODAS las escenas (con o sin imagen).

COHERENCIA VISUAL ENTRE LAS 6 ESCENAS:
- Decide al principio UNA direccion de paleta y estilo (ej "warm earthy tones, soft natural light"
  o "cool teal-blue palette with cinematic neon accents") y MENCIONALA en cada uno de los 6 prompts.
- Si un personaje, lugar u objeto reaparece, COPIA su descripcion PALABRA POR PALABRA en cada
  prompt (Vidu pierde coherencia si la varias).

EVITA en los prompts (la IA de video falla ahi y se ve falso):
- Primeros planos de manos manipulando objetos.
- Letreros, textos, logos, subtitulos en pantalla.
- Primeros planos extremos de rostros hablando (bocas mal animadas).
Solo usalos si son ABSOLUTAMENTE esenciales al tema.

ESTILO NO REALISTA (si el usuario lo pide, ej 2D, anime, cartoon, watercolor):
- Aplica el estilo a las 6 escenas.
- Reemplaza la linea de calidad tecnica realista por una equivalente al estilo
  (ej "hand-drawn 2D animation, clean line art, flat colors, soft cel shading").

VOCES DISPONIBLES (elige UNA voice_id de esta lista):
{voces_json}

SCHEMA EXACTO DE SALIDA (responde SOLO con este JSON):
{{
  "config": {{
    "aspect_ratio": "9:16",
    "voice_id": "<voice_id elegido de la lista>",
    "burn_subtitles": true,
    "output_file": "video_<slug>.mp4"
  }},
  "escenas": [
    {{"narracion": "...", "visual": "..."}}
  ],
  "_voz_nombre": "<nombre legible de la voz elegida>",
  "_voz_motivo": "<una linea explicando por que esa voz encaja>"
}}

output_file: slug en minusculas con _ separando palabras, ej "video_peptidos.mp4", "video_yoga_matutino.mp4". Sin tildes ni espacios."""


def _limpiar_fences(texto):
    t = texto.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t


def pedir_guion_a_claude(anthro_key, descripcion, n_escenas, voces,
                          n_imagenes_usuario=0, imagen_paths=None, logo_path=None):
    from anthropic import Anthropic
    client = Anthropic(api_key=anthro_key)

    voces_min = [{
        "voice_id": v["voice_id"],
        "name": v["name"],
        "labels": v.get("labels", {}),
        "description": v.get("description", "")[:150],
    } for v in voces]

    sysprompt = _SYSTEM_PROMPT.format(voces_json=json.dumps(voces_min, ensure_ascii=False))

    if n_imagenes_usuario > 0:
        nota_imgs = (
            f"\n\nIMAGENES DEL USUARIO: {n_imagenes_usuario} "
            f"(escenas 1..{min(n_imagenes_usuario, n_escenas)} = imagen propia animada en local "
            f"con FFmpeg Ken Burns; escenas restantes = text-to-video con IA). "
            "Para las escenas con imagen, el campo visual no se usa: pon solo una nota breve de movimiento."
        )
    else:
        nota_imgs = "\n\nIMAGENES DEL USUARIO: 0 (todas las escenas son text-to-video)."

    user_msg = (
        f"DESCRIPCION DEL USUARIO:\n{descripcion.strip()}\n\n"
        f"NUMERO DE ESCENAS: {n_escenas}"
        f"{nota_imgs}\n\n"
        "Genera el JSON ahora. Solo el JSON, nada mas."
    )

    resp = client.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": sysprompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_msg}],
    )
    texto = _limpiar_fences(resp.content[0].text)
    try:
        guion = json.loads(texto)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude no devolvio JSON valido: {e}\n--- RAW ---\n{texto[:800]}")

    # Adjuntar referencias locales a archivos del usuario (Claude no las inventa)
    if imagen_paths:
        for i, p in enumerate(imagen_paths):
            if i < len(guion.get("escenas", [])):
                guion["escenas"][i]["imagen_local"] = p
    if logo_path:
        guion.setdefault("config", {})["logo_local"] = logo_path

    return guion


# ==============================================================================
#  IDEAS DESDE KEYWORDS (texto solamente, no toca fal ni ElevenLabs)
# ==============================================================================
_SYSTEM_IDEAS = """Eres un estratega de contenidos para video corto (Reels/TikTok/Shorts).

OBJETIVO: dada una lista de palabras clave SEO con su volumen de busqueda, proponer
{n_ideas} IDEAS de video PROFESIONALES y diferenciadas, priorizando keywords de mayor
volumen pero sin limitarte a ellas si encuentras angulos mas potentes.

REGLAS DURAS:
- Cada idea: titulo atractivo de 5 a 10 palabras (sin emojis, sin signos repetidos).
- Atribuye cada idea a UNA keyword especifica de la lista. Puedes repetir keywords.
- Anade un gancho de UNA sola linea (la promesa, tension o pregunta que abre el video).
- Mezcla formatos: explicativos, mitos vs verdades, listas, comparativas, errores comunes, casos.
- Tono profesional y honesto. CERO clickbait engañoso. CERO promesas medicas. CERO exageraciones.
- Si la tematica toca salud o medicina, ningun titulo prometiendo curas, milagros o resultados garantizados.

SCHEMA EXACTO (responde SOLO con este JSON, sin markdown ni triple backtick):
{{
  "ideas": [
    {{"titulo": "...", "keyword": "...", "gancho": "..."}}
  ]
}}"""


def proponer_ideas(anthro_key, keywords, n_ideas=8, contexto_cliente=""):
    """Propone n_ideas a partir de una lista de keywords [{keyword, volumen}, ...]."""
    from anthropic import Anthropic
    client = Anthropic(api_key=anthro_key)

    sysprompt = _SYSTEM_IDEAS.format(n_ideas=n_ideas)
    top = keywords[:50]  # mas que eso es ruido
    lista_txt = "\n".join(f'- "{k["keyword"]}" (volumen {k["volumen"]})' for k in top)
    user_msg = (
        (f"CLIENTE: {contexto_cliente}\n\n" if contexto_cliente else "")
        + f"KEYWORDS (top 50 por volumen):\n{lista_txt}\n\n"
        + f"Proponer {n_ideas} ideas. Solo el JSON."
    )

    resp = client.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=2048,
        system=[{
            "type": "text", "text": sysprompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_msg}],
    )
    texto = _limpiar_fences(resp.content[0].text)
    try:
        data = json.loads(texto)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude no devolvio JSON valido (ideas): {e}\n--- RAW ---\n{texto[:600]}")
    ideas = data.get("ideas", [])
    # Filtra ideas mal formadas
    limpias = []
    for i in ideas:
        if not isinstance(i, dict):
            continue
        if i.get("titulo") and i.get("keyword"):
            limpias.append({
                "titulo": str(i["titulo"]).strip(),
                "keyword": str(i["keyword"]).strip(),
                "gancho": str(i.get("gancho", "")).strip(),
            })
    return limpias


def generar_script_para_idea(anthro_key, idea, voces, n_escenas=6):
    """Convierte una idea en un guion completo reutilizando pedir_guion_a_claude."""
    descripcion = (
        f"Idea de video: {idea['titulo']}\n"
        f"Keyword principal a abordar: {idea['keyword']}\n"
        f"Gancho: {idea.get('gancho','')}\n\n"
        "Genera un script profesional y cuidado siguiendo las reglas del sistema. "
        "Tono claro y honesto. Si toca salud o medicina, cierre responsable invitando a consultar profesionales. "
        "Vertical 9:16. Estilo cinematografico realista coherente entre escenas."
    )
    return pedir_guion_a_claude(anthro_key, descripcion, n_escenas, voces)


def script_a_brief(idea, guion):
    """Construye el texto que se precarga como BORRADOR en la caja de Crear video."""
    escenas = guion.get("escenas", [])
    lineas = "\n".join(f"{i+1}. {esc.get('narracion','').strip()}"
                       for i, esc in enumerate(escenas))
    return (
        f"Idea: {idea.get('titulo','').strip()}\n"
        f"Keyword principal: {idea.get('keyword','').strip()}\n"
        f"Gancho: {idea.get('gancho','').strip()}\n\n"
        f"Script propuesto ({len(escenas)} escenas, ~6s cada una):\n"
        f"{lineas}\n\n"
        "Estilo: vertical 9:16, cinematografico realista. Tono profesional.\n"
        "Mantener estas narraciones lo mas cerca posible al regenerar."
    )


def validar_guion(guion, n_escenas, voces):
    if not isinstance(guion, dict) or "config" not in guion or "escenas" not in guion:
        raise RuntimeError("Guion mal formado: falta 'config' o 'escenas'.")
    voz_id = guion["config"].get("voice_id")
    voces_ids = {v["voice_id"] for v in voces}
    if voz_id not in voces_ids:
        raise RuntimeError(f"voice_id '{voz_id}' no esta en tu cuenta ElevenLabs.")
    if not guion["escenas"]:
        raise RuntimeError("El guion no tiene escenas.")


def escribir_guion(guion, path="guion.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(guion, f, indent=2, ensure_ascii=False)


# ==============================================================================
#  CLI
# ==============================================================================
def main():
    try:
        anthro, eleven, _fal = cargar_llaves()
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    print("=== Generador de video ===\n")
    print("Describe el video que quieres (tema, estilo, tono, formato).")
    print("Ej: 'video corto sobre meditacion, voz calida y femenina'\n")
    descripcion = input("> ").strip()
    if not descripcion:
        sys.exit("No describiste nada. Salgo.")

    inp = input(f"\nCuantas escenas? (Enter = {N_ESCENAS_DEFAULT}, max 20): ").strip()
    n_escenas = N_ESCENAS_DEFAULT
    if inp:
        try:
            n_escenas = int(inp)
            if not (2 <= n_escenas <= 20):
                sys.exit("Numero invalido. Entre 2 y 20.")
        except ValueError:
            sys.exit("Numero invalido.")

    costo = calcular_costo(n_escenas)
    print(f"\nCosto estimado de fal (Vidu Q3 Turbo 540p):")
    print(f"  {n_escenas} escenas x {SEG_X_ESCENA}s x ${PRECIO_X_SEG}/s = ${costo:.2f}")
    if n_escenas > N_ESCENAS_DEFAULT:
        print(f"  (default es {N_ESCENAS_DEFAULT} escenas / ${COSTO_DEFAULT:.2f})")
        c = input("Confirmas? (s/n): ").strip().lower()
        if c not in ("s", "si", "y", "yes"):
            sys.exit("Cancelado.")

    print("\nConsultando voces de ElevenLabs...")
    voces = obtener_voces_elevenlabs(eleven)
    print(f"  {len(voces)} voces en tu cuenta.")

    print(f"\nClaude ({MODELO_CLAUDE}) generando guion...")
    guion = pedir_guion_a_claude(anthro, descripcion, n_escenas, voces)
    validar_guion(guion, n_escenas, voces)
    escribir_guion(guion, "guion.json")

    print(f"\n=== Guion listo ===")
    print(f"   Voz:      {guion.get('_voz_nombre', '?')} ({guion['config']['voice_id']})")
    print(f"   Motivo:   {guion.get('_voz_motivo', '')}")
    print(f"   Output:   {guion['config'].get('output_file')}")
    print(f"   Escenas:  {len(guion['escenas'])}")
    if len(guion['escenas']) != n_escenas:
        print(f"   (Claude entrego {len(guion['escenas'])} en vez de {n_escenas})")
    print(f"\nLanzando make_video.py...\n")

    subprocess.run([sys.executable, "make_video.py", "guion.json"], cwd=_BASE_DIR, check=False)


if __name__ == "__main__":
    main()
