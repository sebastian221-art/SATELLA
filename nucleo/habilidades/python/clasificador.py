"""
nucleo/habilidades/python/clasificador.py
Clasificador de intención con el modelo. Para los casos que las palabras clave
no agarran (ej: "necesito sacar los duplicados de una lista"), el modelo decide
si es tarea de código y de qué tipo. Entiende lenguaje natural de verdad.
Se llama SOLO en casos ambiguos (el detector filtra antes) para no gastar de más.
"""
from . import _llm

_MODOS = ("GENERACION", "ANALISIS", "DEBUG", "EJECUTAR")


def clasificar(texto: str):
    """Devuelve (es_codigo: bool, modo: str|None)."""
    if not _llm.disponible():
        return False, None
    prompt = (
        f'Mensaje del usuario: "{texto[:300]}"\n\n'
        "¿Está pidiendo una tarea de PROGRAMACIÓN en Python? Respondé con UNA sola palabra:\n"
        "GENERACION = pide crear/escribir código o resolver algo con código (aunque no diga 'función')\n"
        "ANALISIS = pide revisar/analizar/mejorar código\n"
        "DEBUG = pregunta por qué falla un código\n"
        "EJECUTAR = pide correr código\n"
        "NO = no es tarea de código (charla, sentimientos, otra cosa)"
    )
    r = _llm.chat(prompt, max_tokens=6, temperature=0.0,
                  system="Sos un clasificador. Respondés UNA sola palabra, sin explicar.").strip().upper()
    for modo in _MODOS:
        if modo in r:
            return True, modo.lower()
    return False, None