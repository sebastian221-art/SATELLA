"""
nucleo/habilidades/creador/escritor.py
Maneja el disco. Las habilidades nuevas van a REVISIÓN en
nucleo/habilidades/_pendientes/<nombre>/ (el "_" hace que el registro NO las
descubra). Al aprobarlas, se mueven a nucleo/habilidades/<nombre>/, donde el
registro las activa. Esa es la compuerta de seguridad.
"""
import os
import shutil

import nucleo.habilidades as _paquete

_BASE = os.path.dirname(_paquete.__file__)
_STAGING = os.path.join(_BASE, "_pendientes")


def estacionar(nombre: str, codigo: str) -> str:
    destino = os.path.join(_STAGING, nombre)
    os.makedirs(destino, exist_ok=True)
    open(os.path.join(destino, "__init__.py"), "w", encoding="utf-8").close()
    with open(os.path.join(destino, "skill.py"), "w", encoding="utf-8") as f:
        f.write(codigo)
    return destino


def listar_pendientes() -> list:
    if not os.path.isdir(_STAGING):
        return []
    return sorted(d for d in os.listdir(_STAGING)
                  if os.path.isdir(os.path.join(_STAGING, d)))


def aprobar(nombre: str) -> tuple:
    """Mueve la habilidad de revisión a activa. Devuelve (ok, info)."""
    if not nombre:
        return (False, "No me dijiste qué habilidad aprobar.")
    origen = os.path.join(_STAGING, nombre)
    if not os.path.isdir(origen):
        pend = listar_pendientes()
        extra = f" Hay en revisión: {', '.join(pend)}." if pend else ""
        return (False, f"No hay ninguna habilidad '{nombre}' en revisión.{extra}")
    destino = os.path.join(_BASE, nombre)
    if os.path.exists(destino):
        # Ya existe: la reemplazamos (re-cristalizar/actualizar una habilidad).
        shutil.rmtree(destino)
    shutil.move(origen, destino)
    return (True, destino)