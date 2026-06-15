"""
nucleo/habilidades/navegador/memoria.py — MEMORIA DE NAVEGACIÓN (aprendizaje continuo).

Cada vez que el agente CUMPLE una tarea, guarda el camino que funcionó (en forma
repetible: navegar/click-por-texto/hover/escribir/tecla) junto al objetivo y el
dominio. La próxima vez que pidas algo parecido en el mismo dominio, Satella REPITE
el camino aprendido en vez de re-pensarlo desde cero — así automatiza cada vez más
procesos con el tiempo y nada queda en el olvido.

Se guarda en datos/navegador/memoria/<dominio>.json.
"""
import json
import re
import time
from pathlib import Path

_DIR = Path("datos/navegador/memoria")

_STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "a", "que", "con",
         "por", "para", "me", "mi", "lo", "al", "su", "es", "ahora", "porfa", "porfavor",
         "dale", "quiero", "andá", "anda", "ve", "ponme", "poné", "pon", "buscá", "busca",
         "reproducí", "reproduce", "abrí", "abre", "this", "the"}


def _dominio(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return (m.group(1).replace("www.", "").lower() if m else "")


def _slug_dom(dom):
    return re.sub(r"[^\w.-]+", "_", dom or "sitio")


def _palabras(texto):
    toks = re.findall(r"[a-záéíóúñü0-9]+", (texto or "").lower())
    return {t for t in toks if len(t) > 2 and t not in _STOP}


def _archivo(dom):
    return _DIR / f"{_slug_dom(dom)}.json"


def _leer(dom):
    try:
        return json.loads(_archivo(dom).read_text(encoding="utf-8"))
    except Exception:
        return []


def _escribir(dom, data):
    _DIR.mkdir(parents=True, exist_ok=True)
    _archivo(dom).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def aprender(objetivo, pasos, url):
    """Guarda un camino que funcionó. Si ya había uno muy parecido, lo actualiza y le
    sube el contador de éxitos (refuerzo)."""
    dom = _dominio(url)
    if not dom or not pasos:
        return {"ok": False}
    # filtrar pasos no repetibles (scroll/esperar) y dejar los accionables
    limpio = [p for p in pasos if p.get("tipo") in ("navegar", "click", "hover", "input", "tecla")]
    if not limpio:
        return {"ok": False}
    data = _leer(dom)
    claves = _palabras(objetivo)
    for entrada in data:
        if _palabras(entrada["objetivo"]) == claves:        # mismo objetivo → refuerzo
            entrada.update({"pasos": limpio, "exitos": entrada.get("exitos", 1) + 1,
                            "fecha": time.strftime("%Y-%m-%d %H:%M")})
            _escribir(dom, data)
            return {"ok": True, "reforzado": True, "dominio": dom}
    data.append({"objetivo": objetivo, "claves": sorted(claves), "pasos": limpio,
                 "exitos": 1, "fecha": time.strftime("%Y-%m-%d %H:%M")})
    _escribir(dom, data)
    return {"ok": True, "reforzado": False, "dominio": dom}


def recordar(objetivo, url, umbral=0.6):
    """Busca un camino aprendido para este objetivo en el dominio actual. Devuelve la
    entrada si el solapamiento de palabras supera el umbral, o None."""
    dom = _dominio(url)
    if not dom:
        return None
    claves = _palabras(objetivo)
    if not claves:
        return None
    mejor, mejor_score = None, 0.0
    for entrada in _leer(dom):
        ec = set(entrada.get("claves", []))
        if not ec:
            continue
        score = len(claves & ec) / len(claves | ec)     # Jaccard
        if score > mejor_score:
            mejor, mejor_score = entrada, score
    if mejor and mejor_score >= umbral:
        return {**mejor, "score": round(mejor_score, 2), "dominio": dom}
    return None


def listar():
    if not _DIR.exists():
        return []
    out = []
    for f in sorted(_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for e in data:
                out.append({"dominio": f.stem, "objetivo": e.get("objetivo", ""),
                            "exitos": e.get("exitos", 1), "pasos": len(e.get("pasos", []))})
        except Exception:
            continue
    return out