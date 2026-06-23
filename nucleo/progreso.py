"""
nucleo/progreso.py — Canal de progreso desacoplado.
Las habilidades que tardan (Claude Code como subproceso) pueden avisar al usuario
"sigo trabajando" sin conocer el servidor ni SocketIO. El servidor registra un
"sink" (una función que reenvía el texto al chat); las habilidades solo llaman
progreso.emitir("..."). Si nadie registró sink, es no-op (no rompe nada, ej. tests).
"""
import logging

log = logging.getLogger("satella.progreso")

_sink = None


def set_sink(fn) -> None:
    """El servidor registra acá la función que reenvía el progreso al chat."""
    global _sink
    _sink = fn


def emitir(texto: str) -> None:
    """Una habilidad avisa su progreso. Llega al chat si hay sink; si no, no-op."""
    if _sink is None:
        return
    try:
        _sink(texto)
    except Exception as e:
        log.debug(f"[PROGRESO] sink falló: {e}")