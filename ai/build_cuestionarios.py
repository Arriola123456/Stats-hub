"""Mapea cada variable a la página de su cuestionario (MVP: módulos 100-500 y 34, 2024).

Descarga los cuestionarios de INEI en vivo, extrae el texto por página con pdfplumber
(pymupdf como respaldo si pdfplumber no esta disponible; PaddleOCR como fallback OCR solo
cuando una página escaneada no da texto) y mapea cada variable a su pregunta por el número:
p301 -> pregunta 301. Como las preguntas van en orden creciente a lo largo del cuestionario,
se construyen anclas (número de pregunta -> página) por formulario, limpiando outliers
(códigos y referencias sueltas) con una subsecuencia monótona, y se interpola la página de
cada pregunta entre las anclas que la rodean (ENAHO.01 cubre la vivienda 100; ENAHO.01A la
educación 300, salud 400 y empleo 500). Si la pregunta cae fuera del rango o en un hueco
grande (por ejemplo el roster del módulo 200, que va en una grilla que el PDF no expone como
texto), queda sin mapear y la app ofrece el cuestionario completo. La Sumaria (módulo 34) y
las variables derivadas no tienen pregunta: quedan sin cuestionario.

Salida data/cuestionario_paginas.json:
  { coleccion: { anio: { modulo_code: { variable: {forma, pdf, pagina} } } } }

El mapeo por número de pregunta es heurístico y no 1:1; los casos dudosos (sin página o
con la pregunta en muchas páginas) se reportan al final en vez de inventar una página.
Los PDFs y ZIPs quedan fuera de git (data/cuestionarios/); solo se versiona el JSON y, si
es pequeño, un PDF de muestra (data/cuestionario_muestra.pdf).
"""
import copy
import glob
import json
import os
import re
import shutil
import sys
import zipfile

import pandas as pd
from inei_microdatos import load_catalog, download_docs
from inei_microdatos.catalog import filter_catalog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import COL_ACTUALIZADA  # noqa: E402

# --- Alcance del MVP --------------------------------------------------------
ANIOS = ["2024"]
MODULOS_MVP = {"Modulo01", "Modulo02", "Modulo03", "Modulo04", "Modulo05", "Modulo34"}
# Formularios de cuestionario a descargar para el MVP (cubren los módulos 100-500).
FORMAS_NECESARIAS = {"01", "01A"}

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
CUEST = os.path.join(DATA, "cuestionarios")  # fuera de git
os.makedirs(CUEST, exist_ok=True)

_OCR = None


def forma_de_pdf(nombre):
    """Devuelve '01A' / '01B' / '01' segun el nombre del archivo o doc; None si no aplica."""
    u = re.sub(r"[^A-Z0-9]", "", (nombre or "").upper())
    for f in ("01A", "01B", "01"):  # los sufijos antes que '01' a secas
        if "ENAHO" + f in u:
            return f
    return None


def construir_catalogo_docs(enaho):
    """Recorta el catalogo a los docs de cuestionario (formas necesarias, anio MVP)."""
    salida = []
    for e in enaho:
        if "PANEL" in (e.get("value") or "").upper():
            continue
        if (e.get("category") or "") != "ENAHO Actualizada":
            continue
        years = {}
        for anio, periodos in (e.get("years") or {}).items():
            if anio not in ANIOS:
                continue
            nper = {}
            for periodo, pdata in periodos.items():
                docs = [d for d in pdata.get("docs", [])
                        if (d.get("doc_name") or "").startswith("Cuestionario")
                        and forma_de_pdf(d.get("doc_name")) in FORMAS_NECESARIAS]
                if docs:
                    p2 = copy.deepcopy(pdata)
                    p2["modules"] = []
                    p2["docs"] = docs
                    nper[periodo] = p2
            if nper:
                years[anio] = nper
        if years:
            nuevo = copy.deepcopy(e)
            nuevo["years"] = years
            salida.append(nuevo)
    return salida


def descargar(cat_docs):
    try:
        res = download_docs(cat_docs, CUEST, progress=False)
        print("download_docs:", res)
        return True
    except Exception as e:
        print("ERROR descargando cuestionarios de INEI:", e)
        print("Se continua sin PDFs; el mapeo quedara vacio y la app usara los enlaces.")
        return False


def extraer_pdfs():
    """Descomprime los ZIP descargados y devuelve {forma: ruta_pdf}."""
    destino = os.path.join(CUEST, "extract")
    os.makedirs(destino, exist_ok=True)
    for z in glob.glob(os.path.join(CUEST, "**", "*.zip"), recursive=True):
        try:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(destino)
        except zipfile.BadZipFile:
            print("ZIP invalido, se omite:", os.path.basename(z))
    pdfs = {}
    for p in sorted(glob.glob(os.path.join(destino, "**", "*.pdf"), recursive=True)):
        f = forma_de_pdf(os.path.basename(p))
        if f and f not in pdfs:
            pdfs[f] = p
    return pdfs


def ocr_imagen(img):
    """Fallback OCR con PaddleOCR (opcional). Devuelve '' si PaddleOCR no esta disponible.

    Solo se invoca cuando una página no da texto (PDF escaneado), caso poco frecuente en
    los cuestionarios ENAHO 2022+, que suelen traer capa de texto.
    """
    global _OCR
    try:
        import numpy as np
        from paddleocr import PaddleOCR
    except Exception:
        return ""
    try:
        if _OCR is None:
            _OCR = PaddleOCR(use_angle_cls=False, lang="es", show_log=False)
        res = _OCR.ocr(np.array(img))
        lineas = []
        for bloque in (res or []):
            for item in (bloque or []):
                lineas.append(item[1][0])
        return "\n".join(lineas)
    except Exception:
        return ""


def texto_por_pagina(ruta_pdf):
    """Texto por página. pdfplumber primero; pymupdf (fitz) como respaldo."""
    try:
        import pdfplumber
        paginas = []
        with pdfplumber.open(ruta_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if not t.strip():
                    t = ocr_imagen(page.to_image(resolution=150).original)
                paginas.append(t)
        return paginas, "pdfplumber"
    except ImportError:
        pass
    import fitz
    from PIL import Image
    paginas = []
    doc = fitz.open(ruta_pdf)
    for page in doc:
        t = page.get_text() or ""
        if not t.strip():
            pix = page.get_pixmap(dpi=150)
            t = ocr_imagen(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        paginas.append(t)
    doc.close()
    return paginas, "pymupdf"


# Pregunta al inicio de linea: 3 digitos + letra opcional (106, 106A). Prefijo P/Nº opcional.
ANCLA_RE = re.compile(r"(?m)^\s*(?:P\.?\s*|N[ºo°]\.?\s*|Pregunta\s*)?0*(\d{3})([A-Za-z]?)(?![A-Za-z\d])")
# Roster de miembros (modulo 200) en grillas: 2xx + letra opcional, en cualquier lado.
ROSTER_RE = re.compile(r"\b(2[0-2]\d)([A-Za-z]?)(?![A-Za-z\d])")
GAP_MAX = 2500  # hueco maximo entre claves (= 25 numeros de pregunta) para interpolar


def clave(num, letra=""):
    """Clave ordenable de una pregunta: 106 -> 10600, 106A -> 10601, 107 -> 10700.

    Mete la letra en el orden (A=1..Z=26) para que 106 < 106A < 106B < 107.
    """
    return int(num) * 100 + (ord(letra.upper()) - 64 if letra else 0)


def _lnds(seq):
    """Indices de la subsecuencia no decreciente mas larga (para descartar outliers)."""
    n = len(seq)
    if n == 0:
        return []
    dp = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] <= seq[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                prev[i] = j
    best = max(range(n), key=lambda i: dp[i])
    out = []
    while best != -1:
        out.append(best)
        best = prev[best]
    return out[::-1]


def construir_anclas(paginas):
    """Anclas (clave_pregunta -> pagina) monotonas y limpias de un formulario.

    Toma las preguntas (3 digitos + letra opcional, >=100) que abren linea, mas las 2xx del
    roster de miembros (que va en grillas), las convierte a su clave ordenable y se queda con
    la cadena monotona mas larga (la clave crece con la pagina), descartando codigos y
    referencias fuera de orden. Devuelve (clave, pagina) ordenada por clave, sin repetidas.
    """
    pts = []
    for i, t in enumerate(paginas):
        if not t:
            continue
        crudos = set(ANCLA_RE.findall(t)) | set(ROSTER_RE.findall(t))
        for num, letra in crudos:
            if int(num) >= 100:
                pts.append((clave(num, letra), i + 1))
    pts.sort()  # por clave, luego pagina
    anclas = [pts[i] for i in _lnds([p for _, p in pts])]
    salida = []
    for cl, pag in anclas:
        if not salida or salida[-1][0] != cl:
            salida.append((cl, pag))
    return salida


def ubicar(cl_q, anclas_por_forma):
    """Mejor (forma, pagina, aprox) para la clave de pregunta 'cl_q' segun las anclas.

    Interpola la pagina entre las anclas que rodean a la pregunta (van en orden). Solo mapea
    si la clave cae dentro del rango de un formulario y el hueco entre anclas es pequeno; si
    no, no inventa. 'aprox' es True cuando la pagina es interpolada.
    """
    mejor = None  # (gap, forma, pagina, aprox)
    for forma, anclas in anclas_por_forma.items():
        if not anclas or cl_q < anclas[0][0] or cl_q > anclas[-1][0]:
            continue
        exacta = next((p for c, p in anclas if c == cl_q), None)
        if exacta is not None:
            cand = (0, forma, exacta, False)
        else:
            c_lo, p_lo = [(c, p) for c, p in anclas if c < cl_q][-1]
            c_hi, p_hi = [(c, p) for c, p in anclas if c > cl_q][0]
            gap = c_hi - c_lo
            if gap > GAP_MAX:
                continue
            pagina = round(p_lo + (cl_q - c_lo) / (c_hi - c_lo) * (p_hi - p_lo))
            cand = (gap, forma, pagina, True)
        if mejor is None or cand[0] < mejor[0]:
            mejor = cand
    if mejor is None:
        return None, None, None
    return mejor[1], mejor[2], mejor[3]


def copiar_muestra(pdfs, salida):
    """Versiona el PDF mas pequeno como muestra (si pesa <= 2 MB) y lo registra en el JSON."""
    if not pdfs:
        return
    forma, ruta = min(pdfs.items(), key=lambda kv: os.path.getsize(kv[1]))
    if os.path.getsize(ruta) <= 2_000_000:
        shutil.copyfile(ruta, os.path.join(DATA, "cuestionario_muestra.pdf"))
        salida["_muestra"] = {"forma": "ENAHO." + forma, "pdf": "cuestionario_muestra.pdf"}
        print("muestra versionada:", "ENAHO." + forma,
              os.path.getsize(ruta) // 1024, "KB")
    else:
        print("PDF de muestra omitido (el mas pequeno supera 2 MB)")


def main():
    enaho = filter_catalog(load_catalog(), survey="enaho")
    cat_docs = construir_catalogo_docs(enaho)
    print("docs de cuestionario a descargar:",
          [d["doc_name"] for e in cat_docs for y in e["years"].values()
           for p in y.values() for d in p["docs"]])

    ok = descargar(cat_docs) if cat_docs else False
    pdfs = extraer_pdfs() if ok else {}

    textos = {}
    for f, ruta in pdfs.items():
        try:
            textos[f], motor = texto_por_pagina(ruta)
            print(f"forma ENAHO.{f}: {len(textos[f])} paginas ({motor}) "
                  f"<- {os.path.basename(ruta)}")
        except Exception as e:
            print("error leyendo ENAHO." + f, e)

    anclas_por_forma = {f: construir_anclas(textos[f]) for f in textos}
    for f, a in anclas_por_forma.items():
        rango = f"{a[0][0] // 100}..{a[-1][0] // 100}" if a else "sin anclas"
        print(f"forma ENAHO.{f}: {len(a)} anclas (preguntas {rango})")

    df = pd.read_parquet(os.path.join(DATA, "enaho_variables.parquet"))
    sub = df[(df.coleccion == COL_ACTUALIZADA) & (df.anio.isin(ANIOS))
             & (df.modulo_code.isin(MODULOS_MVP))].drop_duplicates(["modulo_code", "variable"])

    salida = {}
    stats = {"mapeadas": 0, "aprox": 0, "sin_pregunta": 0, "no_mapeadas": 0}
    memo = {}
    re_p = re.compile(r"^[pP](\d{3})([A-Za-z])?")
    for _, row in sub.iterrows():
        var, mod = row["variable"], row["modulo_code"]
        m = re_p.match(str(var))
        if not m:
            stats["sin_pregunta"] += 1
            continue
        cl_q = clave(m.group(1), m.group(2) or "")
        if cl_q not in memo:
            memo[cl_q] = ubicar(cl_q, anclas_por_forma)
        forma, pag, aprox = memo[cl_q]
        if pag is None:
            stats["no_mapeadas"] += 1
            continue
        salida.setdefault(COL_ACTUALIZADA, {}).setdefault("2024", {}).setdefault(mod, {})[var] = {
            "forma": "ENAHO." + forma,
            "pdf": os.path.relpath(pdfs[forma], DATA).replace("\\", "/"),
            "pagina": int(pag),
            "aprox": bool(aprox),
        }
        stats["mapeadas"] += 1
        if aprox:
            stats["aprox"] += 1

    copiar_muestra(pdfs, salida)
    with open(os.path.join(DATA, "cuestionario_paginas.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    print("STATS:", stats)
    nodo = salida.get(COL_ACTUALIZADA, {}).get("2024", {})
    for mod in sorted(nodo):
        ej = [(v, d["pagina"], "aprox" if d["aprox"] else "exacta")
              for v, d in list(nodo[mod].items())[:3]]
        print(f"  {mod}: {len(nodo[mod])} mapeadas; ej: {ej}")


if __name__ == "__main__":
    main()
