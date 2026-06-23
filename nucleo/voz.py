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


async def _sintetizar_async(texto: str, voice: str, output: str,
                            rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%"):
    import edge_tts
    communicate = edge_tts.Communicate(texto, voice=voice, rate=rate, pitch=pitch, volume=volume)
    await communicate.save(output)


# ─────────────────────────────────────────────────────────────────────────────
# PROSODIA EMOCIONAL — la voz se matiza según QUÉ voz habla y CON QUÉ emoción.
# edge-tts gratis no actúa emociones (no tiene 'express-as'), pero sí modula
# velocidad/tono/volumen. Combinamos un color base por personaje + un empuje por
# emoción para sugerir: calma, euforia, timidez, aliento, enojo, desilusión, etc.
# ─────────────────────────────────────────────────────────────────────────────

# Color base por voz: (velocidad %, tono Hz, volumen %)
_BASE_VOZ = {
    "echidna": (-8, -2, 0),    # calmada, medida, grave
    "rem":     (2, 6, 0),      # cálida, alentadora, brillante
    "ram":     (6, -6, 0),     # firme, cortante, grave
    "emilia":  (-6, 4, -3),    # gentil, suave
}

# Empuje por emoción (tono detectado): se SUMA sobre el color base.
_EMOCION = {
    "contento":   (8, 6, 2),     # feliz
    "emocionado": (12, 9, 3),    # eufórica
    "afectuoso":  (-2, 4, 0),    # cálida
    "curioso":    (3, 2, 0),     # despierta
    "normal":     (0, 0, 0),
    "serio":      (-3, -3, 0),
    "dudando":    (-5, 1, -3),   # tímida/tentativa
    "cansado":    (-9, -4, -4),  # apagada
    "frustrado":  (4, -3, 2),    # tensa
    "irritado":   (6, -4, 3),    # molesta
    "triste":     (-8, -5, -5),  # desilusionada
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _perfil_prosodia(voz: str = None, emocion: str = None):
    """Devuelve (rate, pitch, volume) como strings para edge-tts."""
    br, bp, bv = _BASE_VOZ.get((voz or "").lower(), (0, 0, 0))
    # La emoción puede venir compuesta ('dudando|frustrado') → tomo la primera.
    em = (emocion or "normal").split("|")[0].strip().lower()
    er, ep, ev = _EMOCION.get(em, (0, 0, 0))
    r = _clamp(br + er, -40, 40)
    p = _clamp(bp + ep, -20, 20)
    v = _clamp(bv + ev, -20, 20)
    return (f"{'+' if r >= 0 else ''}{r}%",
            f"{'+' if p >= 0 else ''}{p}Hz",
            f"{'+' if v >= 0 else ''}{v}%")


def sintetizar_voz(texto: str, voz: str = None, emocion: str = None) -> str | None:
    """
    Genera audio con edge-tts, matizado según la voz y la emoción del momento.
    Retorna base64 del MP3 o None si falla.
    """
    try:
        texto_limpio = preparar_para_voz(texto)
        if not texto_limpio:
            return None

        rate, pitch, volume = _perfil_prosodia(voz, emocion)
        asyncio.run(_sintetizar_async(texto_limpio, VOZ_EDGE, AUDIO_TMP, rate, pitch, volume))

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