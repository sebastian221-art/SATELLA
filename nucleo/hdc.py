"""
nucleo/hdc.py — HDC: memoria asociativa hiperdimensional para Coral.

Da matcheo DIFUSO de conceptos, en CPU, en dos capas:
  1) N-GRAMAS (HDC puro): cada texto se codifica como un hipervector bipolar
     (~10k dims) bundle de sus trigramas de caracteres. Textos parecidos comparten
     trigramas → vectores parecidos. Reconoce typos, plurales, variantes
     ('navegdor'≈'navegador', 'navegadores'≈'navegador') sin diccionario.
  2) ALIAS (mapa growable): sinónimos reales, incluso de otro idioma
     ('browser'→'navegador', 'repo'→'repositorio'). Determinista, sin modelo pesado.
     Satella puede aprender alias nuevos con el tiempo.

Necesita numpy (liviano, CPU). Si no está, Coral cae a matcheo exacto sin romperse.
"""
import json
import logging
import os
import re

log = logging.getLogger("satella.hdc")

try:
    import numpy as np
    _HAY_NUMPY = True
except Exception:
    _HAY_NUMPY = False

_DIM = 10000
_cache_token: dict = {}    # token -> hipervector (cache en memoria)
_alias: dict = {}          # alias_norm -> concepto_canonico
_ruta_alias: str = ""

# Alias semilla comunes en el mundo dev (Satella puede agregar más).
_ALIAS_SEMILLA = {
    "browser": "navegador", "repo": "repositorio", "repos": "repositorio",
    "bug": "error", "deploy": "despliegue", "commit": "commit",
    "front": "frontend", "back": "backend", "db": "base de datos",
    "pc": "computadora", "compu": "computadora",
}


def disponible() -> bool:
    return _HAY_NUMPY


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ── Hipervectores ────────────────────────────────────────────────────────────
def _hv_token(token: str):
    """Hipervector bipolar estable para un token (mismo token → mismo vector)."""
    if token in _cache_token:
        return _cache_token[token]
    semilla = abs(hash(("hdc", token))) % (2**32)
    rng = np.random.default_rng(semilla)
    hv = rng.integers(0, 2, size=_DIM, dtype=np.int8) * 2 - 1  # {-1,+1}
    _cache_token[token] = hv
    return hv


def _trigramas(texto: str) -> list:
    t = f"#{_norm(texto)}#"
    return [t[i:i + 3] for i in range(len(t) - 2)] or [t]


def vector(texto: str):
    """Codifica un texto como hipervector (bundle de sus trigramas)."""
    grams = _trigramas(texto)
    acc = np.zeros(_DIM, dtype=np.int32)
    for g in grams:
        acc += _hv_token(g)
    # binarizar (signo); empates → +1
    return np.where(acc >= 0, 1, -1).astype(np.int8)


def _similitud(a, b) -> float:
    """Coseno normalizado en [-1,1] (para bipolar = dot / DIM). int32 para no desbordar."""
    return float(np.dot(a.astype(np.int32), b.astype(np.int32))) / _DIM


# ── Alias (sinónimos) ────────────────────────────────────────────────────────
def inicializar(ruta_alias: str = None):
    global _ruta_alias, _alias
    if not ruta_alias:
        try:
            from config import EPISODIOS_FILE
            ruta_alias = os.path.join(os.path.dirname(EPISODIOS_FILE), "coral_alias.json")
        except Exception:
            ruta_alias = "coral_alias.json"
    _ruta_alias = ruta_alias
    if os.path.exists(_ruta_alias):
        try:
            with open(_ruta_alias, encoding="utf-8") as f:
                _alias = json.load(f)
        except Exception:
            _alias = {}
    if not _alias:
        _alias = dict(_ALIAS_SEMILLA)
        _guardar_alias()
    estado = "con numpy" if _HAY_NUMPY else "SIN numpy (matcheo exacto)"
    log.info(f"HDC: listo {estado} | {len(_alias)} alias")


def _guardar_alias():
    if not _ruta_alias:
        return
    try:
        os.makedirs(os.path.dirname(_ruta_alias) or ".", exist_ok=True)
        with open(_ruta_alias, "w", encoding="utf-8") as f:
            json.dump(_alias, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"HDC: error guardando alias: {e}")


def agregar_alias(alias: str, canonico: str):
    a, c = _norm(alias), _norm(canonico)
    if a and c and a != c:
        _alias[a] = canonico.strip()
        _guardar_alias()


def resolver_alias(token: str) -> str:
    """Si el token es un alias conocido, devuelve el concepto canónico; si no, el mismo."""
    return _alias.get(_norm(token), token)


# ── Matcheo difuso de conceptos ──────────────────────────────────────────────
def mejores(texto: str, conceptos: list, umbral: float = 0.35, k: int = 4) -> list:
    """Devuelve los conceptos (de la lista) más parecidos al texto por n-gramas."""
    if not _HAY_NUMPY or not conceptos or not texto.strip():
        return []
    vq = vector(texto)
    puntuados = []
    for c in conceptos:
        s = _similitud(vq, vector(c))
        if s >= umbral:
            puntuados.append((s, c))
    puntuados.sort(reverse=True)
    return [c for _, c in puntuados[:k]]