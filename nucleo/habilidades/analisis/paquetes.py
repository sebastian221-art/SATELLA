"""
nucleo/habilidades/analisis/paquetes.py
Analiza un PAQUETE/LIBRERÍA (spaCy, requests, react, lodash…): metadatos de
PyPI o npm, dependencias, salud del repo (GitHub: estrellas, último push, issues,
si está archivado) y CVEs conocidas vía OSV. Todo con APIs públicas, sin key.

Degrada con elegancia: si no hay red o no encuentra el paquete, lo dice.
"""
import re
import json

try:
    import requests
    _REQ = True
except Exception:
    _REQ = False
import urllib.request

from . import cve

_UA = "SatellaAnalizador/1.0"


def _get_json(url, timeout=10):
    try:
        if _REQ:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
            if r.status_code >= 400:
                return None
            return r.json()
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def resolver(nombre):
    """Busca el paquete en PyPI y luego en npm. Devuelve (ecosistema, data) o (None, None)."""
    py = _get_json(f"https://pypi.org/pypi/{nombre}/json")
    if py:
        return "PyPI", py
    npm = _get_json(f"https://registry.npmjs.org/{nombre}")
    if npm and not npm.get("error"):
        return "npm", npm
    return None, None


def _repo_github(url):
    if not url:
        return None
    m = re.search(r"github\.com[/:]([^/]+)/([^/#?]+)", url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2).replace(".git", "")
    data = _get_json(f"https://api.github.com/repos/{owner}/{repo}")
    if not data:
        return None
    return {
        "estrellas": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "issues_abiertas": data.get("open_issues_count"),
        "ultimo_push": (data.get("pushed_at") or "")[:10],
        "archivado": data.get("archived"),
        "lenguaje": data.get("language"),
        "licencia_repo": (data.get("license") or {}).get("spdx_id"),
    }


def analizar(nombre):
    eco, data = resolver(nombre)
    if not eco:
        return {"ok": False, "error": f"No encontré '{nombre}' en PyPI ni npm (¿typo, o sin red?)."}

    f = {"ok": True, "nombre": nombre, "ecosistema": eco}

    if eco == "PyPI":
        info = data.get("info", {})
        f["version"] = info.get("version", "")
        f["resumen"] = (info.get("summary") or "")[:200]
        f["licencia"] = info.get("license") or (info.get("classifiers") and _licencia_de_clasif(info["classifiers"])) or ""
        f["autor"] = info.get("author") or info.get("author_email") or ""
        f["home"] = info.get("home_page") or ""
        urls = info.get("project_urls") or {}
        f["repo"] = next((v for k, v in urls.items() if "github" in (v or "").lower()), "")
        reqs = info.get("requires_dist") or []
        f["dependencias"] = [r.split(";")[0].strip() for r in reqs][:15]
        f["num_dependencias"] = len(reqs)
        f["python_requiere"] = info.get("requires_python") or ""
        rels = data.get("releases") or {}
        f["num_versiones"] = len(rels)
    else:  # npm
        latest = (data.get("dist-tags") or {}).get("latest", "")
        ver = (data.get("versions") or {}).get(latest, {})
        f["version"] = latest
        f["resumen"] = (data.get("description") or "")[:200]
        lic = data.get("license")
        f["licencia"] = lic if isinstance(lic, str) else (lic or {}).get("type", "") if lic else ""
        f["repo"] = ((data.get("repository") or {}).get("url") or "") if isinstance(data.get("repository"), dict) else ""
        deps = ver.get("dependencies") or {}
        f["dependencias"] = list(deps.keys())[:15]
        f["num_dependencias"] = len(deps)
        f["num_versiones"] = len(data.get("versions") or {})

    # Salud del repo (GitHub)
    f["salud"] = _repo_github(f.get("repo") or f.get("home"))

    # CVE del propio paquete (OSV directo por ecosistema)
    f["cve"] = cve.revisar_paquete(eco, nombre, f["version"]) if f.get("version") else {"disponible": False}

    return f


def _licencia_de_clasif(clasificadores):
    for c in clasificadores:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return ""


def como_texto(f):
    if not f.get("ok"):
        return f.get("error", "sin datos")
    L = [f"Paquete: {f['nombre']} {f.get('version','')}  ({f['ecosistema']})"]
    if f.get("resumen"):   L.append(f"Qué es: {f['resumen']}")
    if f.get("licencia"):  L.append(f"Licencia: {f['licencia']}")
    if f.get("autor"):     L.append(f"Autor: {f['autor']}")
    if f.get("repo"):      L.append(f"Repo: {f['repo']}")
    if f.get("python_requiere"): L.append(f"Requiere Python: {f['python_requiere']}")

    L.append(f"\n[DEPENDENCIAS] {f.get('num_dependencias',0)} directa(s)"
             + (": " + ", ".join(f["dependencias"]) if f.get("dependencias") else ""))
    L.append(f"[VERSIONES] {f.get('num_versiones',0)} publicadas")

    s = f.get("salud")
    if s:
        archivado = " · ⚠ ARCHIVADO (sin mantenimiento)" if s.get("archivado") else ""
        L.append(f"\n[SALUD del repo] ⭐ {s.get('estrellas','?')} · {s.get('forks','?')} forks · "
                 f"{s.get('issues_abiertas','?')} issues abiertas · último push {s.get('ultimo_push','?')}"
                 f"{archivado}")
        if s.get("lenguaje"):     L.append(f"  Lenguaje principal: {s['lenguaje']}")
        if s.get("licencia_repo"): L.append(f"  Licencia (repo): {s['licencia_repo']}")

    if f.get("cve", {}).get("disponible") or f.get("cve", {}).get("resultados"):
        L.append("\n[CVE]")
        L.append(cve.como_texto(f["cve"]))
    return "\n".join(L)