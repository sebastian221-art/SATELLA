"""
nucleo/habilidades/planificador/sintetizador.py
Teje una respuesta final coherente a partir de los resultados de cada paso.
Si el modelo no está, cae a un resumen simple (sin inventar nada).
"""
from nucleo.habilidades.python import _llm


def sintetizar(objetivo: str, resultados: list) -> str:
    datos = "\n".join(f"- {r['paso']} → {r['cuerpo']}" for r in resultados)
    if not _llm.disponible():
        return datos
    prompt = (
        f'Objetivo del usuario: "{objetivo}"\n\n'
        f"Resultados de cada paso:\n{datos}\n\n"
        "Escribí una respuesta final breve y coherente para el usuario, integrando "
        "los resultados. En español, directa, sin relleno. NO inventes nada que no "
        "esté en los resultados de arriba."
    )
    return _llm.chat(prompt, max_tokens=500, temperature=0.4).strip() or datos