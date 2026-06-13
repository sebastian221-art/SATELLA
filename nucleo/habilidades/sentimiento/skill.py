"""
Habilidad: sentimiento — detecta el sentimiento (positivo, negativo o neutral) de un texto.
"""
# IMPORTS
import re
from typing import List

# METADATOS DE LA HABILIDAD
NOMBRE = "sentimiento"
DESCRIPCION = "Detecta si el texto tiene tono positivo, negativo o neutral."
EJEMPLOS = [
    "Analizá el sentimiento de este mensaje: me alegro mucho",
    "Detectá el sentimiento: estoy triste",
    "¿Qué tono tiene este texto? Me siento feliz",
]

# Palabras clave que disparan la habilidad
_TRIGGERS = (
    "sentimiento",
    "analizá el sentimiento",
    "detectá el sentimiento",
    "qué tono tiene",
    "qué sentimiento tiene",
)

# Listas simples de palabras positivas y negativas para la heurística
_POSITIVAS: List[str] = [
    "alegro", "feliz", "contento", "genial", "excelente", "bueno", "maravilloso",
    "fantástico", "positivo", "optimista", "encantado", "satisfecho", "placer",
]
_NEGATIVAS: List[str] = [
    "triste", "deprimido", "mal", "horrible", "terrible", "negativo", "pesimista",
    "enojado", "frustrado", "descontento", "odio", "malo", "desgracia", "dolor",
]

def _limpiar(texto: str) -> List[str]:
    """
    Normaliza el texto: minúsculas, elimina caracteres no alfabéticos y lo
    separa en palabras.
    """
    texto = texto.lower()
    # Reemplaza cualquier carácter que no sea letra o número por espacio
    texto = re.sub(r"[^a-záéíóúñü0-9]+", " ", texto)
    return texto.split()

def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    """
    Determina si el mensaje corresponde a esta habilidad.
    Se basa en la presencia de alguna palabra clave en _TRIGGERS.
    """
    t = (texto or "").lower()
    return any(k in t for k in _TRIGGERS)

def manejar(texto: str, contexto: dict = None) -> dict:
    """
    Analiza el sentimiento del texto recibido.
    Usa una heurística basada en conteo de palabras positivas y negativas.
    Devuelve un dict con la información del análisis.
    """
    # Extraer la parte del texto que realmente se quiere analizar.
    # Si el mensaje contiene ":", tomamos lo que sigue; si no, usamos todo.
    if ":" in texto:
        contenido = texto.split(":", 1)[1].strip()
    else:
        # Buscamos la última aparición de la palabra clave y tomamos lo que sigue
        partes = re.split(r"\b(sentimiento|tono)\b", texto, flags=re.IGNORECASE)
        contenido = partes[-1].strip() if partes else texto

    palabras = _limpiar(contenido)

    # Conteo de coincidencias
    pos = sum(1 for p in palabras if p in _POSITIVAS)
    neg = sum(1 for p in palabras if p in _NEGATIVAS)

    # Determinación del sentimiento
    if pos > neg:
        sentimiento = "positivo"
    elif neg > pos:
        sentimiento = "negativo"
    else:
        sentimiento = "neutral"

    resumen = f"Sentimiento detectado: {sentimiento}"
    cuerpo = (
        f"Texto analizado: \"{contenido}\"\n"
        f"Positivas encontradas: {pos}\n"
        f"Negativas encontradas: {neg}\n"
        f"Resultado: {sentimiento}"
    )

    return {
        "ok": True,
        "skill": NOMBRE,
        "modo": "analizar",
        "resumen": resumen,
        "cuerpo": cuerpo,
    }