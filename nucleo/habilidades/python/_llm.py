"""
nucleo/habilidades/python/_llm.py — cliente Groq de la habilidad de código.
Usa un MODELO DEDICADO A CÓDIGO (qwen-2.5-coder-32b por defecto), distinto del
modelo conversacional. Así la generación de código la hace un modelo experto en
código y la personalidad la maneja el modelo conversacional.

Para cambiarlo, en config.py o .env: GROQ_MODEL_CODIGO="qwen-2.5-coder-32b"
"""
import os
import logging

log = logging.getLogger("satella.habilidad.python")

_client = None
_MODEL = "qwen-2.5-coder-32b"   # modelo especializado en código (en Groq)
_ok = False

try:
    from groq import Groq
    try:
        from config import GROQ_API_KEY
    except Exception:
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    # Modelo de código: config > env > default
    try:
        from config import GROQ_MODEL_CODIGO as _MC
        if _MC:
            _MODEL = _MC
    except Exception:
        _MODEL = os.environ.get("GROQ_MODEL_CODIGO", _MODEL)
    if GROQ_API_KEY:
        _client = Groq(api_key=GROQ_API_KEY)
        _ok = True
        log.info(f"[PY] Habilidad código lista — modelo {_MODEL}")
except Exception as e:
    log.error(f"[PY] Groq no disponible: {e}")


def disponible() -> bool:
    return _ok


def modelo() -> str:
    return _MODEL


def chat(prompt: str, max_tokens: int = 1600, temperature: float = 0.3,
         system: str = "Sos un ingeniero de software senior. Preciso, directo, en español (voseo).",
         reasoning_effort: str = None) -> str:
    if not _ok:
        return ""
    kwargs = dict(
        model=_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Modelos de razonamiento (ej. gpt-oss): pedirles que razonen poco deja tokens
    # para la respuesta. Si la versión de Groq no acepta el parámetro, reintentamos
    # sin él (el except de abajo).
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    try:
        resp = _client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        if reasoning_effort:
            try:
                kwargs.pop("reasoning_effort", None)
                resp = _client.chat.completions.create(**kwargs)
                return (resp.choices[0].message.content or "").strip()
            except Exception as e2:
                log.error(f"[PY] Groq falló (sin reasoning_effort): {e2}")
                return ""
        log.error(f"[PY] Groq falló: {e}")
        return ""


def chat_meta(prompt: str, max_tokens: int = 1600, temperature: float = 0.3,
              system: str = "Sos un ingeniero de software senior. Preciso, directo, en español (voseo)."):
    """Como chat(), pero devuelve (contenido, truncado) — truncado=True si el modelo
    cortó por el límite de tokens (finish_reason == 'length')."""
    if not _ok:
        return "", False
    try:
        resp = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        truncado = (getattr(choice, "finish_reason", "") == "length")
        return choice.message.content.strip(), truncado
    except Exception as e:
        log.error(f"[PY] Groq falló: {e}")
        return "", False