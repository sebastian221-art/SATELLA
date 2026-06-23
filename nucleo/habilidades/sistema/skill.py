"""
nucleo/habilidades/sistema/skill.py — CONTROL DEL PC (habilidad #8).

Satella actúa sobre tu PC mediante un REGISTRO de acciones seguras (acciones.py).
El pedido en lenguaje natural lo interpreta Groq (cerebro.py) en una acción concreta.

Capas de seguridad:
  - Lista blanca: solo ejecuta acciones del registro, nunca comandos libres.
  - Niveles de riesgo: verde directo; amarillo/rojo PIDEN CONFIRMACIÓN antes de actuar.
  - Borrar = a la papelera (reversible); rutas críticas del sistema bloqueadas.
"""
import logging

from nucleo.habilidades import contrato
from . import acciones, cerebro

log = logging.getLogger("satella.habilidad.sistema")

NOMBRE = "sistema"
DESCRIPCION = "Controla la PC: abrir apps/archivos, volumen, multimedia, buscar, y (con confirmación) cerrar, apagar, mover o borrar."
EJEMPLOS = [
    "abrime el VSCode",
    "subí el volumen",
    "buscá los archivos que se llamen informe",
    "apagá el PC",
]

# Acción pendiente de confirmación: (accion, params, riesgo, descripcion)
_pendiente = None

_CONFIRMA = ("si", "sí", "dale", "confirmo", "hacelo", "hazlo", "ok", "okay", "obvio",
             "sip", "claro", "de una", "afirmativo", "procedé", "procede")
_CANCELA = ("no", "cancelá", "cancela", "mejor no", "dejá", "deja", "olvidalo",
            "olvidá", "negativo", "pará", "para")

# Gatillos: pedidos que claramente son sobre la PC.
_GATILLOS = (
    "abrí", "abrime", "abre ", "abrir ", "ejecutá", "ejecuta ", "lanzá", "lanza ",
    "cerrá", "cerra ", "cerrar ", "matá el proceso", "volumen", "subí el volumen",
    "bajá el volumen", "subi el volumen", "baja el volumen", "silenciá", "silencia",
    "mutea", "muteá", "reproducí", "reproduci", "pausá", "pausa ", "play", "siguiente canción",
    "canción anterior", "apagá", "apaga ", "apagar", "reiniciá", "reinicia", "reiniciar",
    "bloqueá la pantalla", "bloquea la pantalla", "bloqueá el pc", "mové ", "mover ",
    "borrá ", "borra ", "eliminá ", "elimina ", "creá la carpeta", "crea la carpeta",
    "creá carpeta", "buscá el archivo", "buscá los archivos", "busca el archivo",
    "buscá archivos", "qué apps", "que apps", "cuánta ram", "cuanta ram", "batería",
    "bateria", "qué procesos", "abrí la carpeta", "abrime la carpeta", "abrí el archivo",
    "buscá los archivo", "buscar archivo", "buscar archivos", "encontrá el archivo",
    "encontrá los archivos", "encontrá archivos", "dónde está el archivo",
    "donde esta el archivo", "buscá un archivo", "busca un archivo",
)

# Si el pedido es claramente una búsqueda WEB, sistema NO se mete (lo toma 'busqueda').
_WEB = ("en internet", "en la web", "online", "en línea", "en linea", "en google", "googleá",
        "googlea", "noticias", "qué precio", "precio actual", "quién ganó", "quien gano")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower().strip()
    if not t:
        return False
    # Si hay una acción esperando confirmación, captura el sí/no.
    if _pendiente is not None and _es_respuesta_confirmacion(t):
        return True
    # Búsqueda explícitamente web → no es de sistema.
    if any(w in t for w in _WEB) and ("archivo" not in t and "carpeta" not in t):
        return False
    return any(g in t for g in _GATILLOS)


def _es_respuesta_confirmacion(t: str) -> bool:
    return (any(t == c or t.startswith(c + " ") for c in _CONFIRMA + _CANCELA))


def _fmt(r: dict) -> str:
    detalle = r.get("detalle", "")
    if r.get("datos"):
        detalle += "\n" + "\n".join(f"  {k}: {v}" for k, v in r["datos"].items())
    if r.get("resultados"):
        detalle += "\n" + "\n".join(f"  - {x}" for x in r["resultados"][:20])
    return detalle.strip()


def _describir(accion: str, params: dict) -> str:
    p = ", ".join(f"{k}={v}" for k, v in (params or {}).items())
    return f"{accion}({p})" if p else accion


def manejar(texto: str, contexto: dict = None) -> dict:
    global _pendiente
    t = (texto or "").lower().strip()

    # ── ¿Hay algo esperando confirmación? ──────────────────────────────
    if _pendiente is not None:
        accion, params, riesgo, desc = _pendiente
        if any(t == c or t.startswith(c + " ") for c in _CONFIRMA):
            _pendiente = None
            r = acciones.ejecutar(accion, params)
            estado = "✓ Hecho" if r.get("ok") else "No se pudo"
            return contrato.resultado(NOMBRE, "ejecutar",
                                      f"ejecuté {accion}" if r.get("ok") else f"falló {accion}",
                                      f"{estado}: {_fmt(r)}")
        if any(t == c or t.startswith(c + " ") for c in _CANCELA):
            _pendiente = None
            return contrato.resultado(NOMBRE, "cancelar", "cancelado",
                                      "Cancelado. No toqué nada.")
        # No fue sí ni no → descarto el pendiente y sigo interpretando normal.
        _pendiente = None

    # ── Interpretar el pedido en una acción concreta ───────────────────
    interp = cerebro.interpretar(texto)
    if not interp or not interp.get("accion"):
        return {"ok": False}  # no era comando de sistema → cae a conversación

    accion = interp["accion"]
    params = interp.get("params") or {}
    riesgo = acciones.riesgo_de(accion)
    desc = _describir(accion, params)

    # ── Verde: directo. Amarillo/Rojo: pedir confirmación. ─────────────
    if riesgo == acciones.VERDE:
        r = acciones.ejecutar(accion, params)
        estado = "✓" if r.get("ok") else "No se pudo"
        return contrato.resultado(NOMBRE, "ejecutar",
                                  f"{accion}" if r.get("ok") else f"falló {accion}",
                                  f"{estado} {_fmt(r)}")

    _pendiente = (accion, params, riesgo, desc)
    if riesgo == acciones.ROJO:
        aviso = ("⚠️ Acción DELICADA e irreversible-sensible. " +
                 ("Borrar va a la papelera (recuperable). " if accion == "borrar" else ""))
    else:
        aviso = "Acción que requiere tu OK. "
    return contrato.resultado(
        NOMBRE, "confirmar", "espero confirmación",
        f"{aviso}Voy a: {desc}.\n\n¿Confirmás? Respondé 'sí' para hacerlo o 'no' para cancelar.")