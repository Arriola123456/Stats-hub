"""Hornea indicadores reales de la ENAHO 2024 en data/indicadores.json.

Corre una sola vez al build: descarga la Sumaria (módulo 34) de ENAHO 2024, calcula
indicadores ponderados con el factor de expansión (pobreza, pobreza extrema, ingreso y
gasto del hogar) a nivel nacional, por dominio geográfico y por área (urbano/rural), y los
guarda para que el app los sirva OFFLINE sin tocar la red. Ampliar ANIOS y re-hornear daría
otros años.

El CSV de la Sumaria viene en latin-1 y el zip trae una versión separada por comas y otra
por punto y coma; se lee directamente (no con read_module, que se confunde de delimitador),
prefiriendo el de comas porque usa el punto como separador decimal.
"""
import copy
import glob
import json
import os
import sys
import tempfile
import zipfile

import pandas as pd
from inei_microdatos import download_modules, load_catalog
from inei_microdatos.catalog import filter_catalog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import normaliza_modulo  # noqa: E402

ANIOS = ["2024"]
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
ORDEN_DOMINIO = ["1", "2", "3", "4", "5", "6", "7", "8"]  # orden geográfico del codebook
REQUERIDAS = {"pobreza", "factor07", "dominio", "inghog1d", "gashog2d", "mieperho", "estrato",
              "ubigeo"}
# Código de departamento (2 primeros dígitos del ubigeo) -> nombre.
DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho",
    "06": "Cajamarca", "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco",
    "11": "Ica", "12": "Junín", "13": "La Libertad", "14": "Lambayeque", "15": "Lima",
    "16": "Loreto", "17": "Madre de Dios", "18": "Moquegua", "19": "Pasco", "20": "Piura",
    "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes", "25": "Ucayali",
}


def _cod(v):
    """Normaliza un código de valor ('1.0' o 1.0 -> '1')."""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(v)
    except (TypeError, ValueError):
        return str(v)


def descargar_sumaria(enaho):
    """Descarga la Sumaria (Modulo34) de ENAHO Actualizada (ANIOS) y devuelve la ruta del zip."""
    entrada = None
    for e in enaho:
        if "PANEL" in (e.get("value") or "").upper() or e.get("category") != "ENAHO Actualizada":
            continue
        if any(a in (e.get("years") or {}) for a in ANIOS):
            entrada = copy.deepcopy(e)
            break
    if entrada is None:
        return None
    for anio in list(entrada["years"]):
        if anio not in ANIOS:
            del entrada["years"][anio]
            continue
        for _periodo, pdata in entrada["years"][anio].items():
            pdata["modules"] = [m for m in pdata.get("modules", [])
                                if normaliza_modulo(m.get("module_code")) == "Modulo34"]
            pdata["docs"] = []
    dest = os.path.join(tempfile.gettempdir(), "enaho_bases")
    os.makedirs(dest, exist_ok=True)
    print("Descargando Sumaria de INEI (se omite si ya está)...")
    download_modules([entrada], dest, fmt="CSV", fallback=False, progress=False)
    zips = glob.glob(os.path.join(dest, "**", "*Modulo34*.zip"), recursive=True)
    return zips[0] if zips else None


def leer_sumaria_csv(zip_path):
    """Lee el CSV de la Sumaria del zip, detectando separador y prefiriendo el de comas."""
    candidatos = []  # (sep, nombre)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with zf.open(name) as fh:
                cabecera = fh.readline().decode("latin-1", "replace")
            sep = ";" if cabecera.count(";") > cabecera.count(",") else ","
            cols = {c.strip().lower() for c in cabecera.replace(";", ",").split(",")}
            if REQUERIDAS <= cols:
                candidatos.append((sep, name))
        candidatos.sort(key=lambda t: 0 if t[0] == "," else 1)  # coma primero (decimal con punto)
        if not candidatos:
            raise RuntimeError("No hallé un CSV de Sumaria con las variables requeridas")
        sep, name = candidatos[0]
        with zf.open(name) as fh:
            return pd.read_csv(fh, sep=sep, encoding="latin-1", low_memory=False)


def codebook_dominio():
    """{codigo: Etiqueta} del dominio geográfico, leído del parquet ya horneado."""
    dfm = pd.read_parquet(os.path.join(DATA, "enaho_variables.parquet"))
    row = dfm[(dfm["modulo_code"] == "Modulo34") & (dfm["anio"] == "2024")
              & (dfm["variable"].str.lower() == "dominio")]
    if not len(row) or not isinstance(row.iloc[0]["valores"], str):
        return {}
    return {k: v.title() for k, v in json.loads(row.iloc[0]["valores"]).items()}


def main():
    enaho = filter_catalog(load_catalog(), survey="enaho")
    zip_path = descargar_sumaria(enaho)
    if not zip_path:
        print("No pude descargar la Sumaria de", ANIOS)
        return
    b = leer_sumaria_csv(zip_path)
    b.columns = [c.lower() for c in b.columns]
    num = ["factor07", "mieperho", "inghog1d", "gashog2d", "pobreza", "dominio", "estrato", "ubigeo"]
    b = b[num].apply(pd.to_numeric, errors="coerce")  # solo lo necesario, sin fragmentar
    b = b.dropna(subset=["factor07"])
    dom_lab = codebook_dominio()
    b = b.assign(
        w_pers=b["factor07"] * b["mieperho"],  # peso poblacional (personas)
        dom=b["dominio"].map(lambda d: dom_lab.get(_cod(d)) if pd.notna(d) else None),
        area=b["estrato"].map(lambda e: None if pd.isna(e) else ("Urbano" if e <= 5 else "Rural")),
        dep=b["ubigeo"].map(lambda u: DEPARTAMENTOS.get(str(int(u)).zfill(6)[:2]) if pd.notna(u) else None),
    )

    def tasa_pobreza(sub, extrema=False):
        s = sub.dropna(subset=["w_pers", "pobreza"])
        w = s["w_pers"]
        mask = (s["pobreza"] == 1) if extrema else s["pobreza"].isin([1, 2])
        tot = w.sum()
        return round(100 * (w * mask).sum() / tot, 1) if tot else None

    def media_hogar(sub, col):
        m = sub[col].notna() & sub["factor07"].notna()
        tot = sub.loc[m, "factor07"].sum()  # peso del hogar
        return round((sub.loc[m, "factor07"] * sub.loc[m, col]).sum() / tot) if tot else None

    def por_dominio(func):
        out = {}
        for cod in ORDEN_DOMINIO:
            lab = dom_lab.get(cod)
            sub = b[b["dom"] == lab]
            if lab and len(sub):
                out[lab] = func(sub)
        return out

    def por_area(func):
        return {a: func(b[b["area"] == a]) for a in ("Urbano", "Rural") if len(b[b["area"] == a])}

    def por_departamento(func):
        out = {}
        for cod in sorted(DEPARTAMENTOS):
            lab = DEPARTAMENTOS[cod]
            sub = b[b["dep"] == lab]
            if len(sub):
                out[lab] = func(sub)
        return out

    def indicador(func):
        return {"nacional": func(b),
                "Por dominio geográfico": por_dominio(func),
                "Por departamento": por_departamento(func),
                "Por área": por_area(func)}

    indicadores = {
        "Tasa de pobreza (%)":
            {"unidad": "%", **indicador(lambda s: tasa_pobreza(s))},
        "Tasa de pobreza extrema (%)":
            {"unidad": "%", **indicador(lambda s: tasa_pobreza(s, extrema=True))},
        "Ingreso promedio del hogar (S/. al año)":
            {"unidad": "S/.", **indicador(lambda s: media_hogar(s, "inghog1d"))},
        "Gasto promedio del hogar (S/. al año)":
            {"unidad": "S/.", **indicador(lambda s: media_hogar(s, "gashog2d"))},
    }
    salida = {
        "fuente": "ENAHO 2024 (Sumaria, modulo 34), ponderado con el factor de expansion.",
        "n_hogares": int(len(b)),
        "indicadores": indicadores,
    }
    with open(os.path.join(DATA, "indicadores.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    print("OK indicadores. n_hogares:", salida["n_hogares"])
    for nombre, item in indicadores.items():
        print(f"  {nombre}: nacional={item['nacional']} | area={item['Por área']}")


if __name__ == "__main__":
    main()
