"""
nucleo/habilidades/planificador/detector.py
Detecta pedidos multi-paso o de planificación. CONSERVADOR a propósito: solo
dispara con lenguaje de plan explícito o conectores de secuencia fuertes, para
no robarle pedidos simples a las otras habilidades.
"""
_EXPLICITO = (
    "planificá", "planifica", "planear", "armá un plan", "arma un plan",
    "hacé un plan", "hace un plan", "un plan para", "paso a paso", "por pasos",
    "en varios pasos", "descomponé", "descompone", "organizá las tareas",
    "organiza las tareas", "hacé estos pasos", "hace estos pasos",
)
# Conectores de secuencia fuertes (dos palabras): implican tareas encadenadas.
_SECUENCIA = (
    " y luego ", " y después ", " y despues ", " y al final ",
    " y por último ", " y por ultimo ", " después hacé ", " luego hacé ",
)


def _t(texto):
    return " " + (texto or "").lower().strip() + " "


def es_plan(texto, codigo_adjunto=""):
    t = _t(texto)
    if any(e in t for e in _EXPLICITO):
        return True
    return any(s in t for s in _SECUENCIA)


def limpiar_objetivo(texto):
    """Quita el prefijo de planificación y deja el objetivo limpio."""
    t = (texto or "").strip()
    bajo = t.lower()
    for p in ("planificá:", "planifica:", "planificá", "planifica",
              "armá un plan para", "arma un plan para", "hacé un plan para",
              "hace un plan para", "un plan para", "hacé estos pasos:",
              "hace estos pasos:", "por pasos:", "paso a paso:"):
        if bajo.startswith(p):
            return t[len(p):].lstrip(" :,")
    return t