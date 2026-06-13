"""
nucleo/habilidades/creador/detector.py
Detecta peticiones para el creador y clasifica el modo: crear | aprobar | listar.
Requiere que el mensaje mencione "habilidad"/"skill" para no robarle pedidos
normales de código a la habilidad python.
"""
import re

_PALABRA = ("habilidad", "habilidades", "skill", "skills")
_VERBOS_CREAR = ("creame", "créame", "crea ", "creá", "generá", "genera", "armá",
                 "arma ", "hacé", "hace ", "construí", "construi", "necesito", "quiero")
_VERBOS_APROBAR = ("aprobá", "aproba", "aprobar", "aprueba", "activá", "activa",
                   "activar", "confirmá", "confirma")
_FRASES_LISTAR = ("listar", "listá", "lista las", "mostrar", "mostrá", "mostra",
                  "cuáles", "cuales", "cuántas", "cuantas", "en revisión",
                  "en revision", "pendientes", "qué habilidades", "que habilidades")


def _t(texto):
    return (texto or "").lower()


def menciona_habilidad(texto):
    return any(p in _t(texto) for p in _PALABRA)


def _tiene(texto, claves):
    t = _t(texto)
    return any(k in t for k in claves)


def es_peticion(texto, codigo_adjunto=""):
    if not menciona_habilidad(texto):
        return False
    return (_tiene(texto, _VERBOS_CREAR) or _tiene(texto, _VERBOS_APROBAR)
            or _tiene(texto, _FRASES_LISTAR))


def modo(texto):
    if _tiene(texto, _VERBOS_APROBAR):
        return "aprobar"
    if _tiene(texto, _FRASES_LISTAR) and not _tiene(texto, _VERBOS_CREAR):
        return "listar"
    return "crear"


def extraer_spec(texto):
    """Se queda con la descripción de lo que la habilidad debe hacer."""
    t = (texto or "").strip()
    bajo = t.lower()
    for p in _PALABRA:
        i = bajo.find(p)
        if i != -1:
            resto = t[i + len(p):].strip()
            for c in ("que ", "de ", "para ", "nueva ", "llamada ", "llamado ", ":", "-", "—"):
                if resto.lower().startswith(c):
                    resto = resto[len(c):].strip()
            if resto:
                return resto
    return t


def extraer_nombre_aprobar(texto):
    """De 'aprobá la habilidad X' devuelve X (último identificador)."""
    resto = extraer_spec(texto)
    ids = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", resto)
    # filtra conectores comunes que puedan colarse
    ids = [x for x in ids if x.lower() not in ("la", "el", "de", "que", "habilidad", "skill")]
    return ids[-1] if ids else ""