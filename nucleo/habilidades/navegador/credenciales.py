"""
nucleo/habilidades/navegador/credenciales.py — CREDENCIALES SEGURAS (Fase 4C final).

Las contraseñas se guardan en el LLAVERO del sistema (en Windows, el Administrador de
credenciales), NUNCA en texto plano ni en el chat. Acá solo guardamos un índice NO
secreto (dominio → usuario) para poder listar; la contraseña vive únicamente en el
llavero del sistema operativo, cifrada por Windows.

Flujo seguro: el usuario escribe su login en el NAVEGADOR (no en el chat); Satella lo
lee del DOM y lo manda al llavero. Así la contraseña nunca aparece en la conversación.
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("satella.navegador")

_SERVICIO = "satella-navegador"
_INDICE = Path("datos/navegador/credenciales.json")   # solo dominio→usuario (sin claves)

_kr = None
try:
    import keyring as _kr
except Exception as e:                                 # pragma: no cover
    log.warning(f"[NAV] keyring no disponible: {e} — las credenciales no se podrán guardar")


def disponible() -> bool:
    if _kr is None:
        return False
    try:
        _kr.get_keyring()
        return True
    except Exception:
        return False


def _leer_indice() -> dict:
    try:
        return json.loads(_INDICE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_indice(d: dict):
    _INDICE.parent.mkdir(parents=True, exist_ok=True)
    _INDICE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _clave(dominio: str) -> str:
    return f"{_SERVICIO}:{(dominio or '').replace('www.', '').lower()}"


def guardar(dominio: str, usuario: str, contrasena: str) -> dict:
    """Guarda usuario+contraseña para un dominio. La contraseña va al llavero del SO."""
    if not disponible():
        return {"ok": False, "razon": "El llavero del sistema no está disponible."}
    dom = (dominio or "").replace("www.", "").lower()
    if not dom or not contrasena:
        return {"ok": False, "razon": "Faltan datos (dominio o contraseña)."}
    try:
        _kr.set_password(_clave(dom), usuario or "usuario", contrasena)
    except Exception as e:
        return {"ok": False, "razon": repr(e)}
    idx = _leer_indice()
    idx[dom] = usuario or "usuario"
    _guardar_indice(idx)
    return {"ok": True, "dominio": dom, "usuario": usuario}


def obtener(dominio: str) -> dict:
    """Devuelve {usuario, contrasena} para un dominio, o None si no hay."""
    if not disponible():
        return None
    dom = (dominio or "").replace("www.", "").lower()
    idx = _leer_indice()
    usuario = idx.get(dom)
    if usuario is None:
        # intento por coincidencia parcial del dominio
        for d, u in idx.items():
            if d in dom or dom in d:
                dom, usuario = d, u
                break
    if usuario is None:
        return None
    try:
        contrasena = _kr.get_password(_clave(dom), usuario)
    except Exception:
        contrasena = None
    if not contrasena:
        return None
    return {"dominio": dom, "usuario": usuario, "contrasena": contrasena}


def listar() -> list:
    """Dominios con credencial guardada (sin exponer contraseñas)."""
    return [{"dominio": d, "usuario": u} for d, u in _leer_indice().items()]


def existe(dominio: str) -> bool:
    """¿Hay credencial para este dominio? (sin tocar el llavero)."""
    dom = (dominio or "").replace("www.", "").lower()
    idx = _leer_indice()
    if dom in idx:
        return True
    return any(d in dom or dom in d for d in idx) if dom else False


def borrar(dominio: str) -> dict:
    dom = (dominio or "").replace("www.", "").lower()
    idx = _leer_indice()
    usuario = idx.get(dom)
    if usuario is None:
        for d, u in list(idx.items()):
            if d in dom or dom in d:
                dom, usuario = d, u
                break
    if usuario is None:
        return {"ok": False, "razon": "no_existe"}
    try:
        _kr.delete_password(_clave(dom), usuario)
    except Exception:
        pass
    idx.pop(dom, None)
    _guardar_indice(idx)
    return {"ok": True, "dominio": dom}