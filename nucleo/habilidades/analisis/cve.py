"""
nucleo/habilidades/analisis/cve.py
Cruza librerías detectadas (con versión) contra vulnerabilidades conocidas vía
la API pública de OSV.dev (Google). Sin API key. Si no hay red o no hay versión,
degrada con elegancia (no rompe el análisis).

OSV cubre PyPI, npm, etc. Para librerías front (jQuery, etc.) usamos el ecosistema
npm como mejor aproximación pública.
"""
import json

try:
    import requests
    _REQ = True
except Exception:
    _REQ = False
import urllib.request

# Mapa librería detectada → (ecosistema OSV, nombre del paquete)
_MAPA = {
    "jquery": ("npm", "jquery"),
    "react": ("npm", "react"),
    "vue": ("npm", "vue"),
    "angular": ("npm", "@angular/core"),
    "bootstrap": ("npm", "bootstrap"),
    "lodash": ("npm", "lodash"),
    "d3": ("npm", "d3"),
    "three.js": ("npm", "three"),
    "axios": ("npm", "axios"),
    "swiper": ("npm", "swiper"),
}

_URL = "https://api.osv.dev/v1/query"


def _consultar(ecosistema, paquete, version):
    cuerpo = json.dumps({"version": version, "package": {"name": paquete, "ecosystem": ecosistema}}).encode()
    try:
        if _REQ:
            r = requests.post(_URL, data=cuerpo, timeout=10,
                              headers={"Content-Type": "application/json"})
            return r.json()
        req = urllib.request.Request(_URL, data=cuerpo, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def revisar(librerias):
    """
    librerias: lista tipo ["jQuery 1.12.4", "React"].
    Devuelve dict {disponible, resultados:[{lib, version, vulns:[{id,resumen,severidad}]}], sin_version:[...]}
    """
    resultados, sin_version = [], []
    for entrada in librerias or []:
        partes = entrada.split()
        nombre = partes[0].lower()
        version = partes[1] if len(partes) > 1 else None
        if nombre not in _MAPA:
            continue
        if not version:
            sin_version.append(entrada)
            continue
        eco, paquete = _MAPA[nombre]
        data = _consultar(eco, paquete, version)
        if data is None:
            return {"disponible": False, "resultados": [], "sin_version": sin_version,
                    "error": "No se pudo consultar OSV (sin red o timeout)."}
        vulns = []
        for v in (data.get("vulns") or [])[:6]:
            sev = ""
            for s in v.get("severity", []):
                sev = s.get("score", "")
            vulns.append({"id": v.get("id", ""), "resumen": (v.get("summary") or "")[:120], "severidad": sev})
        resultados.append({"lib": partes[0], "version": version, "vulns": vulns})
    return {"disponible": True, "resultados": resultados, "sin_version": sin_version}


def revisar_paquete(ecosistema, nombre, version):
    """CVE directo para un paquete por su propio ecosistema (PyPI/npm)."""
    if not version:
        return {"disponible": False, "error": "sin versión"}
    data = _consultar(ecosistema, nombre, version)
    if data is None:
        return {"disponible": False, "error": "No se pudo consultar OSV (sin red o timeout)."}
    vulns = []
    for v in (data.get("vulns") or [])[:8]:
        sev = ""
        for s in v.get("severity", []):
            sev = s.get("score", "")
        vulns.append({"id": v.get("id", ""), "resumen": (v.get("summary") or "")[:120], "severidad": sev})
    return {"disponible": True, "resultados": [{"lib": nombre, "version": version, "vulns": vulns}],
            "sin_version": []}


def como_texto(rev):
    if not rev.get("disponible"):
        return "  (no se pudo consultar la base de CVEs: " + rev.get("error", "") + ")"
    L = []
    for r in rev.get("resultados", []):
        if r["vulns"]:
            L.append(f"  ⚠ {r['lib']} {r['version']}: {len(r['vulns'])} vulnerabilidad(es) conocida(s)")
            for v in r["vulns"]:
                sev = f" [{v['severidad']}]" if v["severidad"] else ""
                L.append(f"      · {v['id']}{sev}: {v['resumen']}")
        else:
            L.append(f"  ✓ {r['lib']} {r['version']}: sin CVEs conocidas en OSV")
    for s in rev.get("sin_version", []):
        L.append(f"  ? {s}: no se pudo determinar la versión (no se chequeó CVE)")
    return "\n".join(L) if L else "  (sin librerías mapeables a CVE)"