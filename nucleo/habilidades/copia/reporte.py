"""
nucleo/habilidades/copia/reporte.py
Reporte de FIDELIDAD: qué tan fiel es el equivalente al original y qué tradeoffs
tiene. Honesto por diseño — dice cuándo es 1:1 y cuándo es una aproximación.
"""
from nucleo.habilidades.python import _llm
from nucleo.habilidades import _generacion_segura

_SYSTEM = (
    "Sos un ingeniero senior honesto. Evaluás qué tan fiel es una reimplementación "
    "respecto a la función original. No exagerás: marcás claramente qué cubre igual y "
    "qué es aproximación o tradeoff. Español (voseo), breve."
)


def fidelidad(objetivo, contrato_txt, decision, codigo, verif):
    if not _llm.disponible() or not codigo:
        return ""
    estado = "ejecuta OK" if verif.get("ejecuta") else ("no ejecutó" if verif.get("ejecuta") is None else "falla al ejecutar")
    prompt = (
        f"Original (contrato funcional):\n{contrato_txt[:2500]}\n\n"
        f"Estrategia usada: {decision['estrategia']}.\n"
        f"Estado del código generado: sintaxis {'OK' if verif.get('sintaxis_ok') else 'inválida'}, {estado}.\n\n"
        "Evaluá honestamente:\n"
        "1. FIDELIDAD (alta/media/baja) y por qué.\n"
        "2. QUÉ CUBRE IGUAL que el original.\n"
        "3. QUÉ ES APROXIMACIÓN / TRADEOFF (qué se sacrificó por ser liviano).\n"
        "4. CUÁNDO conviene usar este equivalente y cuándo no.\n"
        "Sé concreto y honesto, sin inflar."
    )
    return _generacion_segura.completar_texto(prompt, system=_SYSTEM, max_tokens=2000)


def fidelidad_heuristica(decision, verif):
    """Fallback sin LLM."""
    if decision["estrategia"] == "port_adaptado":
        base = "Fidelidad alta esperada (port adaptado de lógica liviana)."
    elif decision["estrategia"] == "mejora":
        base = "Equivalente funcional con mejoras; fidelidad de comportamiento alta, implementación distinta."
    else:
        base = ("Equivalente funcional: hace el mismo trabajo de forma más liviana. "
                "Fidelidad de comportamiento media-alta; puede sacrificar escala/precisión del original.")
    if not verif.get("sintaxis_ok"):
        base += " ⚠ Pero el código generado tiene errores de sintaxis: hay que regenerar."
    elif verif.get("ejecuta") is False:
        base += " ⚠ El código no ejecuta limpio todavía: revisar."
    return base