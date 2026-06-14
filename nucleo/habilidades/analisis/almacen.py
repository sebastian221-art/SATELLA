"""
nucleo/habilidades/analisis/almacen.py
Base de datos local de análisis. Guarda cada análisis (por dominio + ruta) con
timestamp, permite traer el historial de una URL y comparar (diff) contra el
análisis anterior. Sustrato para el histórico y para alimentar al navegador #4.

Formato: un JSON por dominio en datos/analisis/<dominio>.json
  { "ruta1": [ {ts, resumen, hechos}, ... ],  "ruta2": [...] }
"""
import os
import json
import time
import hashlib
from urllib.parse import urlparse

_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "datos", "analisis")


def _dir():
    os.makedirs(_BASE, exist_ok=True)
    return _BASE


def _clave(url):
    p = urlparse(url or "")
    dominio = (p.netloc or "local").replace(":", "_")
    ruta = (p.path or "/") + (("?" + p.query) if p.query else "")
    safe = hashlib.md5(dominio.encode()).hexdigest()[:10]
    return dominio, safe, ruta


def _archivo(dominio, safe):
    return os.path.join(_dir(), f"{dominio[:40]}_{safe}.json")


def _leer(dominio, safe):
    f = _archivo(dominio, safe)
    if os.path.exists(f):
        try:
            with open(f, encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}
    return {}


def guardar(url, resumen, hechos):
    """Persiste un análisis. Devuelve dict con {nuevo, cambios} vs el anterior."""
    if not url:
        return {"guardado": False}
    dominio, safe, ruta = _clave(url)
    db = _leer(dominio, safe)
    historial = db.get(ruta, [])
    anterior = historial[-1] if historial else None

    entrada = {"ts": int(time.time()), "fecha": time.strftime("%Y-%m-%d %H:%M"),
               "resumen": resumen, "hechos": hechos}
    historial.append(entrada)
    db[ruta] = historial[-20:]  # cap a 20 versiones por ruta
    try:
        with open(_archivo(dominio, safe), "w", encoding="utf-8") as fp:
            json.dump(db, fp, ensure_ascii=False, indent=1)
        ok = True
    except Exception:
        ok = False

    cambios = _diff(anterior["hechos"], hechos) if anterior else None
    return {"guardado": ok, "es_primero": anterior is None, "version": len(historial),
            "cambios": cambios}


def historial(url):
    if not url:
        return []
    dominio, safe, ruta = _clave(url)
    return _leer(dominio, safe).get(ruta, [])


def _diff(viejo, nuevo):
    """Diferencias relevantes entre dos snapshots de hechos."""
    if not isinstance(viejo, dict) or not isinstance(nuevo, dict):
        return None
    cambios = []

    def _set(d, k):
        v = d.get(k)
        return set(v) if isinstance(v, list) else set()

    for campo, etiqueta in [("tecnologias", "Tecnologías"),
                            ("endpoints", "Endpoints")]:
        a, b = _set(viejo, campo), _set(nuevo, campo)
        if a - b: cambios.append(f"{etiqueta} que desaparecieron: {', '.join(sorted(a - b))}")
        if b - a: cambios.append(f"{etiqueta} nuevos: {', '.join(sorted(b - a))}")

    # seguridad: headers
    sa = set((viejo.get("seguridad") or {}).get("headers_presentes", {}))
    sb = set((nuevo.get("seguridad") or {}).get("headers_presentes", {}))
    if sb - sa: cambios.append(f"Headers de seguridad agregados: {', '.join(sorted(sb - sa))}")
    if sa - sb: cambios.append(f"Headers de seguridad quitados: {', '.join(sorted(sa - sb))}")

    return cambios or ["Sin cambios estructurales relevantes."]