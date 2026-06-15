"""Habilidad NAVEGADOR de Satella — control de navegador real con Playwright,
agente autónomo con visión, modo observador + recetas, memoria de navegación
(aprendizaje continuo) y credenciales seguras."""
from . import motor, ojo  # noqa: F401

__all__ = ["motor", "ojo", "observador", "credenciales", "memoria", "conocimiento"]