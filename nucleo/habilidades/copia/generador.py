"""
nucleo/habilidades/copia/generador.py
Genera el código del EQUIVALENTE para Satella, según el contrato funcional y la
estrategia decidida. Usa el modelo de código (GROQ_MODEL_CODIGO) vía _llm.
"""
import re
from nucleo.habilidades.python import _llm
from nucleo.habilidades import _generacion_segura
from . import decisor

_SYSTEM = (
    "Sos un ingeniero senior de Python. Generás código limpio, modular y LIVIANO para "
    "correr en CPU sin GPU. Implementás la FUNCIÓN pedida adaptada a esas restricciones, "
    "no copias implementación ajena. Devolvés SOLO código Python, sin explicaciones, sin "
    "markdown, sin ```."
)

_INSTR = {
    "port_adaptado": "Portá la lógica adaptándola a Satella (limpia, modular).",
    "equivalente_funcional": ("Construí un EQUIVALENTE FUNCIONAL liviano: mismo trabajo, "
                              "implementación más simple y barata (reglas, heurísticas, "
                              "estructuras chicas) en vez de lo pesado del original."),
    "mejora": ("Construí un equivalente funcional liviano Y mejorá lo que puedas (claridad, "
               "eficiencia, robustez), sin las limitaciones del original."),
}


def generar(objetivo, contrato_txt, decision):
    if not _llm.disponible():
        return ""
    instr = _INSTR.get(decision["estrategia"], _INSTR["equivalente_funcional"])
    prompt = (
        f"Pedido: «{objetivo}».\n\n"
        f"CONTRATO FUNCIONAL a implementar:\n{contrato_txt[:4000]}\n\n"
        f"ESTRATEGIA: {decision['estrategia']} — {instr}\n"
        f"RESTRICCIONES: {decisor.restricciones_satella()}\n\n"
        "Generá el código Python del equivalente. Incluí docstring breve y, si aplica, un "
        "ejemplo de uso bajo `if __name__ == '__main__':`. SOLO código."
    )
    salida = _generacion_segura.completar_codigo(prompt, system=_SYSTEM, max_tokens=4000)
    return _limpiar(salida)


def _limpiar(txt):
    """Saca fences de markdown si el modelo los puso igual."""
    if not txt:
        return ""
    txt = txt.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", txt, re.S)
    if m:
        return m.group(1).strip()
    return txt