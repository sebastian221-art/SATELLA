"""
nucleo/habilidades/navegador/
Control de navegador de Satella. Núcleo (4A): Playwright con perfil persistente
en un hilo dedicado, panel en vivo, modo navegador y percepción (el ojo), todo
gobernado por el Gobernador de permisos.

API para el servidor (streaming del panel) y futuras fases:
    from nucleo.habilidades import navegador
    navegador.motor.activo() / screenshot_b64() / estado()
"""
from . import motor, ojo  # noqa: F401

__all__ = ["motor", "ojo", "observador"]