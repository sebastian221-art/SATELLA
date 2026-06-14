"""
nucleo/habilidades/gobernador/motor.py
EL MOTOR DEL GOBERNADOR. Es la puerta por la que TODA habilidad que actúe sobre
el mundo real (navegador, agentes, OS) debe pasar antes de ejecutar.

Uso desde una habilidad futura:

    from nucleo.habilidades.gobernador import motor, politica
    v = motor.evaluar("abrir y postear en mi-sitio.com",
                      nivel=politica.NAVEGACION, objetivo="mi-sitio.com", propio=True)
    if v["veredicto"] == politica.PERMITIDO:
        ...hacer la acción...
    elif v["veredicto"] == politica.CONFIRMAR:
        # esperar a que el usuario confirme el token v["token"]
        ...
    else:  # DENEGADO
        ...no hacer nada...

Estado persistente (modo, kill switch, allowlist) en datos/seguridad/estado.json.
Confirmaciones pendientes viven en memoria (se resuelven en la misma sesión).
"""
import json
import logging
import secrets
from pathlib import Path

from . import politica, auditoria

log = logging.getLogger("satella.gobernador")

_DIR = Path(__file__).resolve().parents[3] / "datos" / "seguridad"
_ESTADO_PATH = _DIR / "estado.json"

_DEFAULT = {
    "modo": politica.MODO_NORMAL,
    "kill": False,
    "allow_dominios": [],   # dominios web pre-aprobados (navegación sin confirmar)
    "allow_rutas": [],      # rutas locales pre-aprobadas (escritura sin confirmar)
}
_estado = dict(_DEFAULT)
_pendientes = {}            # token -> datos de la acción esperando confirmación


# ── Persistencia ─────────────────────────────────────────────────────────────
def _cargar():
    global _estado
    if _ESTADO_PATH.exists():
        try:
            with open(_ESTADO_PATH, encoding="utf-8") as f:
                _estado = {**_DEFAULT, **json.load(f)}
            return
        except Exception as e:
            log.error(f"[GOB] estado corrupto, uso defaults: {e}")
    _estado = dict(_DEFAULT)


def _guardar():
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        with open(_ESTADO_PATH, "w", encoding="utf-8") as f:
            json.dump(_estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[GOB] no se pudo guardar estado: {e}")


_cargar()


# ── Control (lo maneja la skill por chat) ────────────────────────────────────
def modo(nombre: str = None):
    """Lee el modo actual, o lo cambia si se pasa uno válido."""
    global _estado
    if nombre is None:
        return _estado["modo"]
    if nombre not in politica.MODOS:
        return _estado["modo"]
    _estado["modo"] = nombre
    _guardar()
    auditoria.registrar({"evento": "cambio_modo", "modo": nombre})
    return _estado["modo"]


def kill(activar: bool = None):
    """Lee el kill switch, o lo prende/apaga. Prendido = bloquea toda acción con efecto."""
    global _estado
    if activar is None:
        return _estado["kill"]
    _estado["kill"] = bool(activar)
    _guardar()
    auditoria.registrar({"evento": "kill_switch", "activo": _estado["kill"]})
    return _estado["kill"]


def allow(dominio: str = None, ruta: str = None):
    """Agrega un dominio (navegación) o ruta (escritura) a la lista blanca."""
    if dominio:
        _estado["allow_dominios"].append(dominio.lower().strip())
    if ruta:
        _estado["allow_rutas"].append(ruta.strip())
    _guardar()
    auditoria.registrar({"evento": "allowlist_add", "dominio": dominio, "ruta": ruta})


def politica_actual() -> dict:
    """Snapshot del estado actual (modo, kill, allowlists)."""
    return dict(_estado)


def _en_allowlist(nivel: str, objetivo: str) -> bool:
    o = (objetivo or "").lower()
    if not o:
        return False
    if nivel == politica.NAVEGACION:
        return any(d and d in o for d in _estado["allow_dominios"])
    if nivel == politica.ESCRITURA:
        return any(r and o.startswith(r.lower()) for r in _estado["allow_rutas"])
    return False


# ── LA PUERTA ────────────────────────────────────────────────────────────────
def evaluar(accion: str, nivel: str = None, objetivo: str = "",
            propio: bool = False, detalle: str = "") -> dict:
    """
    Evalúa una acción ANTES de ejecutarla. Devuelve un dict:
        {veredicto, nivel, razon, [token]}
    - PERMITIDO  → la habilidad puede actuar.
    - CONFIRMAR  → hay que esperar la decisión del usuario sobre `token`.
    - DENEGADO   → no actuar.
    Toda evaluación queda auditada.
    """
    nivel = nivel or politica.clasificar(accion, objetivo)

    # 1) Kill switch: corta todo lo que tenga efecto (la lectura sigue pasando).
    if _estado["kill"] and nivel != politica.LECTURA:
        return _resolver(accion, objetivo, nivel, politica.DENEGADO,
                         "Kill switch activo: toda acción con efecto está bloqueada.")

    # 2) Prohibido: nunca, ni en lo propio.
    if nivel == politica.PROHIBIDO:
        return _resolver(accion, objetivo, nivel, politica.DENEGADO,
                         "Acción prohibida: nunca se permite (credenciales ajenas, "
                         "suplantación o ataque a terceros).")

    # 3) Allowlist: el usuario lo aprobó de antemano.
    if _en_allowlist(nivel, objetivo):
        return _resolver(accion, objetivo, nivel, politica.PERMITIDO,
                         "En allowlist: lo aprobaste de antemano.")

    # 4) Regla de política según modo + nivel + propio.
    veredicto, razon = politica.decidir(_estado["modo"], nivel, propio)
    token = None
    if veredicto == politica.CONFIRMAR:
        token = secrets.token_hex(4)
        _pendientes[token] = {
            "accion": accion, "nivel": nivel, "objetivo": objetivo,
            "propio": propio, "detalle": detalle, "razon": razon,
        }
    return _resolver(accion, objetivo, nivel, veredicto, razon, token)


def _resolver(accion, objetivo, nivel, veredicto, razon, token=None) -> dict:
    auditoria.registrar({
        "evento": "evaluar", "accion": str(accion)[:200], "objetivo": str(objetivo)[:200],
        "nivel": nivel, "veredicto": veredicto, "token": token,
    })
    v = {"veredicto": veredicto, "nivel": nivel, "razon": razon}
    if token:
        v["token"] = token
    return v


# ── Confirmaciones pendientes ────────────────────────────────────────────────
def pendientes() -> list:
    return [{"token": t, **d} for t, d in _pendientes.items()]


def confirmar(token: str, aprobado: bool) -> dict:
    """Resuelve un pendiente. La habilidad que esperaba el token actúa o aborta según esto."""
    p = _pendientes.pop(token, None)
    if not p:
        return {"ok": False, "razon": "Token no encontrado o ya resuelto."}
    auditoria.registrar({
        "evento": "confirmacion", "token": token, "aprobado": bool(aprobado),
        "accion": str(p["accion"])[:200], "objetivo": str(p["objetivo"])[:200],
    })
    return {"ok": True, "aprobado": bool(aprobado), "accion": p}


def limpiar_pendientes() -> int:
    n = len(_pendientes)
    _pendientes.clear()
    return n