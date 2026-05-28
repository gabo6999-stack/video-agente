#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clientes.py - Persistencia por cliente para la seccion "Ideas desde keywords".

Estructura en disco:
    clientes/<slug>/
        meta.json
        keywords.json         (lista [{keyword, volumen}, ...] ordenada desc por volumen)
        keywords_raw.xlsx     (copia del archivo subido)
        ideas.json            (historial de tandas de ideas)
        scripts/<slug_idea>.json  (un guion completo + idea origen)
"""

import os
import re
import json
import time
import unicodedata
from pathlib import Path


BASE_DIR     = Path(__file__).resolve().parent
CLIENTES_DIR = BASE_DIR / "clientes"


# ==============================================================================
#  UTILIDADES
# ==============================================================================
def slugify(name):
    """Convierte un nombre libre en un slug seguro para carpeta/filename."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    return s or "cliente"


def ruta_cliente(name, crear=True):
    """Devuelve la carpeta del cliente.

    - crear=True (default): se asegura de que exista (mkdir + scripts/ + meta.json
      con el nombre dado si todavia no existe).
    - crear=False: solo devuelve la ruta; NO crea nada. Para lecturas.
    """
    nombre_limpio = (name or "").strip()
    if not nombre_limpio:
        raise ValueError("Nombre de cliente vacio.")
    p = CLIENTES_DIR / slugify(nombre_limpio)
    if crear:
        p.mkdir(parents=True, exist_ok=True)
        (p / "scripts").mkdir(exist_ok=True)
        meta_path = p / "meta.json"
        if not meta_path.exists():
            # Cualquier write crea meta.json silenciosamente para que el cliente
            # quede visible en listar_clientes() con su nombre legible.
            meta_path.write_text(
                json.dumps({"nombre": nombre_limpio, "creado": time.time()},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return p


def registrar_cliente(name):
    """Crea la carpeta y un meta.json si no existian. Alias semantico de ruta_cliente."""
    return ruta_cliente(name, crear=True)


def listar_clientes():
    """Devuelve [{slug, nombre}, ...] solo de carpetas con meta.json (clientes reales)."""
    if not CLIENTES_DIR.exists():
        return []
    out = []
    for d in sorted(CLIENTES_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "meta.json"
        if not meta.exists():
            # Carpeta sin metadata: no es un cliente registrado (resto de pruebas
            # o creado por error). No la mostramos en el dropdown.
            continue
        try:
            nombre = json.loads(meta.read_text(encoding="utf-8")).get("nombre", d.name)
        except Exception:
            nombre = d.name
        out.append({"slug": d.name, "nombre": nombre})
    return out


def eliminar_cliente(name):
    """Borra la carpeta del cliente completa. Devuelve True si se borro algo."""
    import shutil
    p = CLIENTES_DIR / slugify(name)
    if p.exists() and p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
        return True
    return False


def limpiar_carpetas_huerfanas():
    """Borra carpetas dentro de clientes/ que NO tienen meta.json (fantasmas).
    Devuelve la lista de slugs eliminados."""
    import shutil
    if not CLIENTES_DIR.exists():
        return []
    borradas = []
    for d in CLIENTES_DIR.iterdir():
        if not d.is_dir():
            continue
        if (d / "meta.json").exists():
            continue
        # Carpeta sin meta.json: huerfana. Borrar.
        try:
            shutil.rmtree(d, ignore_errors=True)
            borradas.append(d.name)
        except OSError:
            pass
    return borradas


# ==============================================================================
#  KEYWORDS
# ==============================================================================
def leer_keywords_excel(file_obj):
    """Lee un .xlsx tolerando nombres de columnas.

    Acepta: file-like (con .read/.seek), bytes, bytearray.
    Devuelve dict con keywords + metadatos de diagnostico:
        {
          "keywords":     [{keyword, volumen}, ...] ordenado por volumen desc,
          "kw_col":       nombre de columna detectada como palabra clave (o None),
          "vol_col":      nombre de columna detectada como volumen (o None),
          "columns_seen": lista de columnas tal como aparecen en el .xlsx,
          "n_rows_raw":   filas crudas leidas (antes de filtrar),
        }
    NO lanza si no encuentra columnas: devuelve dict con keywords=[] y deja
    los campos kw_col/vol_col para que el caller diagnostique.
    """
    import io
    import pandas as pd

    # Defensive: si es file-like con puntero (UploadedFile), rebobina.
    # Streamlit re-entrega el MISMO objeto en cada rerun y pd.read_excel
    # avanza el puntero, asi que sin esto, lecturas sucesivas vuelven vacias.
    if hasattr(file_obj, "seek"):
        try:
            file_obj.seek(0)
        except Exception:
            pass

    # Materializa los bytes UNA vez y pasa un BytesIO fresco a pandas.
    if isinstance(file_obj, (bytes, bytearray)):
        bio = io.BytesIO(bytes(file_obj))
    elif hasattr(file_obj, "read"):
        bio = io.BytesIO(file_obj.read())
    else:
        bio = file_obj  # path-like, pandas lo abre

    df = pd.read_excel(bio, engine="openpyxl")
    columns_seen = [str(c) for c in df.columns]
    n_rows_raw = int(len(df))

    if df.empty:
        return {"keywords": [], "kw_col": None, "vol_col": None,
                "columns_seen": columns_seen, "n_rows_raw": n_rows_raw}

    cols_lower = {str(c).strip().lower(): c for c in df.columns}

    def _busca(opciones):
        for c_low, c_orig in cols_lower.items():
            for op in opciones:
                if op in c_low:
                    return c_orig
        return None

    kw_col = _busca(["palabra clave", "palabra", "keyword", "kw", "key word", "termino"])
    vol_col = _busca(["volumen de busqueda", "volumen de búsqueda", "volumen",
                       "search volume", "volume", "vol", "busquedas"])

    if not kw_col or not vol_col:
        return {"keywords": [], "kw_col": kw_col, "vol_col": vol_col,
                "columns_seen": columns_seen, "n_rows_raw": n_rows_raw}

    out = []
    for _, row in df.iterrows():
        kw_val = row[kw_col]
        vol_val = row[vol_col]
        if pd.isna(kw_val) or pd.isna(vol_val):
            continue
        try:
            vol_int = int(float(vol_val))
        except (ValueError, TypeError):
            continue
        kw_clean = str(kw_val).strip()
        if not kw_clean:
            continue
        out.append({"keyword": kw_clean, "volumen": vol_int})

    return {
        "keywords":     sorted(out, key=lambda x: -x["volumen"]),
        "kw_col":       kw_col,
        "vol_col":      vol_col,
        "columns_seen": columns_seen,
        "n_rows_raw":   n_rows_raw,
    }


def guardar_keywords(name, keywords, raw_bytes=None):
    """Guarda la lista de keywords. Si la lista esta vacia y ya habia datos guardados,
    NO sobreescribe (salvaguarda contra borrar por accidente)."""
    p = ruta_cliente(name, crear=True)
    target = p / "keywords.json"
    if not keywords and target.exists():
        try:
            anteriores = json.loads(target.read_text(encoding="utf-8"))
            if anteriores:
                return  # preserva las anteriores
        except Exception:
            pass
    target.write_text(
        json.dumps(keywords, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if raw_bytes is not None:
        (p / "keywords_raw.xlsx").write_bytes(raw_bytes)


def leer_keywords(name):
    """Devuelve la lista de keywords del cliente (vacia si no hay). NO crea carpeta."""
    p = ruta_cliente(name, crear=False) / "keywords.json"
    if not p.exists():
        return []
    try:
        kws = json.loads(p.read_text(encoding="utf-8"))
        return sorted(kws, key=lambda x: -int(x.get("volumen", 0) or 0))
    except Exception:
        return []


# ==============================================================================
#  IDEAS
# ==============================================================================
def guardar_ideas(name, ideas):
    """Apila una tanda de ideas en el historial (queda max las ultimas 10)."""
    p = ruta_cliente(name, crear=True) / "ideas.json"
    history = []
    if p.exists():
        try:
            history = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append({"generadas_en": time.time(), "ideas": ideas})
    history = history[-10:]
    p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return ideas


def leer_ideas_recientes(name):
    """Devuelve la tanda mas reciente: {generadas_en, ideas:[...]} o None. NO crea carpeta."""
    p = ruta_cliente(name, crear=False) / "ideas.json"
    if not p.exists():
        return None
    try:
        h = json.loads(p.read_text(encoding="utf-8"))
        return h[-1] if h else None
    except Exception:
        return None


def leer_ideas_historial(name):
    """Devuelve todas las tandas guardadas (mas reciente al final). NO crea carpeta."""
    p = ruta_cliente(name, crear=False) / "ideas.json"
    if not p.exists():
        return []
    try:
        h = json.loads(p.read_text(encoding="utf-8"))
        return h if isinstance(h, list) else []
    except Exception:
        return []


# ==============================================================================
#  SCRIPTS (guiones generados desde una idea)
# ==============================================================================
def _slug_idea(idea):
    base = (idea or {}).get("titulo") or "idea"
    return slugify(base)[:60] or "idea"


def guardar_script(name, idea, guion):
    """Persiste el guion completo asociado a una idea."""
    p = ruta_cliente(name, crear=True) / "scripts" / f"{_slug_idea(idea)}.json"
    p.write_text(
        json.dumps({
            "idea": idea,
            "generado_en": time.time(),
            "guion": guion,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def leer_scripts(name):
    """Devuelve los scripts del cliente ordenados por mtime desc. NO crea carpeta."""
    p = ruta_cliente(name, crear=False) / "scripts"
    if not p.exists():
        return []
    out = []
    for f in sorted(p.glob("*.json"), key=lambda x: -x.stat().st_mtime):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_archivo"] = f.name
            data["_mtime"] = f.stat().st_mtime
            out.append(data)
        except Exception:
            pass
    return out
