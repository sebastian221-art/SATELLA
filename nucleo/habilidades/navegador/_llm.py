"""
nucleo/habilidades/navegador/_llm.py — cliente Groq del CEREBRO del navegador.
Usa el modelo conversacional/razonador (GROQ_MODEL), no el de código: el agente
tiene que razonar "qué hago ahora en esta página", que es planificación, no
generación de código.
"""
import os
import logging

log = logging.getLogger("satella.navegador")

_client = None
_MODEL = "llama-3.3-70b-versatile"
_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_ok = False
_vision_roto = False   # si una llamada de visión falla, caemos a texto el resto de la sesión

try:
    from groq import Groq
    try:
        from config import GROQ_API_KEY, GROQ_MODEL
        _MODEL = GROQ_MODEL or _MODEL
    except Exception:
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
        _MODEL = os.environ.get("GROQ_MODEL", _MODEL)
    try:
        from config import GROQ_MODEL_VISION
        _VISION_MODEL = GROQ_MODEL_VISION or _VISION_MODEL
    except Exception:
        _VISION_MODEL = os.environ.get("GROQ_MODEL_VISION", _VISION_MODEL)
    if GROQ_API_KEY:
        _client = Groq(api_key=GROQ_API_KEY)
        _ok = True
        log.info(f"[NAV] cerebro listo — modelo {_MODEL} | visión {_VISION_MODEL}")
except Exception as e:
    log.error(f"[NAV] cerebro Groq no disponible: {e}")


def disponible() -> bool:
    return _ok


def vision_disponible() -> bool:
    return _ok and bool(_VISION_MODEL) and not _vision_roto


def pensar(system: str, prompt: str, max_tokens: int = 1200, temperature: float = 0.2) -> str:
    """Pide el próximo paso al modelo. Reintenta si vuelve vacío (gpt-oss a veces gasta
    el presupuesto razonando); con más techo de tokens el JSON entra completo."""
    if not _ok:
        return ""
    for intento in range(3):
        try:
            resp = _client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            c = (resp.choices[0].message.content or "").strip()
            if c:
                return c
            log.warning(f"[NAV] cerebro devolvió vacío (intento {intento + 1}/3)")
        except Exception as e:
            log.error(f"[NAV] cerebro falló: {e}")
            return ""
    return ""


def pensar_vision(system: str, prompt: str, imagen_b64: str,
                  max_tokens: int = 1200, temperature: float = 0.2) -> str:
    """Igual que pensar() pero le manda al modelo multimodal una CAPTURA de la página.
    Así el cerebro VE la pantalla (botones ocultos, layout) como una persona. Si falla,
    desactiva la visión para el resto de la sesión y el cerebro sigue con texto."""
    global _vision_roto
    if not vision_disponible() or not imagen_b64:
        return ""
    try:
        resp = _client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + imagen_b64}},
                ]},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        log.error(f"[NAV] visión falló ({_VISION_MODEL}): {e} — caigo a texto el resto de la sesión")
        _vision_roto = True
        return ""