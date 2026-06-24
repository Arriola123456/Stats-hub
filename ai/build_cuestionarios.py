"""Mapea cada variable a la página de su cuestionario (MVP: módulos 100-500 y 34, 2024).

Descarga los cuestionarios de INEI en vivo, extrae el texto por página con pdfplumber
(pymupdf como respaldo si pdfplumber no esta disponible; PaddleOCR como fallback OCR solo
cuando una página escaneada no da texto) y mapea cada variable a su pregunta por el número:
p301 -> pregunta 301, que se busca entre los formularios descargados (para el MVP,
ENAHO.01 con la vivienda 100 y ENAHO.01A con educación 300, salud 400 y empleo 500). Si la
pregunta aparece con claridad se mapea su página; si no (por ejemplo el roster del módulo
200, que va en una grilla que el PDF no expone como texto), la variable queda sin mapear y
la app ofrece el cuestionario completo. La Sumaria (módulo 34) y las variables derivadas no
tienen pregunta: quedan sin cuestionario.

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


def localizar(num, textos):
    """Ubica la pregunta 'num' entre todos los formularios disponibles (alta precisión).

    Prefiere una coincidencia fuerte (el número abre una línea: contexto de pregunta). Si no
    hay fuerte pero sí una única coincidencia débil, la toma. Si la pregunta aparece suelta
    en muchas páginas, o con fuerza en más de un formulario, no inventa: la deja sin mapear.
    Devuelve (forma, pagina, tipo) con tipo en {fuerte, unico, ambiguo, ausente}.
    """
    inicio = re.compile(r"(?m)^\s*(?:P\.?\s*|N[ºo°]\s*|Pregunta\s*)?0*%s\b" % re.escape(num))
    suelto = re.compile(r"(?<!\d)0*%s(?!\d)" % re.escape(num))
    fuertes, debiles = [], []
    for forma, paginas in textos.items():
        for i, t in enumerate(paginas):
            if not t:
                continue
            if inicio.search(t):
                fuertes.append((forma, i + 1))
            elif suelto.search(t):
                debiles.append((forma, i + 1))
    if fuertes:
        if len({f for f, _ in fuertes}) == 1:  # todas las fuertes en un mismo formulario
            return fuertes[0][0], fuertes[0][1], "fuerte"
        return None, None, "ambiguo"  # pregunta fuerte en varios formularios
    if len(debiles) == 1:
        return debiles[0][0], debiles[0][1], "unico"
    return None, None, ("ambiguo" if debiles else "ausente")


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

    df = pd.read_parquet(os.path.join(DATA, "enaho_variables.parquet"))
    sub = df[(df.coleccion == COL_ACTUALIZADA) & (df.anio.isin(ANIOS))
             & (df.modulo_code.isin(MODULOS_MVP))].drop_duplicates(["modulo_code", "variable"])

    salida = {}
    stats = {"mapeadas": 0, "sin_pregunta": 0, "no_mapeadas": 0, "dudosas": 0}
    dudosas = []
    memo = {}
    re_p = re.compile(r"^p(\d{3})", re.IGNORECASE)
    for _, row in sub.iterrows():
        var, mod = row["variable"], row["modulo_code"]
        m = re_p.match(str(var))
        if not m:
            stats["sin_pregunta"] += 1
            continue
        num = m.group(1)
        if num not in memo:
            memo[num] = localizar(num, textos)
        forma, pag, tipo = memo[num]
        if pag is None:
            stats["no_mapeadas"] += 1
            if tipo == "ambiguo":
                stats["dudosas"] += 1
                dudosas.append((mod, var, num, "ambigua, sin pagina"))
            continue
        salida.setdefault(COL_ACTUALIZADA, {}).setdefault("2024", {}).setdefault(mod, {})[var] = {
            "forma": "ENAHO." + forma,
            "pdf": os.path.relpath(pdfs[forma], DATA).replace("\\", "/"),
            "pagina": pag,
        }
        stats["mapeadas"] += 1

    copiar_muestra(pdfs, salida)
    with open(os.path.join(DATA, "cuestionario_paginas.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    print("STATS:", stats)
    if dudosas:
        print(f"casos dudosos ({len(dudosas)}), muestra:")
        for d in dudosas[:30]:
            print("  ", d)


if __name__ == "__main__":
    main()
