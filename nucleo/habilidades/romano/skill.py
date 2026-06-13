"""
Habilidad: romano — convierte números arábigos a numerales romanos.
"""

# Nombre único en snake_case
NOMBRE = "romano"

# Descripción breve de la habilidad
DESCRIPCION = "Convierte un número entero a su representación en números romanos."

# Frases típicas que deberían activar la habilidad
EJEMPLOS = [
    "convertí a romano: 2023",
    "poné este número en romano 1999",
    "¿cómo queda 58 en romano?"
]

# Palabras clave que disparan la detección
_TRIGGERS = ("romano", "romanos", "a romano", "en romano", "convertir a romano")

def _es_numero(texto: str) -> bool:
    """Devuelve True si el texto contiene al menos un número entero."""
    return any(part.isdigit() for part in texto.split())

def _extraer_numero(texto: str) -> int | None:
    """Intenta extraer el primer número entero encontrado en el texto."""
    for part in texto.split():
        if part.isdigit():
            return int(part)
        # También acepta números seguidos de puntuación (ej: "2023," o "58:")
        limpio = part.rstrip(".,:;!?)")
        if limpio.isdigit():
            return int(limpio)
    return None

def _a_romano(num: int) -> str:
    """Convierte un entero (1‑3999) a numeral romano."""
    if not (0 < num < 4000):
        raise ValueError("El número debe estar entre 1 y 3999")
    valores = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")
    ]
    resultado = []
    for valor, simbolo in valores:
        while num >= valor:
            resultado.append(simbolo)
            num -= valor
    return "".join(resultado)

def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    """
    Detecta si el mensaje corresponde a la habilidad.
    Se activa cuando contiene alguna palabra clave y al menos un número.
    """
    t = (texto or "").lower()
    return any(k in t for k in _TRIGGERS) and _es_numero(t)

def manejar(texto: str, contexto: dict = None) -> dict:
    """
    Convierte el número encontrado en el texto a romano.
    Devuelve siempre un dict con la información requerida.
    """
    numero = _extraer_numero(texto)
    if numero is None:
        return {
            "ok": False,
            "skill": NOMBRE,
            "modo": "error",
            "resumen": "no se encontró número para convertir",
            "cuerpo": "No pude identificar un número entero en el mensaje.",
        }

    try:
        romano = _a_romano(numero)
        ok = True
        modo = "transformar"
        resumen = f"Número {numero} convertido a romano"
        cuerpo = romano
    except ValueError as e:
        ok = False
        modo = "error"
        resumen = "número fuera de rango"
        cuerpo = str(e)

    return {
        "ok": ok,
        "skill": NOMBRE,
        "modo": modo,
        "resumen": resumen,
        "cuerpo": cuerpo,
    }