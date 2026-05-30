#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py - Interfaz local (Streamlit) para el sistema de video automatico.

Navegacion por sidebar con tres grupos coloreados:
  - PRODUCIR (azul):           Crear video, Usar mis imagenes
  - IDEAS Y CLIENTES (verde):  Ideas desde keywords, Repositorio / calendario
  - SISTEMA (ambar):           Biblioteca de videos, Configuracion (llaves)

Arrancar:
    streamlit run app.py
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

import shutil as _diag_shutil
import subprocess as _diag_sub

# === DIAGNOSTICO DE ARRANQUE (visible en logs de Railway) ===
# Imprime las rutas reales de ffmpeg y ffprobe ANTES de levantar Streamlit
# para confirmar disponibilidad sin tener que gastar voces/clips probando.
for _name in ("ffmpeg", "ffprobe"):
    _p = _diag_shutil.which(_name)
    print(f"[startup] {_name}: {_p or '(NO ENCONTRADO)'}", flush=True)
    if _p:
        try:
            _v = _diag_sub.run([_p, "-version"], capture_output=True,
                               text=True, timeout=5).stdout.splitlines()
            if _v:
                print(f"[startup] {_name} version: {_v[0]}", flush=True)
        except Exception as _e:
            print(f"[startup] {_name} -version error: {_e}", flush=True)
print(f"[startup] PATH={os.environ.get('PATH','')}", flush=True)

import streamlit as st

import generar
import clientes


BASE_DIR       = Path(__file__).resolve().parent
CLAVES_PATH    = BASE_DIR / "claves.txt"
PY             = sys.executable
CONFIG_OUTRO_S = 2.5

URL_BILLING = {
    "ELEVENLABS_API_KEY": "https://elevenlabs.io/app/subscription",
    "ANTHROPIC_API_KEY":  "https://console.anthropic.com/settings/billing",
    "FAL_API_KEY":        "https://fal.ai/dashboard/usage-billing/credits",
    "FAI_API_KEY":        "https://fal.ai/dashboard/usage-billing/credits",
    "FAL_KEY":            "https://fal.ai/dashboard/usage-billing/credits",
}

st.set_page_config(page_title="Video Auto", page_icon="🎬", layout="wide")


# ==============================================================================
#  LOGIN GATE (solo activo si APP_PASSWORD esta en env, p.ej. en Railway)
# ==============================================================================
def _check_password():
    """Devuelve True si el usuario tiene acceso. Si APP_PASSWORD no existe en
    el entorno, se considera modo local y no se pide contraseña."""
    app_password = os.environ.get("APP_PASSWORD")
    if not app_password:
        return True  # local: sin contraseña
    if st.session_state.get("_authed"):
        return True

    st.title("🔒 Video Auto")
    st.caption("Acceso protegido. Introduce la contraseña para continuar.")
    pw = st.text_input("Contraseña", type="password", key="_pw_input")
    cols = st.columns([1, 4])
    with cols[0]:
        clic = st.button("Entrar", type="primary", use_container_width=True)
    if clic:
        if pw == app_password:
            st.session_state["_authed"] = True
            st.session_state.pop("_pw_input", None)
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


if not _check_password():
    st.stop()


# ==============================================================================
#  ELEVENLABS BALANCE (cache 5 min)
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def _eleven_balance(api_key):
    import requests
    try:
        r = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": api_key}, timeout=10,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "usados": int(d.get("character_count", 0)),
            "limite": int(d.get("character_limit", 0)),
            "plan":   d.get("tier", "?"),
        }
    except Exception:
        return None


# ==============================================================================
#  CLAVES.TXT HELPERS
# ==============================================================================
def _leer_claves_raw():
    if not CLAVES_PATH.exists():
        return []
    filas = []
    with CLAVES_PATH.open(encoding="utf-8") as f:
        for i, raw in enumerate(f.readlines()):
            line = raw.rstrip("\n")
            if "=" not in line or line.lstrip().startswith("#"):
                filas.append((i, line, None, None))
                continue
            k, v = line.split("=", 1)
            filas.append((i, line, k.strip(), v.strip().strip('"').strip("'")))
    return filas


def _guardar_claves(nuevos_valores):
    filas = _leer_claves_raw()
    salida_lineas = []
    for _, raw, k, _v in filas:
        if k and k in nuevos_valores:
            salida_lineas.append(f"{k}={nuevos_valores[k]}")
        else:
            salida_lineas.append(raw)
    presentes = {k for _, _, k, _ in filas if k}
    nuevas = [k for k in nuevos_valores if k not in presentes]
    if nuevas:
        salida_lineas.append("")
        for k in nuevas:
            salida_lineas.append(f"{k}={nuevos_valores[k]}")
    CLAVES_PATH.write_text("\n".join(salida_lineas) + "\n", encoding="utf-8")


# ==============================================================================
#  UPLOADS HELPERS
# ==============================================================================
def _guardar_uploads(imgs, logo):
    upload_dir = BASE_DIR / ".uploads"
    upload_dir.mkdir(exist_ok=True)
    for old in list(upload_dir.glob("img_*.*")) + list(upload_dir.glob("logo.*")):
        try:
            old.unlink()
        except OSError:
            pass

    rutas_imgs = []
    for i, f in enumerate(imgs, 1):
        ext = Path(f.name).suffix.lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        dst = upload_dir / f"img_{i}{ext}"
        dst.write_bytes(f.getbuffer())
        rutas_imgs.append(str(dst.resolve()))

    ruta_logo = None
    if logo is not None:
        dst = upload_dir / "logo.png"
        dst.write_bytes(logo.getbuffer())
        ruta_logo = str(dst.resolve())
    return rutas_imgs, ruta_logo


# ==============================================================================
#  EJECUCION DEL PIPELINE  (intacto - es el flujo de generacion de video)
# ==============================================================================
def _ejecutar_generacion(descripcion, n_escenas, anthro_key, eleven_key,
                         rutas_imgs=None, ruta_logo=None, con_subs=True,
                         aspect_ratio="9:16"):
    log_box = st.empty()
    lines = []

    def _append(line):
        lines.append(line)
        log_box.code("\n".join(lines[-40:]), language="text")

    rutas_imgs = rutas_imgs or []
    n_imgs_efectivas = min(len(rutas_imgs), n_escenas)

    with st.status("Trabajando...", expanded=True) as status:
        try:
            status.update(label="1/4 · Consultando voces de ElevenLabs...")
            _append("Consultando voces de ElevenLabs...")
            voces = generar.obtener_voces_elevenlabs(eleven_key)
            _append(f"  {len(voces)} voces en la cuenta.")
            if n_imgs_efectivas:
                _append(f"  {n_imgs_efectivas} imagen(es) propias en escenas 1..{n_imgs_efectivas} "
                        f"(se animan GRATIS con FFmpeg Ken Burns, sin costo de animacion).")
            if ruta_logo:
                _append(f"  Outro con logo activado ({CONFIG_OUTRO_S}s).")

            status.update(label=f"2/4 · Claude ({generar.MODELO_CLAUDE}) escribiendo guion...")
            _append(f"Claude ({generar.MODELO_CLAUDE}) escribiendo guion para {n_escenas} escenas...")
            guion = generar.pedir_guion_a_claude(
                anthro_key, descripcion, n_escenas, voces,
                n_imagenes_usuario=n_imgs_efectivas,
                imagen_paths=rutas_imgs[:n_imgs_efectivas] if n_imgs_efectivas else None,
                logo_path=ruta_logo,
                aspect_ratio=aspect_ratio,
            )
            guion.setdefault("config", {})["burn_subtitles"] = bool(con_subs)
            generar.validar_guion(guion, n_escenas, voces)
            generar.escribir_guion(guion, str(BASE_DIR / "guion.json"))
            _append(f"  Voz elegida: {guion.get('_voz_nombre','?')}  ({guion['config']['voice_id']})")
            _append(f"  Motivo:      {guion.get('_voz_motivo','')}")
            _append(f"  Output:      {guion['config'].get('output_file')}")
            _append(f"  Escenas:     {len(guion['escenas'])}")
            _append(f"  Formato:     {guion['config'].get('aspect_ratio', '9:16')}")
            _append(f"  Subtitulos: {'ON (estilo elegante)' if con_subs else 'OFF (video limpio)'}")

            status.update(label="3/4 · Generando voz + clips...")
            _append("Lanzando make_video.py...")
            proc = subprocess.Popen(
                [PY, "make_video.py", "guion.json"],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                _append(line.rstrip())
            proc.wait()

            output_file = guion["config"].get("output_file", "video_final.mp4")
            output_path = BASE_DIR / output_file
            if proc.returncode == 0 and output_path.exists():
                status.update(label="4/4 · Video listo!", state="complete", expanded=False)
                st.success(f"Video listo en: `{output_path}`")
                with open(output_path, "rb") as f:
                    video_bytes = f.read()
                st.video(video_bytes)
                st.download_button(
                    "⬇️  Descargar video a tu PC",
                    data=video_bytes,
                    file_name=output_file,
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                    help="En Railway el disco es efimero: descarga el video antes de cerrar la sesion.",
                )
            else:
                status.update(label="Fallo durante la generacion", state="error")
                st.error(
                    f"make_video.py devolvio codigo {proc.returncode}. "
                    f"Revisa el log y vuelve a darle a Generar - la reanudacion saltara "
                    f"las escenas que si hayan quedado."
                )
        except Exception as e:
            status.update(label="Error", state="error")
            _append(f"ERROR: {e}")
            st.error(str(e))


# ==============================================================================
#  PAGINA: CREAR VIDEO
# ==============================================================================
def pagina_crear():
    # Si vino un borrador desde Ideas, precargarlo UNA vez en la caja
    if "_borrador_desc" in st.session_state:
        st.session_state["desc_crear"] = st.session_state.pop("_borrador_desc")

    st.header("Crear video")

    try:
        anthro_key, eleven_key, _fal = generar.cargar_llaves()
    except RuntimeError as e:
        st.error(f"Falta configurar llaves: {e}")
        st.info("Ve a **Configuracion (llaves)** y guarda tus llaves.")
        return

    st.info(
        "**Escribe como quieras.** Si te ayuda, puedes mencionar tema, duracion, "
        "tipo de voz, estilo visual o formato. Pero no es obligatorio: con que "
        "describas tu idea, basta. El sistema rellena el resto."
    )

    st.text_area(
        "Descripcion del video",
        height=160,
        placeholder="Ej: un video sobre los beneficios de caminar... (o describelo a tu manera)",
        label_visibility="collapsed",
        key="desc_crear",
    )
    descripcion = st.session_state.get("desc_crear", "")

    # Formato del video: etiqueta amigable -> aspect ratio que entiende el pipeline
    FORMATOS_UI = {
        "Vertical 9:16 (Reels / TikTok / Shorts)": "9:16",
        "Horizontal 16:9 (YouTube)":               "16:9",
        "Cuadrado 1:1 (feed)":                     "1:1",
    }

    c1, c2, c3, c4 = st.columns([1, 1.6, 1.1, 1.8])
    with c1:
        n_escenas = st.number_input(
            "Escenas",
            min_value=2, max_value=20,
            value=generar.N_ESCENAS_DEFAULT,
            step=1,
            help=f"Default: {generar.N_ESCENAS_DEFAULT} escenas (~{generar.N_ESCENAS_DEFAULT * generar.SEG_X_ESCENA}s)",
        )
    with c2:
        formato_label = st.selectbox(
            "Formato del video",
            list(FORMATOS_UI.keys()),
            index=0,  # vertical 9:16 por defecto
            help="Vertical para Reels/TikTok/Shorts, horizontal para YouTube, "
                 "cuadrado para feed. Aplica a todo: clips de IA, tus fotos y subtitulos.",
        )
        aspect_ratio = FORMATOS_UI[formato_label]
    with c3:
        con_subs = st.toggle(
            "Con subtitulos",
            value=True,
            help="Subtitulos incrustados estilo Reels. Desactiva para video limpio.",
        )
    with c4:
        st.caption(
            f"{n_escenas} escenas × {generar.SEG_X_ESCENA}s · {formato_label.split(' (')[0]}. "
            f"Default: {generar.N_ESCENAS_DEFAULT} escenas (${generar.COSTO_DEFAULT:.2f}). "
            f"{'Con subs.' if con_subs else 'Sin subs.'}"
        )

    uploads_abierto = bool(st.session_state.get("_abrir_uploads", False))
    with st.expander(
        "Opcional · usar tus propias imagenes / logo final",
        expanded=uploads_abierto,
    ):
        st.caption(
            "Si subes tus propias imagenes, el sistema las ANIMA GRATIS aqui mismo: "
            "le da un movimiento suave de zoom y paneo (efecto Ken Burns) a cada una, "
            "sin costo de animacion (solo pagas la voz). Una imagen por escena, en orden. "
            "Las escenas para las que no subas imagen se generan con IA. "
            "El logo se agrega como pantalla de cierre (2.5s, fondo negro, sin costo)."
        )
        imgs = st.file_uploader(
            "Imagenes (orden = orden de escenas)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help="Sube hasta el numero de escenas. Cada imagen se anima gratis. "
                 "Si subes menos, las restantes se generan con IA.",
            key="up_imgs_crear",
        )
        logo = st.file_uploader(
            "Logo PNG para outro (opcional)",
            type=["png"],
            accept_multiple_files=False,
            help="Si lo subes, el video termina con tu logo centrado sobre fondo negro durante 2.5s.",
            key="up_logo_crear",
        )

    n_imgs_subidas = len(imgs) if imgs else 0
    n_imgs_efectivas = min(n_imgs_subidas, n_escenas)
    n_ia = n_escenas - n_imgs_efectivas
    if n_imgs_efectivas > 0:
        costo = generar.calcular_costo_mixto(n_escenas, n_imgs_efectivas)
        if n_ia > 0:
            modo_etiqueta = f"{n_imgs_efectivas} con tus fotos (gratis) + {n_ia} con IA"
        else:
            modo_etiqueta = f"{n_imgs_efectivas} con tus fotos (gratis)"
    else:
        costo = generar.calcular_costo(n_escenas)
        modo_etiqueta = f"{n_escenas} escenas"

    aviso_extra = (
        n_escenas > generar.N_ESCENAS_DEFAULT
        or costo > generar.COSTO_DEFAULT * 1.01
    )
    if n_imgs_subidas > n_escenas:
        st.info(
            f"Subiste {n_imgs_subidas} imagenes pero solo hay {n_escenas} escenas. "
            f"Solo se usaran las primeras {n_escenas}."
        )
    if n_imgs_efectivas > 0:
        st.success(
            f"Tus {n_imgs_efectivas} imagen(es) se animan **gratis** (efecto Ken Burns, "
            f"sin costo de animacion)."
            + (f" Las otras {n_ia} escena(s) se generan con IA." if n_ia > 0 else "")
        )
    if aviso_extra:
        st.warning(
            f"Costo arriba del default ({modo_etiqueta}): **${costo:.2f}** "
            f"vs ${generar.COSTO_DEFAULT:.2f} estandar."
        )

    # El costo mostrado es solo el de fal (animacion IA). Las imagenes propias
    # no suman; la voz de ElevenLabs se cobra aparte (saldo en la barra lateral).
    if costo <= 0.0001:
        btn_label = "🎬  Generar video  ·  sin costo de animacion (solo la voz)"
    else:
        btn_label = f"🎬  Generar video  ·  ~${costo:.2f} - {modo_etiqueta}"
    if logo is not None:
        btn_label += "  + outro"

    if st.button(btn_label, type="primary",
                 disabled=not descripcion.strip(),
                 use_container_width=True):
        if aviso_extra and not st.session_state.get("_confirmado", False):
            st.session_state["_confirmado"] = True
            st.warning("Pulsa el boton otra vez para confirmar este costo.")
            return
        st.session_state.pop("_confirmado", None)
        rutas_imgs, ruta_logo = _guardar_uploads(imgs or [], logo)
        _ejecutar_generacion(
            descripcion, n_escenas, anthro_key, eleven_key,
            rutas_imgs=rutas_imgs, ruta_logo=ruta_logo,
            con_subs=con_subs, aspect_ratio=aspect_ratio,
        )


# ==============================================================================
#  PAGINA: IDEAS DESDE KEYWORDS
# ==============================================================================
def _selector_cliente(prefix=""):
    """Selector de cliente reutilizable. Devuelve el nombre activo o None."""
    existentes = clientes.listar_clientes()
    nombres = [c["nombre"] for c in existentes]
    OPCION_NUEVO = "+ Nuevo cliente..."
    opciones = [OPCION_NUEVO] + nombres

    actual = st.session_state.get("_cliente_actual")
    idx = 0
    if actual in nombres:
        idx = nombres.index(actual) + 1

    sel = st.selectbox("Cliente", opciones, index=idx, key=f"{prefix}sel_cliente")

    if sel == OPCION_NUEVO:
        nuevo = st.text_input(
            "Nombre del nuevo cliente",
            key=f"{prefix}nombre_nuevo_cliente",
            placeholder="ej. Farmacia Lopez",
        )
        if nuevo.strip() and st.button("Registrar cliente", key=f"{prefix}btn_reg_cliente"):
            clientes.registrar_cliente(nuevo.strip())
            st.session_state["_cliente_actual"] = nuevo.strip()
            st.rerun()
        return None
    st.session_state["_cliente_actual"] = sel
    return sel


def pagina_ideas():
    st.header("Ideas desde keywords")
    st.caption(
        "Solo usa la API de Claude (no gasta creditos de fal ni ElevenLabs). "
        "Sube una tabla de keywords con volumenes y Claude propone ideas y scripts cuidados."
    )

    try:
        anthro_key, eleven_key, _fal = generar.cargar_llaves()
    except RuntimeError as e:
        st.error(f"Falta configurar llaves: {e}")
        return

    cliente = _selector_cliente(prefix="ideas_")
    if not cliente:
        st.info("Elige un cliente existente o crea uno nuevo para empezar.")
        return

    st.divider()
    st.subheader(f"📋 Tabla de keywords · {cliente}")

    up_xlsx = st.file_uploader(
        "Subir Excel (.xlsx) con keywords",
        type=["xlsx"],
        help="Columnas esperadas: 'palabra clave' y 'volumen de busqueda'. Acepta variantes (keyword, kw, volumen, search volume...).",
        key=f"up_kw_{cliente}",
    )
    # Solo procesar cuando llega un archivo NUEVO. Sin esto, cada rerun de
    # Streamlit re-procesaria el mismo upload y, con el puntero ya consumido,
    # sobreescribia el keywords.json con lista vacia.
    sig_key = f"_kw_sig_{clientes.slugify(cliente)}"
    sig_actual = (up_xlsx.name, up_xlsx.size) if up_xlsx is not None else None
    if up_xlsx is not None and st.session_state.get(sig_key) != sig_actual:
        try:
            up_xlsx.seek(0)
            raw_bytes = up_xlsx.read()
            info = clientes.leer_keywords_excel(raw_bytes)
            if info["keywords"]:
                clientes.guardar_keywords(cliente, info["keywords"], raw_bytes=raw_bytes)
                st.session_state[sig_key] = sig_actual
                st.success(
                    f"Tabla guardada: {len(info['keywords'])} keywords "
                    f"(de {info['n_rows_raw']} filas en el Excel). "
                    f"Columnas detectadas: keyword=`{info['kw_col']}`, volumen=`{info['vol_col']}`."
                )
            else:
                st.error(
                    "El Excel se leyo pero no produjo keywords validas.\n\n"
                    f"- Columnas vistas: {info['columns_seen']}\n"
                    f"- Filas leidas: {info['n_rows_raw']}\n"
                    f"- Detectado: kw_col={info['kw_col']!r}, vol_col={info['vol_col']!r}\n\n"
                    "Si las columnas no se detectaron, renombra a 'palabra clave' y "
                    "'volumen de busqueda' (o keyword/volumen) y vuelve a subirlo."
                )
        except Exception as e:
            import traceback
            st.error(f"No pude leer el Excel: {e}")
            with st.expander("Traceback completo"):
                st.code(traceback.format_exc())

    kws = clientes.leer_keywords(cliente)
    if not kws:
        st.info("No hay keywords todavia. Sube un .xlsx arriba para empezar.")
        return

    st.write(f"**{len(kws)}** keywords (ordenadas por volumen desc):")
    st.dataframe(
        kws,
        hide_index=True,
        use_container_width=True,
        column_config={
            "keyword": st.column_config.TextColumn("Palabra clave"),
            "volumen": st.column_config.NumberColumn("Volumen", format="%d"),
        },
    )

    st.divider()
    st.subheader("💡 Ideas de contenido")

    c1, c2 = st.columns([1, 2])
    with c1:
        n_ideas = st.slider("Cuantas ideas", 5, 10,
                            value=int(st.session_state.get("_n_ideas", 8)),
                            key=f"slider_n_ideas_{cliente}")
        st.session_state["_n_ideas"] = n_ideas
    with c2:
        st.caption(
            f"Claude ({generar.MODELO_CLAUDE}) leera tus top 50 keywords y propondra "
            f"{n_ideas} ideas variadas. Costo aprox: pocos centavos en Anthropic, "
            "cero en fal y ElevenLabs."
        )

    if st.button("Proponer contenidos", type="primary", use_container_width=True,
                 key=f"btn_ideas_{cliente}"):
        with st.spinner("Claude pensando..."):
            try:
                ideas = generar.proponer_ideas(
                    anthro_key, kws, n_ideas=n_ideas, contexto_cliente=cliente,
                )
                clientes.guardar_ideas(cliente, ideas)
                st.session_state[f"_ideas_{cliente}"] = ideas
                st.success(f"{len(ideas)} ideas generadas y guardadas en disco.")
            except Exception as e:
                st.error(f"Fallo al proponer ideas: {e}")

    # Mostrar ideas (de session o de disco)
    ideas = st.session_state.get(f"_ideas_{cliente}")
    if not ideas:
        ultima = clientes.leer_ideas_recientes(cliente)
        ideas = ultima["ideas"] if ultima else []

    if not ideas:
        st.caption("Aun no se generaron ideas para este cliente.")
        return

    st.write(f"**{len(ideas)} ideas**:")
    for i, idea in enumerate(ideas, 1):
        with st.container(border=True):
            st.markdown(f"**{i}. {idea['titulo']}**")
            st.caption(f"🔑 Keyword: `{idea['keyword']}`")
            if idea.get("gancho"):
                st.write(f"_{idea['gancho']}_")

            cols = st.columns([1.3, 4])
            with cols[0]:
                if st.button("✍️ Generar script", key=f"gen_{cliente}_{i}"):
                    with st.spinner("Claude escribiendo el script..."):
                        try:
                            voces = generar.obtener_voces_elevenlabs(eleven_key)
                            guion = generar.generar_script_para_idea(
                                anthro_key, idea, voces,
                                n_escenas=generar.N_ESCENAS_DEFAULT,
                            )
                            clientes.guardar_script(cliente, idea, guion)
                            st.session_state[f"_script_{cliente}_{i}"] = {
                                "idea": idea, "guion": guion,
                            }
                            st.success("Script generado y guardado.")
                        except Exception as e:
                            st.error(f"Fallo al generar script: {e}")

            script_key = f"_script_{cliente}_{i}"
            if script_key in st.session_state:
                _renderizar_script(cliente, st.session_state[script_key], i)


def _renderizar_script(cliente, paquete, idx):
    """Muestra script con copy nativo de st.code + boton 'Enviar al generador'."""
    idea = paquete["idea"]
    guion = paquete["guion"]
    brief = generar.script_a_brief(idea, guion)

    st.markdown("**Script generado** (boton de copiar en la esquina superior derecha del bloque):")
    st.code(brief, language="text")

    cols = st.columns([1.4, 1, 3])
    with cols[0]:
        if st.button("📤 Enviar al generador", key=f"send_{cliente}_{idx}",
                     type="primary"):
            st.session_state["_borrador_desc"] = brief
            st.session_state["_pagina"] = "Crear video"
            st.session_state.pop("_abrir_uploads", None)
            st.rerun()
    with cols[1]:
        voz = guion.get("_voz_nombre", "?")
        st.caption(f"Voz sugerida: {voz}")


# ==============================================================================
#  PAGINA: REPOSITORIO / CALENDARIO
# ==============================================================================
def pagina_repositorio():
    st.header("Repositorio / calendario")
    st.caption("Ideas y scripts ya generados, organizados por cliente.")

    clientes_list = clientes.listar_clientes()
    if not clientes_list:
        st.info("No hay clientes registrados. Crea uno en **Ideas desde keywords**.")
        return

    nombres = [c["nombre"] for c in clientes_list]
    actual = st.session_state.get("_cliente_actual")
    idx = nombres.index(actual) if actual in nombres else 0
    sel = st.selectbox("Cliente", nombres, index=idx, key="repo_cliente_sel")
    st.session_state["_cliente_actual"] = sel

    st.divider()

    ultima = clientes.leer_ideas_recientes(sel)
    if ultima and ultima.get("ideas"):
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(ultima["generadas_en"]))
        st.subheader(f"💡 Ultimas ideas ({ts})")
        for i, idea in enumerate(ultima["ideas"], 1):
            with st.container(border=True):
                st.markdown(f"**{i}. {idea['titulo']}**")
                st.caption(f"Keyword: `{idea['keyword']}`  ·  {idea.get('gancho','')}")
    else:
        st.info("Sin ideas guardadas para este cliente.")

    scripts = clientes.leer_scripts(sel)
    if scripts:
        st.divider()
        st.subheader(f"📜 Scripts guardados ({len(scripts)})")

        for s in scripts:
            idea = s.get("idea", {})
            guion = s.get("guion", {})
            ts = time.strftime("%Y-%m-%d %H:%M",
                               time.localtime(s.get("generado_en", s.get("_mtime", 0))))
            with st.expander(f"📄 {idea.get('titulo','(sin titulo)')}  ·  {ts}"):
                st.caption(f"Keyword: `{idea.get('keyword','?')}`")
                brief = generar.script_a_brief(idea, guion)
                st.code(brief, language="text")
                if st.button("📤 Enviar al generador",
                             key=f"repo_send_{s['_archivo']}",
                             type="primary"):
                    st.session_state["_borrador_desc"] = brief
                    st.session_state["_pagina"] = "Crear video"
                    st.session_state.pop("_abrir_uploads", None)
                    st.rerun()
    else:
        st.caption("Sin scripts guardados todavia.")


# ==============================================================================
#  PAGINA: BIBLIOTECA DE VIDEOS
# ==============================================================================
def pagina_biblioteca():
    st.header("Biblioteca de videos")
    st.caption("Todos los .mp4 generados en la carpeta del proyecto.")

    mp4s = sorted(BASE_DIR.glob("*.mp4"), key=lambda x: -x.stat().st_mtime)
    if not mp4s:
        st.info("Todavia no hay videos en la carpeta del proyecto.")
        return

    for f in mp4s:
        size_mb = f.stat().st_size / (1024 * 1024)
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        with st.expander(f"🎬 {f.name}  ·  {size_mb:.1f} MB  ·  {ts}"):
            with open(f, "rb") as vf:
                data = vf.read()
            st.video(data)
            st.download_button(
                "⬇️  Descargar a tu PC",
                data=data,
                file_name=f.name,
                mime="video/mp4",
                key=f"dl_{f.name}",
                use_container_width=True,
            )


# ==============================================================================
#  PAGINA: CONFIGURACION (llaves)
# ==============================================================================
def pagina_config():
    st.header("Llaves API")
    st.caption(
        f"Archivo: `{CLAVES_PATH}`. Pega cada llave despues del = y guarda. "
        "Los botones **Recargar** abren la pagina de saldo del proveedor."
    )

    # Banner: que llaves vienen del entorno (Railway)
    KEYS_CONOCIDAS = ["ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY",
                      "FAL_KEY", "FAL_API_KEY", "FAI_API_KEY", "APP_PASSWORD"]
    en_env = [k for k in KEYS_CONOCIDAS if os.environ.get(k)]
    if en_env:
        st.info(
            f"⚙️ **Origen actual**: estas llaves vienen del entorno (Railway): "
            f"`{', '.join(en_env)}`. Las ediciones aqui guardan en `claves.txt`, "
            "pero las variables de entorno **siempre toman precedencia**."
        )
    else:
        st.caption("📄 **Origen actual**: solo `claves.txt` (sin variables de entorno).")

    # Si claves.txt no existe o esta vacio, ofrecemos formulario para crearlo
    filas = _leer_claves_raw() if CLAVES_PATH.exists() else []
    pares = [(k, v) for _, _, k, v in filas if k]
    if not pares:
        st.warning("`claves.txt` esta vacio o no existe. Llena las llaves que necesites y guarda.")
        pares = [
            ("ANTHROPIC_API_KEY", ""),
            ("ELEVENLABS_API_KEY", ""),
            ("FAL_KEY", ""),
        ]

    nombre_amigable = {
        "ANTHROPIC_API_KEY":  "Claude (Anthropic)",
        "ELEVENLABS_API_KEY": "ElevenLabs (voz)",
        "FAL_API_KEY":        "fal.ai (clips de video)",
        "FAI_API_KEY":        "fal.ai (clips de video) - errata: deberia ser FAL_API_KEY",
        "FAL_KEY":            "fal.ai (clips de video)",
        "XAI_API_KEY":        "Grok / xAI (legacy, ya no se usa)",
    }

    nuevos = {}
    with st.form("form_claves"):
        for k, v in pares:
            titulo = nombre_amigable.get(k, k)
            cols = st.columns([4, 1])
            with cols[0]:
                nuevos[k] = st.text_input(
                    f"{titulo}  ·  `{k}`",
                    value=v,
                    type="password",
                    key=f"in_{k}",
                )
            with cols[1]:
                url = URL_BILLING.get(k)
                if url:
                    st.link_button("Recargar saldo", url, use_container_width=True)
                else:
                    st.write("")
        guardado = st.form_submit_button("Guardar cambios", type="primary")

    if guardado:
        viejos = {k: v for k, v in pares}
        cambios = {k: v for k, v in nuevos.items() if v != viejos.get(k)}
        if not cambios:
            st.info("No hubo cambios que guardar.")
        else:
            _guardar_claves(cambios)
            # Invalidar el cache del balance si cambio la llave de ElevenLabs
            if "ELEVENLABS_API_KEY" in cambios:
                _eleven_balance.clear()
            st.success(f"Guardado: {', '.join(cambios.keys())}")
            st.toast("claves.txt actualizado")

    st.divider()
    st.subheader("Atajos de recarga")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.link_button("ElevenLabs · Subscription",
                       URL_BILLING["ELEVENLABS_API_KEY"],
                       use_container_width=True)
    with c2:
        st.link_button("fal.ai · Credits",
                       URL_BILLING["FAL_API_KEY"],
                       use_container_width=True)
    with c3:
        st.link_button("Anthropic · Billing",
                       URL_BILLING["ANTHROPIC_API_KEY"],
                       use_container_width=True)


# ==============================================================================
#  SIDEBAR NAV (3 grupos coloreados)
# ==============================================================================
PAGINAS = {
    "Crear video":               pagina_crear,
    "Ideas desde keywords":      pagina_ideas,
    "Repositorio / calendario":  pagina_repositorio,
    "Biblioteca de videos":      pagina_biblioteca,
    "Configuracion (llaves)":    pagina_config,
}

GROUPS = [
    ("PRODUCIR",          "#1d4ed8",  ["Crear video", "Usar mis imagenes"]),
    ("IDEAS Y CLIENTES",  "#15803d",  ["Ideas desde keywords", "Repositorio / calendario"]),
    ("SISTEMA",           "#b45309",  ["Biblioteca de videos", "Configuracion (llaves)"]),
]


def _pill(text, color):
    st.sidebar.markdown(
        f"<div style='background:{color}; color:white; padding:6px 12px; "
        "border-radius:6px; font-weight:600; margin:14px 0 6px 0; "
        "font-size:0.8em; letter-spacing:0.6px;'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def render_sidebar():
    st.sidebar.markdown("## 🎬 Video Auto")

    # Saldo ElevenLabs (cache 5min)
    try:
        _, eleven_key, _ = generar.cargar_llaves()
    except Exception:
        eleven_key = None
    bal = _eleven_balance(eleven_key) if eleven_key else None
    if bal:
        restantes = max(0, bal["limite"] - bal["usados"])
        pct = (bal["usados"] / bal["limite"] * 100) if bal["limite"] else 0
        st.sidebar.caption(
            f"ElevenLabs · {restantes:,} chars restantes · "
            f"{pct:.0f}% usado · plan {bal['plan']}"
        )
    else:
        st.sidebar.caption("ElevenLabs · saldo no disponible")

    if "_pagina" not in st.session_state:
        st.session_state["_pagina"] = "Crear video"

    for grupo_nombre, color, items in GROUPS:
        _pill(grupo_nombre, color)
        for item in items:
            es_activa = (
                st.session_state["_pagina"] == item
                or (item == "Usar mis imagenes"
                    and st.session_state["_pagina"] == "Crear video"
                    and st.session_state.get("_abrir_uploads"))
            )
            label = ("▸ " if es_activa else "   ") + item
            if st.sidebar.button(label, use_container_width=True, key=f"nav_{item}"):
                if item == "Usar mis imagenes":
                    st.session_state["_pagina"] = "Crear video"
                    st.session_state["_abrir_uploads"] = True
                else:
                    st.session_state["_pagina"] = item
                    st.session_state.pop("_abrir_uploads", None)
                st.rerun()


# ==============================================================================
#  ROUTING
# ==============================================================================
render_sidebar()

_pag = st.session_state.get("_pagina", "Crear video")
if _pag in PAGINAS:
    PAGINAS[_pag]()
else:
    pagina_crear()
