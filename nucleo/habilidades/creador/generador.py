"""
nucleo/habilidades/creador/generador.py
Genera el skill.py de una habilidad nueva, conforme al contrato.

Cerebro: CLAUDE CODE (calidad frontera, con tu CLAUDE.md). Le pasa el contrato,
una habilidad de ejemplo como molde, y la LISTA de habilidades ya existentes
(para que encaje y no duplique). Si Claude Code no está, cae a Groq (_llm) como
respaldo, así el creador nunca queda inutilizable.
"""
import re

from nucleo.habilidades import contrato
from nucleo.habilidades.python import _llm

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None


def _extraer_codigo(txt: str) -> str:
    if "```" in (txt or ""):
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


def _habilidades_existentes() -> str:
    try:
        from nucleo.habilidades import registro
        nombres = [getattr(s, "NOMBRE", "?") for s in registro.habilidades()]
        return ", ".join(n for n in nombres if n and n != "?")
    except Exception:
        return ""


def _prompt_crear(spec: str) -> str:
    existentes = _habilidades_existentes()
    nota_existentes = (f"\nHabilidades que YA existen (no las dupliques, encajá con ellas): "
                       f"{existentes}.\n" if existentes else "")
    return (
        f"Quiero una habilidad nueva para Satella que: {spec}\n"
        f"{nota_existentes}\n"
        f"{contrato.descripcion_contrato()}\n\n"
        "Este es un EJEMPLO de habilidad VÁLIDA — respetá esta forma exacta:\n"
        f"```python\n{contrato.EJEMPLO_SKILL}\n```\n\n"
        "Escribí el skill.py completo de la habilidad pedida, comentarios en español, "
        "respetando el contrato al pie de la letra. Elegí un NOMBRE en snake_case de "
        "una sola palabra. Si la tarea necesita razonar o generar texto, usá "
        "`from nucleo.habilidades.python import _llm` y `_llm.chat(prompt, max_tokens=600)`. "
        "manejar() siempre debe devolver el dict completo (vía contrato.resultado). "
        "No escribas archivos. Respondé SOLO el código en un bloque ```python ... ```."
    )


def _pensar(prompt: str, max_tokens: int = 2200) -> str:
    """Usa Claude Code si está; si no, Groq. Devuelve el texto crudo."""
    if claude_cli is not None and claude_cli.disponible():
        r = claude_cli.preguntar(prompt, allowed_tools="Read", max_turns=6, timeout=240,
                                 etiqueta="Creador de habilidad",
                                 fases=["diseñando la habilidad", "escribiendo el skill.py",
                                        "revisando el contrato"])
        if r.get("ok"):
            return r.get("texto", "")
    # Respaldo: Groq
    if _llm.disponible():
        return _llm.chat(prompt, max_tokens=max_tokens, temperature=0.2)
    return ""


def generar(spec: str) -> dict:
    salida = _pensar(_prompt_crear(spec))
    codigo = _extraer_codigo(salida)
    return {"ok": bool(codigo), "nombre": _nombre_de(codigo, spec), "codigo": codigo}


def refinar(spec: str, codigo: str, error: str) -> str:
    prompt = (
        f"Esta habilidad (para: {spec}) NO pasó la validación. Error:\n{error}\n\n"
        f"Código actual:\n```python\n{codigo}\n```\n\n"
        f"Contrato a cumplir:\n{contrato.descripcion_contrato()}\n\n"
        "Corregí el skill.py para que cumpla el contrato y pase. "
        "Respondé SOLO el código completo en ```python ... ```."
    )
    return _extraer_codigo(_pensar(prompt))