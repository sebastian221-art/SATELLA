"""
Habilidad: mayusculas — convierte texto a mayúsculas.
"""

NOMBRE = "mayusculas"
DESCRIPCION = "Convierte a mayúsculas el texto que le pidas."
EJEMPLOS = [
    "poné esto en mayúsculas: hola mundo",
    "convertí a mayúsculas: re zero",
    "en mayus: satella es genial",
]

_TRIGGERS = ("mayuscula", "mayúscula", "mayus", "en mayús", "en mayus")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    return any(k in t for k in _TRIGGERS)


def manejar(texto: str, contexto: dict = None) -> dict:
    # Extraer el contenido a transformar: si hay ":", tomar lo que viene después
    objetivo = texto.split(":", 1)[1].strip() if ":" in texto else texto
    resultado = objetivo.upper()
    return {
        "ok": True,
        "skill": NOMBRE,
        "modo": "transformar",
        "resumen": "texto convertido a mayúsculas",
        "cuerpo": resultado,
    }