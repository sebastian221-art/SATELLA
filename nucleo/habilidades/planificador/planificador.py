"""
nucleo/habilidades/planificador/planificador.py
Descompone un objetivo en una lista ordenada de pasos concretos.

Descomposición:
  1) Split DETERMINISTA por conectores de secuencia ("y luego", ";", ...) — los
     casos obvios no gastan modelo y son 100% confiables.
  2) Objetivo de un solo bloque → CLAUDE CODE arma el plan (mejor que Groq para
     objetivos ambiguos), con respaldo Groq si no está.
"""
import re

from nucleo.habilidades.python import _llm

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None

_MAX_PASOS = 6

_CONECTORES = re.compile(
    r"\s+y\s+luego\s+|\s+y\s+despu[eé]s\s+|\s+y\s+al\s+final\s+|"
    r"\s+y\s+por\s+[uú]ltimo\s+|\s+y\s+despu[eé]s\s+de\s+eso\s+|\s*;\s*",
    re.IGNORECASE,
)


def _split_conectores(objetivo: str) -> list:
    partes = _CONECTORES.split(objetivo or "")
    return [p.strip(" ,.") for p in partes if p and p.strip(" ,.")]


def _habilidades_disponibles() -> str:
    try:
        from nucleo.habilidades import registro
        lineas = []
        for s in registro.habilidades():
            n = getattr(s, "NOMBRE", "")
            if n == "planificador":
                continue
            d = getattr(s, "DESCRIPCION", "")
            lineas.append(f"- {n}: {d}" if d else f"- {n}")
        return "\n".join(lineas) or "- (ninguna habilidad específica; usá razonamiento general)"
    except Exception:
        return "- (no pude leer las habilidades)"


def _prompt_plan(objetivo: str) -> str:
    return (
        f'Objetivo del usuario: "{objetivo}"\n\n'
        f"Habilidades disponibles para resolver pasos:\n{_habilidades_disponibles()}\n\n"
        "Descomponé el objetivo en una lista ORDENADA de pasos concretos. Cada paso "
        "debe ser una INSTRUCCIÓN CORTA E IMPERATIVA, tal como se la darías directo a "
        "la habilidad, NO una descripción. Bien: «convertí 2024 a romano», «analizá el "
        "sentimiento de \"hoy estoy feliz\"». Mal: «Utilizar la habilidad romano para "
        "convertir el número…». No resuelvas los pasos, solo enumeralos. "
        f"Máximo {_MAX_PASOS} pasos. Si el objetivo es simple, puede ser un solo paso.\n"
        'Formato EXACTO: una línea por paso, empezando con "PASO: ". Nada más.'
    )


def _parsear_pasos(salida: str) -> list:
    pasos = []
    for linea in (salida or "").splitlines():
        linea = linea.strip()
        m = re.match(r"(?:PASO\s*:?|^\d+[\.\)])\s*(.+)", linea, re.IGNORECASE)
        if m:
            paso = m.group(1).strip(" -")
            if paso:
                pasos.append(paso)
    return pasos


def planificar(objetivo: str) -> list:
    """Devuelve una lista ordenada de pasos (strings). Vacía si falla."""
    # 1) Split determinista: si hay conectores de secuencia, esos SON los pasos.
    partes = _split_conectores(objetivo)
    if len(partes) >= 2:
        return partes[:_MAX_PASOS]

    # 2) Un solo bloque: descomponer con Claude Code (mejor), respaldo Groq.
    prompt = _prompt_plan(objetivo)

    if claude_cli is not None and claude_cli.disponible():
        r = claude_cli.preguntar(prompt, allowed_tools="Read", max_turns=3, timeout=120,
                                 etiqueta="Planificador",
                                 fases=["entendiendo el objetivo", "armando el plan"])
        if r.get("ok"):
            pasos = _parsear_pasos(r.get("texto", ""))
            if pasos:
                return pasos[:_MAX_PASOS]

    if _llm.disponible():
        pasos = _parsear_pasos(_llm.chat(prompt, max_tokens=600, temperature=0.3))
        if pasos:
            return pasos[:_MAX_PASOS]

    return [objetivo] if (objetivo or "").strip() else []