"""
nucleo/habilidades/python/aprendiz.py — CUADERNO de soluciones (de verdad).
Antes solo guardaba metadata (no servía para nada). Ahora guarda la SOLUCIÓN
completa: el pedido, el código generado, el lenguaje y el veredicto. Y permite
RECUPERAR una solución pasada para un pedido casi idéntico (cache inteligente:
más rápido y sin gastar cuota). Es la semilla del Coral (Fase 2).
Nunca rompe el flujo (todo en try).
"""
import os
import re
import json
import time
import logging

log = logging.getLogger("satella.habilidad.python")

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ARCHIVO = os.path.join(_RAIZ, "datos", "aprendizaje_codigo.json")
_MAX = 1000


def _cargar() -> list:
    if os.path.exists(_ARCHIVO):
        try:
            with open(_ARCHIVO, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _guardar(datos: list) -> None:
    os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
    with open(_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def registrar(modo: str, entrada: str, resultado: dict,
              codigo: str = "", lenguaje: str = "", verdicto=None) -> None:
    """Guarda la solución COMPLETA (incluido el código) en el cuaderno."""
    try:
        registro = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "modo": modo,
            "lenguaje": lenguaje or "",
            "entrada": (entrada or "")[:500],
            "codigo": (codigo or "")[:8000],          # la solución real
            "verdicto": verdicto,                       # True/False/None
            "resumen": (resultado or {}).get("resumen", "")[:300],
        }
        datos = _cargar()
        datos.append(registro)
        if len(datos) > _MAX:
            datos = datos[-_MAX:]
        _guardar(datos)
    except Exception as e:
        log.debug(f"[PY] aprendiz no pudo registrar: {e}")


# ── Recuperación (cache inteligente) ─────────────────────────────────────────
_STOP = frozenset({"un", "una", "el", "la", "de", "que", "en", "y", "o", "a",
                   "con", "para", "los", "las", "me", "mi", "se", "lo"})


def _tokens(texto: str) -> set:
    palabras = re.findall(r"[a-záéíóúñ0-9]+", (texto or "").lower())
    return {p for p in palabras if p not in _STOP and len(p) > 1}


def buscar_similar(entrada: str, lenguaje: str = "", umbral: float = 0.85):
    """
    Busca una solución pasada EXITOSA para un pedido casi idéntico (Jaccard).
    Umbral alto a propósito: solo reusa si es prácticamente el mismo pedido,
    para no devolver código equivocado. Devuelve el registro o None.
    """
    try:
        objetivo = _tokens(entrada)
        if not objetivo:
            return None
        mejor, mejor_sim = None, 0.0
        for r in _cargar():
            if not r.get("codigo") or r.get("verdicto") is False:
                continue
            if lenguaje and r.get("lenguaje") and r["lenguaje"] != lenguaje:
                continue
            cand = _tokens(r.get("entrada", ""))
            if not cand:
                continue
            inter = len(objetivo & cand)
            union = len(objetivo | cand)
            sim = inter / union if union else 0.0
            if sim > mejor_sim:
                mejor, mejor_sim = r, sim
        return mejor if mejor_sim >= umbral else None
    except Exception:
        return None


def cuantos() -> int:
    return len(_cargar())