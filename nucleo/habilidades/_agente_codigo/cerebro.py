"""
nucleo/habilidades/agente_codigo/cerebro.py
─────────────────────────────────────────────────────────────────────────────
EL CEREBRO DE CÓDIGO — punto ÚNICO de intercambio de modelo.

Soporta dos proveedores vía config (CODE_PROVIDER):
  - "groq"      → tu setup actual (cliente groq, GROQ_MODEL_CODIGO). DEFAULT, no rompe nada.
  - "deepseek"  → API de DeepSeek (compatible OpenAI). DeepSeek V4 para código fuerte.

Y rutea por dificultad:
  - pensar_codigo(...)               → modelo normal (rápido/barato): generar y editar.
  - pensar_codigo(..., dificil=True) → modelo RAZONADOR (R1/R2): planificar, bugs difíciles.

El día que tengas GPU, apuntás CODE_PROVIDER a un modelo local (Ollama/LM Studio
también hablan OpenAI) cambiando solo la base_url en config. El resto del agente
ni se entera.

Config esperada en config.py (todo opcional, con defaults sensatos):
    CODE_PROVIDER             = "groq" | "deepseek"
    # groq:
    GROQ_API_KEY, GROQ_MODEL_CODIGO, GROQ_MODEL
    # deepseek (compatible OpenAI -> pip install openai):
    DEEPSEEK_API_KEY
    DEEPSEEK_BASE_URL         = "https://api.deepseek.com"
    DEEPSEEK_MODEL            = "deepseek-chat"        # V3.2/V4 (confirmá el string en api-docs.deepseek.com)
    DEEPSEEK_MODEL_RAZONADOR  = "deepseek-reasoner"    # R1/R2
    CODIGO_MAX_TOKENS         = 8000
"""
import logging

log = logging.getLogger("satella.agente.cerebro")


def _cfg(nombre, defecto=None):
    try:
        import config
        return getattr(config, nombre, defecto)
    except Exception:
        return defecto


_PROVIDER = (_cfg("CODE_PROVIDER", "groq") or "groq").lower()
_MAX_TOKENS = _cfg("CODIGO_MAX_TOKENS", 8000)

_cliente = None
_MODELO = None
_MODELO_DIFICIL = None
_listo = False
_intentado = False


def _init():
    global _cliente, _MODELO, _MODELO_DIFICIL, _listo, _intentado
    if _intentado:
        return
    _intentado = True
    try:
        if _PROVIDER == "deepseek":
            from openai import OpenAI  # pip install openai
            api_key = _cfg("DEEPSEEK_API_KEY")
            base_url = _cfg("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            if not api_key:
                log.error("[CEREBRO] CODE_PROVIDER=deepseek pero falta DEEPSEEK_API_KEY")
                return
            _cliente = OpenAI(api_key=api_key, base_url=base_url)
            _MODELO = _cfg("DEEPSEEK_MODEL", "deepseek-chat")
            _MODELO_DIFICIL = _cfg("DEEPSEEK_MODEL_RAZONADOR", "deepseek-reasoner")
        else:  # groq (default)
            from groq import Groq
            api_key = _cfg("GROQ_API_KEY")
            if not api_key:
                log.error("[CEREBRO] falta GROQ_API_KEY")
                return
            _cliente = Groq(api_key=api_key)
            _MODELO = _cfg("GROQ_MODEL_CODIGO") or _cfg("GROQ_MODEL")
            _MODELO_DIFICIL = _cfg("GROQ_MODEL_RAZONADOR") or _MODELO
        _listo = bool(_cliente and _MODELO)
        if _listo:
            log.info(f"[CEREBRO] listo - proveedor={_PROVIDER} modelo={_MODELO} (dificil={_MODELO_DIFICIL})")
    except Exception as e:
        log.error(f"[CEREBRO] no pude inicializar ({_PROVIDER}): {e}")
        _listo = False


def disponible() -> bool:
    _init()
    return _listo


def pensar_codigo(prompt: str, sistema: str = "", dificil: bool = False,
                  temperatura: float = 0.2) -> str:
    """Una vuelta de razonamiento sobre codigo. dificil=True usa el razonador."""
    _init()
    if not _listo:
        return ""
    modelo = _MODELO_DIFICIL if dificil else _MODELO
    mensajes = []
    if sistema:
        mensajes.append({"role": "system", "content": sistema})
    mensajes.append({"role": "user", "content": prompt})
    try:
        resp = _cliente.chat.completions.create(
            model=modelo,
            messages=mensajes,
            temperature=temperatura,
            max_tokens=_MAX_TOKENS,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        log.error(f"[CEREBRO] error pidiendo a {modelo}: {e}")
        return ""