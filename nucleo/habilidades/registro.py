"""
nucleo/habilidades/registro.py
Registro modular de habilidades. Para sumar una habilidad nueva (cálculo,
internet, archivos...), la importás y la agregás a _SKILLS. Nada más cambia.

Cada habilidad debe exponer:
  - NOMBRE: str
  - detecta(texto, codigo_adjunto="") -> bool
  - manejar(texto, contexto=None) -> dict  con {ok, skill, modo, resumen, cuerpo}
"""
import logging

log = logging.getLogger("satella.habilidades")

# Importá acá cada habilidad y sumala a la lista.
from nucleo.habilidades.python import skill as habilidad_python

_SKILLS = [
    habilidad_python,
    # nucleo.habilidades.calculo, nucleo.habilidades.internet, ... (futuro)
]


def detectar_skill(texto: str, codigo_adjunto: str = ""):
    """Devuelve la primera habilidad que reclame el mensaje, o None."""
    for s in _SKILLS:
        try:
            if s.detecta(texto, codigo_adjunto):
                return s
        except Exception as e:
            log.error(f"[HAB] {getattr(s, 'NOMBRE', '?')} detecta() falló: {e}")
    return None