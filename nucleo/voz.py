"""
Validación de respuestas de Satella + TTS con edge-tts.
"""
import asyncio
import base64
import logging
import os
import re
from config import VOZ_EDGE, AUDIO_TMP
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
log = logging.getLogger("satella.voz")

_PROHIBIDAS = [
    "claro que sí", "claro que si", "por supuesto", "con gusto",
    "¿en qué más puedo ayudarte?", "en qué más puedo", "como ia",
    "como asistente", "¡claro!", "entendido,", "por su puesto",
    "¡por supuesto!", "puedo ayudarte con", "estoy aquí para ayudarte",
    "espero haberte ayudado", "si necesitas algo más",
]

_SUSTITUCION_FRASES = {
    "¡claro!": "Sí.",
    "entendido": "Ok",
    "por supuesto": "Sí",
    "con gusto": "",
    "¡por supuesto!": "Sí.",
}


def validar(respuesta: str, nombre_esperado: str) -> tuple[bool, str]:
    """
    Valida que la respuesta cumpla con la personalidad de Satella.
    Retorna (es_valida, razon_si_invalida).
    """
    lower = respuesta.lower()

    for frase in _PROHIBIDAS:
        if frase in lower:
            return False, f"frase prohibida: '{frase}'"

    if len(respuesta.strip()) < 3:
        return False, "respuesta vacía"

    if len(respuesta) > 800:
        log.warning("Respuesta muy larga — se acepta pero se registra")

    return True, ""


def limpiar(respuesta: str) -> str:
    """Limpieza ligera del texto que se MUESTRA. NO toca el espaciado: conserva
    saltos de línea Y la indentación del código (Python depende de ella). El
    aplastado a una línea para el TTS lo hace preparar_para_voz por separado."""
    for malo, bueno in _SUSTITUCION_FRASES.items():
        respuesta = re.sub(re.escape(malo), bueno, respuesta, flags=re.IGNORECASE)
    respuesta = re.sub(r'\n{4,}', '\n\n\n', respuesta)   # solo recorta excesos de líneas en blanco
    return respuesta.strip()


def preparar_para_voz(texto: str) -> str:
    """Limpia el texto para TTS — elimina markdown y caracteres problemáticos."""
    t = texto
    t = re.sub(r'\*+', '', t)
    t = re.sub(r'`+', '', t)
    t = re.sub(r'#{1,6}\s*', '', t)
    t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', t)
    t = re.sub(r'[✓✅❌🏥📋🔔⚙️📞💬⚠️🩺🌟💪🎯]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


async def _sintetizar_async(texto: str, voice: str, output: str):
    import edge_tts
    communicate = edge_tts.Communicate(texto, voice=voice)
    await communicate.save(output)


def sintetizar_voz(texto: str) -> str | None:
    """
    Genera audio con edge-tts.
    Retorna base64 del MP3 o None si falla.
    """
    try:
        texto_limpio = preparar_para_voz(texto)
        if not texto_limpio:
            return None

        asyncio.run(_sintetizar_async(texto_limpio, VOZ_EDGE, AUDIO_TMP))

        with open(AUDIO_TMP, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        try:
            os.remove(AUDIO_TMP)
        except Exception:
            pass

        return audio_b64

    except ImportError:
        log.warning("edge-tts no instalado. Instala con: pip install edge-tts")
        return None
    except Exception as e:
        log.error(f"Voz: error edge-tts — {e}")
        return None