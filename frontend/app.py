"""ENAHO Hub: portal interactivo sobre la Encuesta Nacional de Hogares.

La metadata (módulos, diccionario, sinopsis, mapeo de cuestionarios) se sirve OFFLINE
desde los archivos pre-horneados en data/. Solo el Graficador y las Descargas tocan el
portal de INEI en vivo (con caché y manejo de errores de red).
"""
import gzip
import io
import json
import os
import re
import sys
import tempfile

import pandas as pd
import streamlit as st

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
sys.path.insert(0, os.path.join(RAIZ, "ai"))

from comun import coleccion, fix_encoding, normaliza_modulo  # noqa: E402
from sinopsis_modulos import sinopsis_de  # noqa: E402

st.set_page_config(page_title="ENAHO Hub", page_icon="📊", layout="wide")


# --- Carga de metadata offline (cacheada) -----------------------------------
@st.cache_data
def cargar_resumen():
    with open(os.path.join(DATA, "enaho_resumen.json"), encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def cargar_modulos():
    with gzip.open(os.path.join(DATA, "enaho_modulos.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def cargar_variables():
    return pd.read_parquet(os.path.join(DATA, "enaho_variables.parquet"))


@st.cache_data
def cargar_cuestionarios():
    ruta = os.path.join(DATA, "cuestionario_paginas.json")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return {}


@st.cache_data
def indice_descarga(anios):
    """coleccion -> anio -> {module_name: {code, formatos}} desde el catalogo offline.

    Sirve para poblar los selectores y resolver el codigo de descarga de cada modulo,
    restringido a los anios de la demo. No toca la red (load_catalog es offline).
    """
    from inei_microdatos import load_catalog
    from inei_microdatos.catalog import filter_catalog

    enaho = filter_catalog(load_catalog(), survey="enaho")
    idx = {}
    for e in enaho:
        col = coleccion(e.get("category"), e.get("value"))
        for anio, periodos in (e.get("years") or {}).items():
            if anio not in anios:
                continue
            for _periodo, pdata in (periodos or {}).items():
                for m in pdata.get("modules", []):
                    nombre = fix_encoding(m.get("module_name"))
                    code = m.get("csv_code") or m.get("stata_code") or m.get("spss_code")
                    if not code:
                        continue
                    formatos = [f for f, c in (("CSV", m.get("csv_code")),
                                               ("STATA", m.get("stata_code")),
                                               ("SPSS", m.get("spss_code"))) if c]
                    idx.setdefault(col, {}).setdefault(anio, {})[nombre] = {
                        "code": code, "formatos": formatos,
                        "modulo_code": normaliza_modulo(m.get("module_code")),
                    }
    return idx


def leer_modulo(code):
    """Descarga y lee un modulo de INEI (en vivo). Cacheado; puede lanzar por red."""
    @st.cache_data(show_spinner=f"Descargando base {code} de INEI...")
    def _leer(c):
        from inei_microdatos import read_module
        return read_module(c)
    return _leer(code)


# --- Visor de cuestionario (rasteriza el PDF local con pymupdf) --------------
@st.cache_data(show_spinner=False)
def _num_paginas(ruta):
    import fitz
    doc = fitz.open(ruta)
    n = doc.page_count
    doc.close()
    return n


@st.cache_data(show_spinner=False)
def _render_pagina(ruta, pagina):
    import fitz
    doc = fitz.open(ruta)
    png = doc[pagina - 1].get_pixmap(dpi=170).tobytes("png")
    doc.close()
    return png


_RE_NUMPREG = re.compile(r"^[pP](\d{3})")


def _numero_pregunta(variable):
    m = _RE_NUMPREG.match(str(variable))
    return m.group(1) if m else None


def _cod_valor(k):
    """Muestra el código de valor sin el .0 sobrante ('1.0' -> '1')."""
    try:
        f = float(k)
        return str(int(f)) if f.is_integer() else str(k)
    except (TypeError, ValueError):
        return str(k)


@st.cache_data(show_spinner=False)
def _pagina_con_pregunta(ruta, pagina_base, numero, total, zoom):
    """Renderiza la página resaltando la pregunta 'numero'.

    Afina la página: si el número no aparece como texto en la horneada, lo busca en las
    vecinas (+-2) y usa esa. Devuelve (png_bytes, pagina_usada, encontrada).
    """
    import fitz

    def coincide(w):
        t = w.strip(".)-º°:() ")
        return numero is not None and t in (numero, "P" + numero, "p" + numero)

    doc = fitz.open(ruta)

    def rects_de(p):
        page = doc[p - 1]
        rr = [fitz.Rect(x0, y0, x1, y1)
              for x0, y0, x1, y1, w, *_ in page.get_text("words") if coincide(w)]
        rr.sort(key=lambda r: (round(r.x0 / 60), r.y0))  # por columna y altura
        return rr

    orden = [pagina_base] + [pagina_base + d for d in (-1, 1, -2, 2)
                             if 1 <= pagina_base + d <= total]
    elegida, rect = pagina_base, None
    for p in orden:
        rr = rects_de(p)
        if rr:
            elegida, rect = p, rr[0]
            break

    page = doc[elegida - 1]
    if rect is not None:
        colw = page.rect.width * 0.46
        marca = fitz.Rect(rect.x0 - 3, rect.y0 - 3,
                          min(rect.x0 + colw, page.rect.width), rect.y1 + 3)
        try:
            page.draw_rect(marca, color=(0.9, 0.35, 0), width=2,
                           fill=(1, 0.9, 0.2), fill_opacity=0.3)
        except Exception:
            page.draw_rect(marca, color=(0.9, 0.35, 0), width=2)
    if zoom and rect is not None and page.rotation == 0:
        clip = fitz.Rect(max(0, rect.x0 - 12), max(0, rect.y0 - 16),
                         min(page.rect.width, rect.x0 + page.rect.width * 0.5),
                         min(page.rect.height, rect.y0 + 320))
        png = page.get_pixmap(dpi=200, clip=clip).tobytes("png")
    else:  # paginas rotadas (roster) o sin zoom: pagina completa
        png = page.get_pixmap(dpi=170).tobytes("png")
    doc.close()
    return png, elegida, rect is not None


def _ruta_pdf(mapeo, cuest):
    """Ruta absoluta al PDF: el real si esta presente; si no, el de muestra si coincide forma."""
    pdf_rel = mapeo.get("pdf")
    if pdf_rel and os.path.exists(os.path.join(DATA, pdf_rel)):
        return os.path.join(DATA, pdf_rel)
    muestra = cuest.get("_muestra") or {}
    if muestra.get("forma") == mapeo.get("forma"):
        ruta = os.path.join(DATA, muestra.get("pdf", ""))
        if os.path.exists(ruta):
            return ruta
    return None


def _enlaces_cuestionario(modulos, col, anio):
    docs = (modulos.get(col, {}).get(anio, {}) or {}).get("docs", [])
    return [d for d in docs if d.get("url") and (d.get("doc_name") or "").startswith("Cuestionario")]


def _mostrar_enlaces(modulos, col, anio):
    cues = _enlaces_cuestionario(modulos, col, anio)
    if cues:
        st.caption("Cuestionario completo:")
        for d in cues:
            st.markdown(f"- [{d['doc_name']}]({d['url']})")
    else:
        st.caption("Sin cuestionario disponible para este módulo.")


def _visor_cuestionario(cuest, modulos, col, anio, modulo_code, variable):
    """Muestra la pregunta resaltada en su página del cuestionario, con zoom y navegación."""
    st.markdown("#### Visor de cuestionario")
    mapeo = (cuest.get(col, {}).get(anio, {}).get(modulo_code, {}) or {}).get(variable)
    if not (mapeo and mapeo.get("pagina")):
        st.caption("Variable sin pregunta mapeada (derivada/calculada, o en una grilla del "
                   "cuestionario).")
        _mostrar_enlaces(modulos, col, anio)
        return
    ruta = _ruta_pdf(mapeo, cuest)
    if not ruta:
        st.info(f"Mapeada a {mapeo.get('forma')} página {mapeo['pagina']}, pero el PDF no está "
                "en este equipo (corre ai/build_cuestionarios.py).")
        _mostrar_enlaces(modulos, col, anio)
        return
    total = _num_paginas(ruta)
    numero = _numero_pregunta(variable)
    base = min(int(mapeo["pagina"]), total)
    zoom = st.toggle("🔍 Acercar a la pregunta", value=True,
                     key=f"zoom_{modulo_code}_{variable}")
    png, usada, ok = _pagina_con_pregunta(ruta, base, numero, total, zoom)
    if ok:
        st.success(f"{mapeo.get('forma')} · pregunta {numero} resaltada en la página {usada}.")
    else:
        st.info(f"{mapeo.get('forma')} · página {usada}. No ubiqué la pregunta en el texto; "
                "revísala en la página o ajústala abajo.")
    st.image(png, use_container_width=True)
    with st.expander("Ver otra página o abrir el cuestionario completo"):
        ir = st.number_input("Página", min_value=1, max_value=total, value=usada,
                             key=f"vis_{modulo_code}_{variable}")
        if ir != usada:
            st.image(_render_pagina(ruta, int(ir)), use_container_width=True)
        _mostrar_enlaces(modulos, col, anio)


# --- Sidebar: modo institucion (esquema B2B, sin login real) ----------------
def sidebar_institucion():
    st.sidebar.header("Modo institución")
    try:
        instituciones = dict(st.secrets["instituciones"])
    except Exception:
        instituciones = {}
    codigo = st.sidebar.text_input("Código de institución", type="password",
                                   placeholder="ej. UP-2024")
    activa = None
    if codigo:
        nombre = instituciones.get(codigo)
        if nombre:
            activa = nombre
            st.sidebar.success(f"Acceso B2B activo: {nombre}")
        else:
            st.sidebar.error("Código no reconocido")
    st.sidebar.caption("Demostración del esquema B2B por cuentas institucionales "
                       "(MEF, UP, ULIMA, PUCP). Sin login real.")
    return activa


# --- Selector de modulo compartido (Graficador y Descargas) -----------------
def selector_modulo(idx, prefijo):
    if not idx:
        st.warning("No hay catálogo disponible para los años de la demo.")
        return None
    col = st.selectbox("Colección", sorted(idx.keys()), key=f"{prefijo}_col")
    anio = st.selectbox("Año", sorted(idx[col].keys()), key=f"{prefijo}_anio")
    modulos = idx[col][anio]
    nombre = st.selectbox("Módulo", sorted(modulos.keys()), key=f"{prefijo}_mod")
    info = modulos[nombre]
    st.caption(sinopsis_de(nombre))
    return {"coleccion": col, "anio": anio, "modulo": nombre,
            "code": info["code"], "formatos": info["formatos"],
            "modulo_code": info.get("modulo_code")}


# --- Pestaña 1: Inicio ------------------------------------------------------
def tab_inicio(resumen, institucion):
    st.title("📊 ENAHO Hub")
    st.subheader("Toda la Encuesta Nacional de Hogares, lista para investigar")
    if institucion:
        st.info(f"Sesión institucional: **{institucion}**")
    st.write(
        "La ENAHO es la principal fuente de pobreza, empleo e ingresos del Perú, pero llega "
        "en decenas de módulos, formatos y años con codificación incómoda. **ENAHO Hub** "
        "ordena esa data pública y te ahorra el trabajo: explora los módulos con su sinopsis, "
        "busca entre miles de variables y mira dónde aparecen, grafica al vuelo y descarga "
        "las bases listas para Stata, Python o SPSS. La metadata se sirve offline, así que "
        "la demo no depende de que INEI esté arriba."
    )
    cob = resumen.get("cobertura_total", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Colecciones", len(cob.get("colecciones", [])))
    c2.metric("Cobertura", f"{cob.get('anio_min','?')}-{cob.get('anio_max','?')}")
    c3.metric("Variables (demo)", f"{resumen.get('variables_unicas', 0):,}")
    c4.metric("Módulos (demo)", resumen.get("n_modulos", 0))
    st.caption(
        f"Demo activa: ENAHO {', '.join(resumen.get('alcance_demo', []))}. "
        f"Las métricas de variables y módulos corresponden a este alcance; la cobertura "
        f"total del catálogo es {cob.get('anio_min','?')}-{cob.get('anio_max','?')}."
    )
    st.divider()
    st.markdown(
        "**El producto no es la data (es pública): es la capa que la ordena y el tiempo que "
        "ahorra.** Modelo B2B por cuentas institucionales."
    )


# --- Pestaña 2: Explorador de modulos ---------------------------------------
def tab_modulos(modulos):
    st.header("Explorador de módulos")
    if not modulos:
        st.warning("No hay módulos horneados.")
        return
    c1, c2 = st.columns(2)
    with c1:
        col = st.selectbox("Colección", sorted(modulos.keys()), key="exp_col")
    with c2:
        anio = st.selectbox("Año", sorted(modulos[col].keys()), key="exp_anio")
    nodo = modulos[col][anio]
    docs = [d for d in nodo.get("docs", []) if d.get("url")
            and any(p in (d.get("doc_name") or "") for p in ("Diccionario", "Ficha", "Cuestionario"))]
    if docs:
        with st.expander(f"Documentación de {col} {anio} (diccionarios, fichas, cuestionarios)"):
            for d in docs:
                st.markdown(f"- [{d['doc_name']}]({d['url']})")
    st.caption(f"{len(nodo['modulos'])} módulos. Cada uno con su sinopsis y formatos.")
    for m in nodo["modulos"]:
        with st.expander(f"{m['modulo_code']} · {m['module_name']}"):
            st.write(sinopsis_de(m["module_name"]))
            if m.get("formatos"):
                st.write("**Formatos disponibles:** " + ", ".join(m["formatos"]))


# --- Pestaña 3: Diccionario de variables (navegacion progresiva) ------------
def tab_diccionario(df, cuest, modulos):
    st.header("Diccionario de variables")
    st.caption("Elige una colección y un módulo; aparecen sus variables. Al seleccionar una, "
               "verás su ficha y, a la derecha, la página exacta del cuestionario.")
    c1, c2 = st.columns(2)
    with c1:
        col = st.selectbox("Colección", sorted(df["coleccion"].unique()), key="dic_col")
    sub_col = df[df["coleccion"] == col]
    mods = sub_col[["modulo_code", "modulo"]].drop_duplicates().sort_values("modulo_code")
    opciones = list(mods.itertuples(index=False, name=None))
    with c2:
        mod_sel = st.selectbox("Módulo", opciones, key=f"dic_mod_{col}",
                               format_func=lambda t: f"{t[0]} · {t[1]}")
    modulo_code, modulo_nombre = mod_sel
    st.caption(sinopsis_de(modulo_nombre))

    sub_mod = sub_col[sub_col["modulo_code"] == modulo_code]
    q = st.text_input("Filtrar variables del módulo (opcional)",
                      placeholder="nombre o etiqueta, ej. ingreso", key=f"dic_q_{modulo_code}")
    if q:
        ql = q.lower()
        sub_mod = sub_mod[sub_mod["variable"].str.lower().str.contains(ql, na=False)
                          | sub_mod["etiqueta"].fillna("").str.lower().str.contains(ql, na=False)]
    sub_mod = sub_mod.drop_duplicates("variable")
    if sub_mod.empty:
        st.warning("Sin variables que coincidan.")
        return

    mapeadas = set()
    for a in sub_mod["anio"].unique():
        mapeadas |= set((cuest.get(col, {}).get(a, {}).get(modulo_code, {}) or {}).keys())
    etiquetas = dict(zip(sub_mod["variable"], sub_mod["etiqueta"].fillna("")))
    n_map = len(mapeadas & set(sub_mod["variable"]))
    st.caption(f"{len(sub_mod):,} variables en este módulo. El icono 📄 marca las que tienen "
               f"página de cuestionario mapeada ({n_map} aquí).")

    def _fmt(v):
        marca = "📄 " if v in mapeadas else ""
        et = etiquetas.get(v, "")
        return f"{marca}{v}  ·  {et[:70]}" if et else f"{marca}{v}"

    opciones_var = sub_mod["variable"].tolist()
    idx_def = next((i for i, v in enumerate(opciones_var) if v in mapeadas), 0)
    var_sel = st.selectbox("Variable", opciones_var, index=idx_def, format_func=_fmt,
                           key=f"dic_var_{modulo_code}_{q}")
    fila = sub_mod[sub_mod["variable"] == var_sel].iloc[0]

    izq, der = st.columns([2, 3])
    with izq:
        st.markdown(f"### `{var_sel}`")
        st.write(fila["etiqueta"] or "(sin etiqueta)")
        st.write(f"**Módulo:** {fila['modulo']}  ({modulo_code})")
        st.write(f"**Colección:** {col}")
        st.write(f"**Año:** {fila['anio']}   ·   **Registros del módulo:** {fila['n_filas']:,}")
        vals_raw = fila.get("valores")
        if vals_raw:
            try:
                vals = json.loads(vals_raw)
            except Exception:
                vals = None
            if vals:
                st.markdown("**Valores (códigos):**")
                st.dataframe(pd.DataFrame({"Código": [_cod_valor(k) for k in vals],
                                          "Etiqueta": list(vals.values())}),
                             hide_index=True, use_container_width=True)
        otros = [m for m in df[df["variable"] == var_sel]["modulo"].drop_duplicates().tolist()
                 if m != fila["modulo"]]
        if otros:
            st.caption("También aparece en: " + ", ".join(otros))
    with der:
        _visor_cuestionario(cuest, modulos, col, fila["anio"], modulo_code, var_sel)


# --- Pestaña 4: Graficador --------------------------------------------------
@st.cache_data
def _meta_modulo(coleccion, anio, modulo_code):
    """{nombre_columna_lower: (etiqueta, valores_dict|None)} del módulo, desde el parquet."""
    df = cargar_variables()
    sub = df[(df["coleccion"] == coleccion) & (df["anio"] == anio)
             & (df["modulo_code"] == modulo_code)]
    out = {}
    for _, r in sub.iterrows():
        vals = None
        if r["valores"]:
            try:
                vals = json.loads(r["valores"])
            except Exception:
                vals = None
        out[str(r["variable"]).lower()] = (r["etiqueta"], vals)
    return out


def _grafico(df, meta):
    if df.empty:
        st.warning("La base llegó vacía.")
        return

    def etq(col):
        e = meta.get(str(col).lower(), (None, None))[0]
        return f"{e}  ·  {col}" if e else str(col)

    def tiene_codigos(col):
        return meta.get(str(col).lower(), (None, None))[1] is not None

    cols = df.columns.tolist()
    num_cols = df.select_dtypes("number").columns.tolist()
    # Eje X: primero las variables con códigos etiquetados (son las categorías naturales).
    x_op = [c for c in cols if tiene_codigos(c)] + [c for c in cols if not tiene_codigos(c)]
    # Eje Y: primero las numéricas continuas (sin códigos), como ingreso u horas.
    y_op = [c for c in num_cols if not tiene_codigos(c)] + [c for c in num_cols if tiene_codigos(c)]

    c1, c2 = st.columns(2)
    with c1:
        x = st.selectbox("Eje X (categoría)", x_op, format_func=etq, key="graf_x")
    with c2:
        op = st.selectbox("Eje Y (qué medir)",
                          ["Número de casos", "Promedio", "Suma", "Mediana"], key="graf_op")
    y = None
    if op != "Número de casos":
        if not y_op:
            st.warning("La tabla no tiene variables numéricas para el eje Y.")
            return
        y = st.selectbox("Variable numérica (Eje Y)", y_op, format_func=etq, key="graf_y")

    # Mapear los códigos del eje X a sus etiquetas (1 -> Hombre, 2 -> Mujer, ...).
    xvals = meta.get(str(x).lower(), (None, None))[1]
    xmap = {_cod_valor(k): v for k, v in xvals.items()} if xvals else {}

    def cat(v):
        if pd.isna(v):
            return None
        etiqueta = xmap.get(_cod_valor(v), str(v)) if xmap else str(v)
        return str(etiqueta).strip() or None  # descarta vacíos y espacios en blanco

    tmp = pd.DataFrame({"cat": df[x].map(cat)})
    if op == "Número de casos":
        serie = tmp.dropna(subset=["cat"]).groupby("cat").size()
        ylabel = "Número de casos"
    else:
        tmp["y"] = pd.to_numeric(df[y], errors="coerce")
        g = tmp.dropna(subset=["cat", "y"]).groupby("cat")["y"]
        serie = {"Promedio": g.mean(), "Suma": g.sum(), "Mediana": g.median()}[op]
        ylabel = f"{op} de {etq(y)}"
    if serie.empty:
        st.warning("No hay datos para esa combinación.")
        return
    serie = serie.sort_values(ascending=False).head(30)
    serie.index = serie.index.astype(str)
    serie.name = ylabel
    st.bar_chart(serie, x_label=etq(x), y_label=ylabel)
    st.caption(f"{ylabel} por «{etq(x)}» (hasta 30 categorías).")


def tab_graficador(idx):
    st.header("Graficador")
    st.caption("Descarga la base de INEI en vivo (cacheada) y grafica por ejes legibles.")
    sel = selector_modulo(idx, "graf")
    if not sel:
        return
    if st.button("Cargar base de INEI", key="graf_cargar"):
        st.session_state["graf_sel"] = sel
    selg = st.session_state.get("graf_sel")
    if not selg:
        return
    try:
        tablas = leer_modulo(selg["code"])
    except Exception as e:
        st.error(f"No se pudo descargar la base desde INEI: {e}. "
                 "Reintenta o verifica tu conexión; el portal de INEI puede estar caído.")
        return
    if not tablas:
        st.warning("La base llegó vacía.")
        return
    nombre_tabla = st.selectbox("Tabla", list(tablas.keys()), key="graf_tabla")
    df = tablas[nombre_tabla]
    st.caption(f"{df.shape[0]:,} filas x {df.shape[1]} columnas. "
               "Elige una categoría (Eje X) y qué medir (Eje Y).")
    meta = _meta_modulo(selg["coleccion"], selg["anio"], selg["modulo_code"])
    _grafico(df, meta)


# --- Pestaña 5: Descargas ---------------------------------------------------
def _exportar(df, fmt):
    if fmt == "CSV":
        return df.to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv"
    if fmt == "Parquet (Python)":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return buf.getvalue(), "application/octet-stream", "parquet"
    if fmt == "Stata (.dta)":
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "base.dta")
            df.to_stata(p, write_index=False, version=118)
            with open(p, "rb") as fh:
                return fh.read(), "application/octet-stream", "dta"
    if fmt == "SPSS (.sav)":
        import pyreadstat
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "base.sav")
            pyreadstat.write_sav(df, p)
            with open(p, "rb") as fh:
                return fh.read(), "application/octet-stream", "sav"
    raise ValueError(fmt)


def tab_descargas(idx):
    st.header("Descargas")
    st.caption("Descarga la base lista para tu herramienta: Stata, SPSS, Python o CSV.")
    sel = selector_modulo(idx, "desc")
    if not sel:
        return
    if st.button("Cargar base de INEI", key="desc_cargar"):
        st.session_state["desc_code"] = sel["code"]
    code = st.session_state.get("desc_code")
    if not code:
        return
    try:
        tablas = leer_modulo(code)
    except Exception as e:
        st.error(f"No se pudo descargar la base desde INEI: {e}. "
                 "Reintenta o verifica tu conexión; el portal de INEI puede estar caído.")
        return
    if not tablas:
        st.warning("La base llegó vacía.")
        return
    nombre_tabla = st.selectbox("Tabla", list(tablas.keys()), key="desc_tabla")
    df = tablas[nombre_tabla]
    st.caption(f"{df.shape[0]:,} filas x {df.shape[1]} columnas.")
    fmt = st.selectbox("Formato", ["CSV", "Stata (.dta)", "SPSS (.sav)", "Parquet (Python)"],
                       key="desc_fmt")
    try:
        datos, mime, ext = _exportar(df, fmt)
        st.download_button(f"Descargar {nombre_tabla}.{ext}", data=datos,
                           file_name=f"{nombre_tabla}.{ext}", mime=mime)
    except Exception as e:
        st.error(f"No se pudo exportar a {fmt}: {e}. Prueba con CSV.")


# --- Main -------------------------------------------------------------------
def main():
    resumen = cargar_resumen()
    modulos = cargar_modulos()
    df = cargar_variables()
    cuest = cargar_cuestionarios()
    idx = indice_descarga(tuple(sorted(resumen.get("alcance_demo", []))))

    institucion = sidebar_institucion()

    t1, t2, t3, t4, t5 = st.tabs(
        ["Inicio", "Explorador de módulos", "Diccionario de variables",
         "Graficador", "Descargas"])
    with t1:
        tab_inicio(resumen, institucion)
    with t2:
        tab_modulos(modulos)
    with t3:
        tab_diccionario(df, cuest, modulos)
    with t4:
        tab_graficador(idx)
    with t5:
        tab_descargas(idx)


if __name__ == "__main__":
    main()
