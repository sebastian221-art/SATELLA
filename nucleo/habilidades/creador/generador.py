"""
nucleo/habilidades/creador/generador.py
Genera el skill.py de una habilidad nueva, conforme al contrato, usando el
modelo de código. Le da al modelo el contrato + una habilidad de ejemplo como
molde para que la salida encaje sí o sí.
"""
import re

from nucleo.habilidades import contrato
from nucleo.habilidades.python import _llm


def _extraer_codigo(txt: str) -> str:
    if "```" in txt:
        m = re.search(r"```(?:python)?\s*\n?(.*?)```", txt, re.DOTALL)
        if m:
            return m.group(1).strip()
    return (txt or "").strip()


def _nombre_de(codigo: str, spec: str) -> str:
    m = re.search(r'NOMBRE\s*=\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']', codigo or "")
    if m:
        return m.group(1)
    pal = re.findall(r"[a-zA-Z]+", (spec or "").lower())
    return "_".join(pal[:2]) if pal else "habilidad_nueva"


def generar(spec: str) -> dict:
    if not _llm.disponible():
        return {"ok": False}
    prompt = (
        f"Quiero una habilidad nueva para Satella que: {spec}\n\n"
        f"{contrato.descripcion_contrato()}\n\n"
        "Este es un EJEMPLO de habilidad VÁLIDA — respetá esta forma exacta:\n"
        f"```python\n{contrato.EJEMPLO_SKILL}\n```\n\n"
        "Escribí el skill.py completo de la habilidad pedida, comentarios en español, "
        "respetando el contrato al pie de la letra. Elegí un NOMBRE en snake_case de "
        "una sola palabra. Si la tarea necesita razonar o generar texto, usá "
        "`from nucleo.habilidades.python import _llm` y `_llm.chat(prompt, max_tokens=600)`. "
        "manejar() siempre debe devolver el dict completo. "
        "Respondé SOLO el código en un bloque ```python ... ```."
    )
    codigo = _extraer_codigo(_llm.chat(prompt, max_tokens=2200, temperature=0.2))
    return {"ok": bool(codigo), "nombre": _nombre_de(codigo, spec), "codigo": codigo}


def refinar(spec: str, codigo: str, error: str) -> str:
    if not _llm.disponible():
        return codigo
    prompt = (
        f"Esta habilidad (para: {spec}) NO pasó la validación. Error:\n{error}\n\n"
        f"Código actual:\n```python\n{codigo}\n```\n\n"
        f"Contrato a cumplir:\n{contrato.descripcion_contrato()}\n\n"
        "Corregí el skill.py para que cumpla el contrato y pase. "
        "Respondé SOLO el código completo en ```python ... ```."
    )
    return _extraer_codigo(_llm.chat(prompt, max_tokens=2200, temperature=0.2))