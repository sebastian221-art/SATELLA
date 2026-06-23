"""
nucleo/habilidades/gobernador/detector.py
Detecta cuándo el mensaje es para GESTIONAR el Gobernador (ver permisos, cambiar
de modo, kill switch, ver auditoría, aprobar/rechazar pendientes) y a qué
intención concreta corresponde. Es deliberadamente específico para no robarle
mensajes a copia/analisis.
"""
import re

_GATILLOS = (
    "gobernador", "permiso", "permisos", "modo seguro", "modo normal",
    "modo auditoria", "modo auditoría", "kill switch", "killswitch",
    "frená todo", "frena todo", "frená satella", "pará todo", "para todo",
    "detené todo", "detener todo", "auditoría", "auditoria", "qué hiciste",
    "que hiciste", "qué hizo satella", "que hizo satella", "registro de acciones",
    "historial de acciones", "pendientes", "aprobá", "aproba", "apruebo",
    "rechazá", "rechaza", "denegá", "denega", "lista blanca", "allowlist",
    "política de seguridad", "politica de seguridad", "qué podés hacer sola",
    "que podes hacer sola",
)

_HEX = re.compile(r"\b([0-9a-f]{8})\b")


def _t(s):
    return (s or "").lower()


def detecta(texto, codigo_adjunto=""):
    t = _t(texto)
    # "aprobá/activá la HABILIDAD X" es para el CREADOR, no para el gobernador
    # (el gobernador aprueba TOKENS de confirmación, no habilidades).
    if any(h in t for h in ("habilidad", "skill")) and \
       any(a in t for a in ("aprobá", "aproba", "apruebo", "aprobar",
                            "activá", "activa", "activar")):
        return False
    return any(g in t for g in _GATILLOS)


def intencion(texto):
    """Devuelve (accion, arg). accion ∈ kill/modo/auditoria/pendientes/aprobar/rechazar/politica."""
    t = _t(texto)

    # Kill switch (prender o apagar)
    if any(k in t for k in ("kill switch", "killswitch", "frená todo", "frena todo",
                            "pará todo", "para todo", "detené todo", "detener todo",
                            "frená satella")):
        if any(k in t for k in ("desactiv", "apag", "quitá", "quita", "saca", "off",
                                "reanud", "soltá", "solta", "libera")):
            return ("kill", False)
        return ("kill", True)

    # Cambios de modo
    if "modo seguro" in t:
        return ("modo", "seguro")
    if "modo normal" in t:
        return ("modo", "normal")
    if "modo auditoria" in t or "modo auditoría" in t:
        return ("modo", "auditoria")

    # Ver auditoría
    if any(k in t for k in ("auditor", "qué hiciste", "que hiciste", "qué hizo",
                            "que hizo", "registro de acciones", "historial de acciones")):
        return ("auditoria", None)

    # Pendientes
    if "pendiente" in t:
        return ("pendientes", None)

    # Aprobar / rechazar (con token de 8 hex si lo trae)
    if any(k in t for k in ("aprobá", "aproba", "apruebo", "aprobar")):
        m = _HEX.search(t)
        return ("aprobar", m.group(1) if m else None)
    if any(k in t for k in ("rechazá", "rechaza", "rechazar", "denegá", "denega", "denegar")):
        m = _HEX.search(t)
        return ("rechazar", m.group(1) if m else None)

    # Por defecto: mostrar la política/estado actual
    return ("politica", None)