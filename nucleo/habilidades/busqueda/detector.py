"""
nucleo/habilidades/busqueda/detector.py
Detecta pedidos que necesitan info FRESCA de internet (no conocimiento atemporal).
Conservador a propósito: solo dispara con verbos de búsqueda explícitos o
marcadores de actualidad, para no robarle pedidos a las otras habilidades ni
responder con búsqueda algo que es charla o conocimiento general.
"""
import re

_VERBOS = (
    "buscá", "busca ", "buscame", "buscáme", "búscame", "googleá", "googlea",
    "googleame", "investigá", "investiga", "averiguá", "averigua", "averiguame",
    "fijate en internet", "fijate online", "buscá en internet", "busca en internet",
    "buscá online", "busca online", "buscá info", "busca info",
)

_ACTUALIDAD = (
    "último", "última", "ultimos", "últimos", "últimas", "lo nuevo", "lo último",
    "novedades", "noticias", "qué pasó con", "que paso con", "qué hay de nuevo",
    "que hay de nuevo", "actualmente", "hoy en día", "hoy en dia", "en este momento",
    "reciente", "recientes", "cuándo sale", "cuando sale", "ya salió", "ya salio",
    "precio de", "precio del", "cuánto cuesta", "cuanto cuesta", "cuánto vale",
    "cuanto vale", "quién ganó", "quien gano", "resultado de", "qué se sabe de",
    "que se sabe de", "se sabe algo de", "están diciendo", "estan diciendo",
    "tendencias", "qué es lo último", "lo más nuevo", "versión actual", "version actual",
    "está pasando", "esta pasando", "en vivo", "cotización", "cotizacion",
)

# Años actuales/futuros: señal fuerte de que quiere info fresca.
_ANIOS = ("2025", "2026", "2027")


def _t(texto):
    return (texto or "").lower()


def hay_url(texto):
    return bool(re.search(r"https?://|www\.", texto or ""))


def es_busqueda(texto, codigo_adjunto=""):
    t = _t(texto)
    if hay_url(texto) or codigo_adjunto:   # URLs y código son de otras habilidades
        return False
    if any(v in t for v in _VERBOS):
        return True
    if any(a in t for a in _ACTUALIDAD):
        return True
    # "noticias 2026", "lo de X en 2026"
    if any(a in t for a in _ANIOS) and any(w in t for w in ("noticia", "nuevo", "último", "ultimo", "pasó", "paso", "sale", "salió")):
        return True
    return False


def limpiar_consulta(texto):
    """Saca el verbo de búsqueda inicial y deja la consulta limpia."""
    t = (texto or "").strip()
    bajo = t.lower()
    for p in ("buscá en internet", "busca en internet", "buscá online", "busca online",
              "fijate en internet", "buscá info sobre", "busca info sobre",
              "buscáme", "búscame", "buscame", "buscá", "busca", "googleame",
              "googleá", "googlea", "investigá", "investiga", "averiguáme",
              "averiguame", "averiguá", "averigua"):
        if bajo.startswith(p):
            resto = t[len(p):].lstrip(" :,")
            # sacar un "sobre " inicial si quedó
            if resto.lower().startswith("sobre "):
                resto = resto[6:].lstrip()
            return resto or t
    return t