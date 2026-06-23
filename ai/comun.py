"""Utilidades compartidas para hornear la metadata de ENAHO."""
import re

# Nombres oficiales de las tres colecciones ENAHO.
COL_ACTUALIZADA = "ENAHO Metodología Actualizada (2004+)"
COL_ANTERIOR = "ENAHO Metodología Anterior (1997-2003)"
COL_PANEL = "ENAHO Panel"


def fix_encoding(s):
    """Repara mojibake tipico (UTF-8 leido como Latin-1), p. ej. 'EducaciÃ³n' -> 'Educación'.

    Es un no-op si la cadena ya esta bien codificada (solo actua cuando aparecen los
    marcadores tipicos del mojibake y la reconversion no falla).
    """
    if not isinstance(s, str) or not s:
        return s
    if not any(c in s for c in ("Ã", "Â", "â")):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def coleccion(category, etiqueta):
    """Clasifica una entrada en una de las tres colecciones ENAHO.

    'etiqueta' es el campo 'value' (catalogo) o 'survey' (indice); ambos contienen
    'PANEL' cuando corresponde a la encuesta panel.
    """
    if "PANEL" in (etiqueta or "").upper():
        return COL_PANEL
    if (category or "") == "ENAHO Actualizada":
        return COL_ACTUALIZADA
    return COL_ANTERIOR


def normaliza_modulo(code):
    """Normaliza el codigo de modulo a 'ModuloNN'. Acepta '906-Modulo03' o '3'."""
    if code is None:
        return None
    code = str(code)
    m = re.search(r"Modulo(\d+)", code, re.IGNORECASE)
    if m:
        return "Modulo" + m.group(1).zfill(2)
    if code.isdigit():
        return "Modulo" + code.zfill(2)
    return code
