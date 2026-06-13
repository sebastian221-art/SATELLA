"""
nucleo/habilidades/mezclador/detector.py
Detecta dos intenciones:
  componer    → "mezclá: <objetivo>" / "combiná habilidades para <objetivo>"
  cristalizar → "congelá esto como <nombre>" / "guardá ese proceso como <nombre>"
Evita pisar al creador: NO usa la palabra "habilidad" como disparador.
"""
import re

_COMPONER = ("mezclá", "mezcla ", "mezcla:", "combiná", "combina ", "combina:",
             "componé", "compone ")
_CRISTALIZAR = ("congelá", "congela ", "congelalo", "congelala", "congelá esto",
                "guardá ese proceso", "guarda ese proceso", "guardá esto como",
                "guarda esto como", "congelá la mezcla", "congela la mezcla",
                "guardá la mezcla", "volvelo reutilizable")


def _t(texto):
    return (texto or "").lower()


def es_peticion(texto, codigo_adjunto=""):
    t = _t(texto)
    return any(k in t for k in _COMPONER) or any(k in t for k in _CRISTALIZAR)


def modo(texto):
    t = _t(texto)
    if any(k in t for k in _CRISTALIZAR):
        return "cristalizar"
    return "componer"


def extraer_objetivo(texto):
    t = (texto or "").strip()
    bajo = t.lower()
    for p in ("mezclá:", "mezcla:", "combiná:", "combina:", "componé:", "compone:",
              "mezclá", "mezcla", "combiná", "combina", "componé", "compone",
              "habilidades para", "para"):
        if bajo.startswith(p):
            return t[len(p):].lstrip(" :")
    return t


def extraer_nombre(texto):
    """De '...como <nombre>' devuelve <nombre> (snake_case)."""
    m = re.search(r"como\s+([a-zA-Z_][a-zA-Z0-9_]*)", texto or "", re.IGNORECASE)
    return m.group(1) if m else None