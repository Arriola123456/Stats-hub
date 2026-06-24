"""Hornea la capa de metadata offline de ENAHO en data/.

Corre una sola vez y sin tocar la red: lee el catalogo y el indice de variables
empaquetados en inei-microdatos y genera tres archivos pre-horneados que la app sirve
sin depender de que INEI este arriba:
  - data/enaho_modulos.json.gz   modulos por coleccion y anio, con formatos y enlaces.
  - data/enaho_variables.parquet tabla larga buscable de variables.
  - data/enaho_resumen.json      conteos globales para las metricas de Inicio.

Alcance de esta demo: solo el/los anios en ANIOS. Para ampliar, edita ANIOS.
"""
import gzip
import json
import os
import sys

import pandas as pd
import inei_microdatos as im
from inei_microdatos import load_catalog
from inei_microdatos.catalog import filter_catalog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import fix_encoding, coleccion, normaliza_modulo  # noqa: E402

# --- Alcance de la demo -----------------------------------------------------
ANIOS = ["2024"]  # ampliar aqui para hornear mas anios

# --- Rutas ------------------------------------------------------------------
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
os.makedirs(DATA, exist_ok=True)

DOCS_BASE = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/DocumentosZIP/"


def formatos_de(m):
    """Formatos disponibles de un modulo segun que *_code no sea None."""
    pares = [("CSV", m.get("csv_code")), ("STATA", m.get("stata_code")), ("SPSS", m.get("spss_code"))]
    return [nombre for nombre, code in pares if code]


def construir_modulos(enaho):
    """coleccion -> anio -> {modulos:[...], docs:[...]}, fusionando periodos del anio."""
    salida = {}
    for e in enaho:
        val = e.get("value")
        for anio, periodos in (e.get("years") or {}).items():
            if anio not in ANIOS:
                continue
            col = coleccion(e.get("category"), val)
            nodo = salida.setdefault(col, {}).setdefault(anio, {"modulos": [], "docs": []})
            vistos_mod = {m["module_name"] for m in nodo["modulos"]}
            vistos_doc = {(d["doc_name"], d["url"]) for d in nodo["docs"]}
            for _periodo, pdata in (periodos or {}).items():
                for m in pdata.get("modules", []):
                    nombre = fix_encoding(m.get("module_name"))
                    if nombre in vistos_mod:
                        continue
                    vistos_mod.add(nombre)
                    nodo["modulos"].append({
                        "modulo_code": normaliza_modulo(m.get("module_code")),
                        "module_name": nombre,
                        "formatos": formatos_de(m),
                    })
                for d in pdata.get("docs", []):
                    zp = d.get("zip_path")
                    url = (DOCS_BASE + zp) if zp else None
                    nombre = fix_encoding(d.get("doc_name"))
                    if (nombre, url) in vistos_doc:
                        continue
                    vistos_doc.add((nombre, url))
                    nodo["docs"].append({"doc_name": nombre, "url": url})
    return salida


def construir_variables():
    """Tabla larga: una fila por variable y bloque (modulo-anio-coleccion)."""
    idx_path = os.path.join(os.path.dirname(im.__file__), "data", "variable_index.json.gz")
    with gzip.open(idx_path, "rt", encoding="utf-8") as f:
        bloques = json.load(f)
    filas = []
    for b in bloques:
        survey = b.get("survey") or ""
        if "ENAHO" not in survey.upper():
            continue
        if str(b.get("year")) not in ANIOS:
            continue
        col = coleccion(b.get("category"), survey)
        modcode = normaliza_modulo(b.get("module_code"))
        modname = fix_encoding(b.get("module_name"))
        nrows = b.get("n_rows")
        anio = str(b.get("year"))
        for v in b.get("variables", []):
            vals = v.get("values")
            filas.append({
                "variable": v.get("name"),
                "etiqueta": fix_encoding(v.get("label")),
                "modulo": modname,
                "modulo_code": modcode,
                "coleccion": col,
                "anio": anio,
                "n_filas": nrows,
                "valores": json.dumps(vals, ensure_ascii=False) if vals else None,
            })
    return pd.DataFrame(filas)


def cobertura_total(enaho):
    """Colecciones y rango de anios de TODO el catalogo ENAHO (para el pitch de Inicio)."""
    cols, anios = set(), set()
    for e in enaho:
        for anio in (e.get("years") or {}):
            cols.add(coleccion(e.get("category"), e.get("value")))
            if str(anio).isdigit():
                anios.add(int(anio))
    return {
        "colecciones": sorted(cols),
        "anio_min": min(anios) if anios else None,
        "anio_max": max(anios) if anios else None,
    }


def main():
    cat = load_catalog()
    enaho = filter_catalog(cat, survey="enaho")

    modulos = construir_modulos(enaho)
    # gzip determinista (mtime=0) para no generar diffs espurios al re-hornear.
    crudo = json.dumps(modulos, ensure_ascii=False).encode("utf-8")
    with open(os.path.join(DATA, "enaho_modulos.json.gz"), "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(crudo)

    df = construir_variables()
    df.to_parquet(os.path.join(DATA, "enaho_variables.parquet"), index=False)

    try:
        from inei_microdatos.catalog import catalog_age
        fecha_cat = str(catalog_age())
    except Exception:
        fecha_cat = None

    variables_unicas = int(df["variable"].str.lower().nunique()) if not df.empty else 0
    resumen = {
        "alcance_demo": ANIOS,
        "colecciones": sorted(modulos.keys()),
        "anios_por_coleccion": {c: sorted(modulos[c].keys()) for c in modulos},
        "n_modulos": sum(len(modulos[c][a]["modulos"]) for c in modulos for a in modulos[c]),
        "variables_unicas": variables_unicas,
        "filas": int(len(df)),
        "cobertura_total": cobertura_total(enaho),
        "fecha_catalogo": fecha_cat,
    }
    with open(os.path.join(DATA, "enaho_resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    print("OK metadata (alcance", ANIOS, "):")
    print("  colecciones:", resumen["colecciones"])
    print("  modulos:", resumen["n_modulos"])
    print("  filas (apariciones var x modulo):", resumen["filas"])
    print("  variables unicas:", resumen["variables_unicas"])
    print("  cobertura total catalogo:", resumen["cobertura_total"])
    if not df.empty:
        print("  muestra modulos:", df["modulo"].dropna().unique()[:6].tolist())


if __name__ == "__main__":
    main()
