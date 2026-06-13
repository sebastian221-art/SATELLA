"""
nucleo/habilidades/planificador/planificador.py
Descompone un objetivo en una lista ordenada de pasos concretos. Le pasa al
modelo las habilidades disponibles para que los pasos sean ruteables.
"""
import re

from nucleo.habilidades.python import _llm

_MAX_PASOS = 6

# Conectores de secuencia fuertes: si aparecen, el objetivo es multi-paso SÍ o SÍ.
_CONECTORES = re.compile(
    r"\s+y\s+luego\s+|\s+y\s+despu[eé]s\s+|\s+y\s+al\s+final\s+|"
    r"\s+y\s+por\s+[uú]ltimo\s+|\s+y\s+despu[eé]s\s+de\s+eso\s+|\s*;\s*",
    re.IGNORECASE,
)


def _split_conectores(objetivo: str) -> list:
    """Parte el objetivo en los conectores de secuencia. Determinista y confiable."""
    partes = _CONECTORES.split(objetivo or "")
    return [p.strip(" ,.") for p in partes if p and p.strip(" ,.")]


def _habilidades_disponibles() -> str:
    """Lista NOMBRE: DESCRIPCION de las habilidades activas (menos el planificador)."""
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


def planificar(objetivo: str) -> list:
    """Devuelve una lista ordenada de pasos (strings). Vacía si falla."""
    # 1) Split determinista: si hay conectores de secuencia, esos SON los pasos.
    #    Evita que el LLM, por azar, meta un objetivo multi-parte en un solo paso.
    partes = _split_conectores(objetivo)
    if len(partes) >= 2:
        return partes[:_MAX_PASOS]

    # 2) Un solo bloque: dejamos que el modelo decida si hay sub-pasos.
    if not _llm.disponible():
        return [objetivo] if (objetivo or "").strip() else []
    prompt = (
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
    salida = _llm.chat(prompt, max_tokens=600, temperature=0.3)
    pasos = []
    for linea in (salida or "").splitlines():
        linea = linea.strip()
        m = re.match(r"(?:PASO\s*:?|^\d+[\.\)])\s*(.+)", linea, re.IGNORECASE)
        if m:
            paso = m.group(1).strip(" -")
            if paso:
                pasos.append(paso)
    return pasos[:_MAX_PASOS] if pasos else ([objetivo] if (objetivo or "").strip() else [])