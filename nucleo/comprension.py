"""
Comprensión profunda de Satella.
Groq analiza el mensaje y devuelve estructura de comprensión.
"""
import json
import logging
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL_RAPIDO

log = logging.getLogger("satella.comprension")
_client = Groq(api_key=GROQ_API_KEY)

_PROMPT_COMPRENSION = """Analiza este mensaje de Juan Sebastian (creador de Satella, 19 años, Bucaramanga, desarrolla IA).

Mensaje actual: "{mensaje}"
Contexto reciente: {contexto}
Lo que sé de él: {modelo}

Responde SOLO con JSON válido, sin texto extra, sin backticks:
{{
  "intencion_real": "qué quiere realmente en máximo 8 palabras",
  "tono": "frustrado|contento|curioso|cansado|dudando|serio|normal|afectuoso|irritado|emocionado",
  "subtext": "qué no dice explícitamente pero se siente en máximo 8 palabras",
  "necesita": "desafio|validacion|apoyo_directo|informacion|solo_hablar|ayuda_tecnica|que_la_escuchen",
  "urgencia": 0.5,
  "nombre": "Sebas|Sebastian|Juan Sebastian",
  "rag_keywords": "2-3 palabras clave para buscar conocimiento relevante o null"
}}

Reglas para el nombre:
- "Sebas" → momento normal, afectuoso, cotidiano (80% de los casos)
- "Sebastian" → momento serio, tema importante, requiere atención
- "Juan Sebastian" → cometió error grave, Satella genuinamente molesta, situación crítica"""


def comprender(mensaje: str, contexto: str, modelo: str) -> dict:
    """
    Analiza el mensaje y retorna estructura de comprensión.
    Fallback a valores por defecto si Groq falla.
    """
    try:
        prompt = _PROMPT_COMPRENSION.format(
            mensaje=mensaje[:500],
            contexto=contexto[:300] if contexto else "Primera interacción de la sesión",
            modelo=modelo[:200] if modelo else "Sin datos previos"
        )

        resp = _client.chat.completions.create(
            model=GROQ_MODEL_RAPIDO,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )

        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError as e:
        log.warning(f"Comprensión: JSON inválido de Groq — {e}")
        return _fallback(mensaje)
    except Exception as e:
        log.error(f"Comprensión: error Groq — {e}")
        return _fallback(mensaje)


def _fallback(mensaje: str) -> dict:
    """Valores por defecto cuando Groq falla."""
    tl = mensaje.lower()
    nombre = "Sebas"
    if any(w in tl for w in ["ayuda", "error", "falla", "no funciona", "problema"]):
        nombre = "Sebastian"
    return {
        "intencion_real": "consulta general",
        "tono": "normal",
        "subtext": "mensaje directo",
        "necesita": "informacion",
        "urgencia": 0.5,
        "nombre": nombre,
        "rag_keywords": None
    }