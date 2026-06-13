"""
nucleo/habilidades/planificador/skill.py — El planificador.

Es una habilidad que ORQUESTA a las demás: descompone un objetivo en pasos,
rutea cada paso a la habilidad que corresponda (o lo resuelve con el modelo),
y teje una respuesta final. Es el backbone del que después cuelgan el mezclador
y los agentes.

Siempre devuelve ok=True: una vez que detecta() disparó, la respuesta es suya.
"""
import logging

from nucleo.habilidades import contrato
from . import detector, planificador, ejecutor, sintetizador

log = logging.getLogger("satella.habilidad.planificador")

NOMBRE = "planificador"
DESCRIPCION = "Descompone un objetivo en pasos y los resuelve usando las demás habilidades."
EJEMPLOS = [
    "planificá: convertí 2024 a romano y después analizá el sentimiento de 'estoy feliz'",
    "hacé un plan para preparar un informe y luego resumilo",
    "paso a paso: validá este email y después generá un saludo",
]


_PROFUNDIDAD = 0
_MAX_PROF = 2


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_plan(texto, codigo_adjunto)


def manejar(texto: str, contexto: dict = None) -> dict:
    global _PROFUNDIDAD
    objetivo = detector.limpiar_objetivo(texto)

    # Guarda anti-recursión: las habilidades compuestas (del mezclador) delegan
    # en el planificador; si una de ellas se cuela como paso, esto corta el ciclo.
    if _PROFUNDIDAD >= _MAX_PROF:
        from nucleo.habilidades.python import _llm
        cuerpo = (_llm.chat(f"Resolvé de forma directa y breve, en español: {objetivo}",
                            max_tokens=500).strip()
                  if _llm.disponible() else "(límite de recursión del planificador)")
        return contrato.resultado(NOMBRE, "planificar", "resuelto sin sub-plan", cuerpo)

    _PROFUNDIDAD += 1
    try:
        pasos = planificador.planificar(objetivo)
        if not pasos:
            return contrato.resultado(NOMBRE, "planificar", "no pude planificar",
                                      "No pude armar un plan para eso (¿modelo disponible?).")

        log.info(f"[PLAN] {len(pasos)} paso(s) para: {objetivo[:60]}")
        resultados = ejecutor.ejecutar_plan(pasos, contexto)
        sintesis = sintetizador.sintetizar(objetivo, resultados)

        plan_txt = "\n".join(f"{i}. {p}" for i, p in enumerate(pasos, 1))
        ejec_txt = "\n".join(f"{i}. [{r['skill']}] {r['cuerpo']}"
                             for i, r in enumerate(resultados, 1))
        cuerpo = (
            f"**Plan ({len(pasos)} paso/s):**\n{plan_txt}\n\n"
            f"**Ejecución:**\n{ejec_txt}\n\n"
            f"**Resultado:**\n{sintesis}"
        )
        return contrato.resultado(NOMBRE, "planificar",
                                  f"plan ejecutado en {len(pasos)} paso(s)", cuerpo)
    finally:
        _PROFUNDIDAD -= 1