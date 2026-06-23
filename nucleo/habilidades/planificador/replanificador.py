"""
nucleo/habilidades/planificador/replanificador.py
Re-planificación adaptativa: cuando un paso del plan FALLA, mira el objetivo, lo
que ya se hizo, el fallo y lo que quedaba, y propone los pasos que deberían
hacerse AHORA para recuperarse (otra estrategia, no repetir lo que falló).

Usa Groq (rápido): esto pasa a mitad de una tarea, con el usuario esperando, así
que prioriza responsividad sobre profundidad.
"""
import re

from nucleo.habilidades.python import _llm

_MAX = 6


def replanificar(objetivo, resultados, paso_fallido, pendientes):
    """Devuelve una nueva lista de pasos para recuperarse, o [] si no se puede."""
    if not _llm.disponible():
        return []

    hechos = "\n".join(
        f"- {r['paso']} → {'ok' if r.get('ok') else 'FALLÓ'}: {(r.get('cuerpo') or '')[:120]}"
        for r in resultados
    ) or "(nada todavía)"
    pend = "\n".join(f"- {p}" for p in pendientes) or "(no quedaban pasos)"

    try:
        from . import planificador
        habilidades = planificador._habilidades_disponibles()
    except Exception:
        habilidades = "(no pude leer las habilidades)"

    prompt = (
        f'OBJETIVO: "{objetivo}"\n\n'
        f"Lo que ya se hizo:\n{hechos}\n\n"
        f"El paso «{paso_fallido}» FALLÓ.\n\n"
        f"Pasos que quedaban por hacer:\n{pend}\n\n"
        f"Habilidades disponibles:\n{habilidades}\n\n"
        "Re-planificá: dame los pasos que se deberían hacer AHORA para cumplir el objetivo, "
        "corrigiendo o EVITANDO lo que falló (probá otra estrategia, NO repitas lo mismo). "
        "Instrucciones cortas e imperativas, como se las darías a la habilidad. "
        "Si el objetivo ya no es alcanzable, devolvé solo «PASO: imposible». "
        f"Máximo {_MAX} pasos. Una línea por paso, empezando con \"PASO: \"."
    )
    salida = _llm.chat(prompt, max_tokens=500, temperature=0.3)
    pasos = []
    for linea in (salida or "").splitlines():
        m = re.match(r"(?:PASO\s*:?|^\d+[.\)])\s*(.+)", linea.strip(), re.IGNORECASE)
        if m:
            p = m.group(1).strip(" -")
            if p:
                pasos.append(p)
    if pasos and pasos[0].lower().startswith("imposible"):
        return []
    return pasos[:_MAX]