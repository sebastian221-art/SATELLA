"""
nucleo/habilidades/python/aprendiz.py
Aprendiz de patrones: guarda cada interacción de código (qué se pidió, qué se
generó/analizó, el veredicto) en un dataset local. Acumula el "cuaderno" de la
habilidad para futuras mejoras y recuperación. Nunca rompe el flujo (todo en try).
"""
import json
import os
import time
import logging

log = logging.getLogger("satella.habilidad.python")

# datos/aprendizaje_codigo.json en la raíz del proyecto.
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ARCHIVO = os.path.join(_RAIZ, "datos", "aprendizaje_codigo.json")
_MAX = 1000


def registrar(modo: str, entrada: str, resultado: dict) -> None:
    try:
        registro = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "modo": modo,
            "entrada": (entrada or "")[:500],
            "resumen": (resultado or {}).get("resumen", "")[:300],
        }
        datos = []
        if os.path.exists(_ARCHIVO):
            try:
                with open(_ARCHIVO, "r", encoding="utf-8") as f:
                    datos = json.load(f)
            except Exception:
                datos = []
        datos.append(registro)
        if len(datos) > _MAX:
            datos = datos[-_MAX:]
        os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
        with open(_ARCHIVO, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug(f"[PY] aprendiz no pudo registrar: {e}")


def cuantos() -> int:
    try:
        with open(_ARCHIVO, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0