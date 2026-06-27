"""
nucleo/habilidades/contrato.py
─────────────────────────────────────────────────────────────────────────────
EL CONTRATO DE HABILIDAD DE SATELLA.

Una "habilidad" es una carpeta dentro de nucleo/habilidades/<nombre>/ que tiene
un skill.py exponiendo esta interfaz:

  OBLIGATORIO
    NOMBRE: str                                   # identificador único, snake_case
    detecta(texto: str, codigo_adjunto: str="") -> bool
    manejar(texto: str, contexto: dict=None) -> dict
        # devuelve un dict con: ok, skill, modo, resumen, cuerpo

  OPCIONAL (metadata recomendada)
    DESCRIPCION: str
    EJEMPLOS: list[str]
    VERSION: str

El registro descubre las carpetas automáticamente y valida cada una contra
este contrato antes de activarla. Si no cumple, no entra.
"""
import inspect

# Claves que SIEMPRE debe traer el dict que devuelve manejar().
CAMPOS_RESULTADO = ("ok", "skill", "modo", "resumen", "cuerpo")


def resultado(skill: str, modo: str, resumen: str, cuerpo: str, ok: bool = True, costo=None) -> dict:
    """Helper para que cualquier habilidad arme un resultado válido.

    `costo` es OPCIONAL: si la habilidad conoce lo que gastó (ej. lo que devuelve
    Claude Code en total_cost_usd), lo pasa y queda registrado en la telemetría.
    Si no, se omite del dict — backward-compatible con las skills que no lo traen.
    """
    r = {"ok": ok, "skill": skill, "modo": modo, "resumen": resumen, "cuerpo": cuerpo}
    if costo is not None:
        r["costo"] = costo
    return r


def validar(modulo) -> tuple:
    """
    Valida que un módulo cumpla el contrato.
    Devuelve (ok: bool, problemas: list[str]).
    """
    problemas = []

    nombre = getattr(modulo, "NOMBRE", None)
    if not isinstance(nombre, str) or not nombre.strip():
        problemas.append("falta NOMBRE (string no vacío)")

    for fn in ("detecta", "manejar"):
        f = getattr(modulo, fn, None)
        if not callable(f):
            problemas.append(f"falta la función {fn}()")

    det = getattr(modulo, "detecta", None)
    if callable(det):
        try:
            params = inspect.signature(det).parameters
            if len(params) < 1:
                problemas.append("detecta() debe aceptar al menos (texto)")
        except (ValueError, TypeError):
            pass

    man = getattr(modulo, "manejar", None)
    if callable(man):
        try:
            params = inspect.signature(man).parameters
            if len(params) < 1:
                problemas.append("manejar() debe aceptar al menos (texto)")
        except (ValueError, TypeError):
            pass

    return (len(problemas) == 0, problemas)


def descripcion_contrato() -> str:
    """Texto del contrato para alimentar al modelo que genera habilidades."""
    return (
        "Una habilidad de Satella es un archivo skill.py que define EXACTAMENTE:\n"
        "  NOMBRE: str  (snake_case, una sola palabra, identificador único)\n"
        "  DESCRIPCION: str  (qué hace, una línea)\n"
        "  EJEMPLOS: list[str]  (2-3 frases que deberían activar la habilidad)\n"
        "  def detecta(texto: str, codigo_adjunto: str = '') -> bool\n"
        "      # True si el mensaje le corresponde a esta habilidad. Basado en palabras clave.\n"
        "  def manejar(texto: str, contexto: dict = None) -> dict\n"
        "      # hace la tarea y devuelve un dict con las claves:\n"
        "      #   ok (bool), skill (str=NOMBRE), modo (str), resumen (str), cuerpo (str)\n"
        "Reglas:\n"
        "  - Solo imports ABSOLUTOS (ej: from nucleo.habilidades.python import _llm).\n"
        "  - Si la tarea necesita razonar o generar texto, usá el modelo:\n"
        "      from nucleo.habilidades.python import _llm\n"
        "      respuesta = _llm.chat(prompt, max_tokens=600)\n"
        "  - Si la tarea es una transformación determinista, hacela en Python puro.\n"
        "  - manejar() SIEMPRE devuelve el dict completo, nunca None.\n"
        "  - Nada de input(), nada que bloquee, nada de side-effects al importar."
    )


# Habilidad de ejemplo COMPLETA y VÁLIDA — sirve de molde para el generador.
EJEMPLO_SKILL = '''"""
Habilidad: mayusculas — convierte texto a mayúsculas.
"""
NOMBRE = "mayusculas"
DESCRIPCION = "Convierte a mayúsculas el texto que le pidas."
EJEMPLOS = ["poné esto en mayúsculas: hola", "convertí a mayúsculas: re zero"]

_TRIGGERS = ("mayuscula", "mayúscula", "en mayus")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    return any(k in t for k in _TRIGGERS)


def manejar(texto: str, contexto: dict = None) -> dict:
    objetivo = texto.split(":", 1)[1].strip() if ":" in texto else texto
    resultado = objetivo.upper()
    return {
        "ok": True,
        "skill": NOMBRE,
        "modo": "transformar",
        "resumen": "texto convertido a mayúsculas",
        "cuerpo": resultado,
    }
'''