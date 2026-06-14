"""
nucleo/habilidades/analisis/repos.py
Analiza un PROYECTO/REPO: carpeta local o repo de GitHub.
  · árbol y lenguajes (por extensión + LOC)
  · manifiestos y dependencias (requirements/package.json/pyproject/go.mod/Cargo)
  · entry points y tests
  · calidad de los .py (reusa el analizador de la habilidad python)
  · escaneo de SECRETOS (claves/API keys/tokens hardcodeados) — clave para auditar lo propio
"""
import os
import re
import json

try:
    import requests
    _REQ = True
except Exception:
    _REQ = False
import urllib.request

_UA = "SatellaAnalizador/1.0"
_IGNORAR = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
            "build", ".next", ".cache", "site-packages", ".idea", ".vscode"}
_EXT_LANG = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "React",
             ".tsx": "React/TS", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
             ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
             ".c": "C", ".cpp": "C++", ".cs": "C#", ".json": "JSON", ".md": "Markdown",
             ".sql": "SQL", ".sh": "Shell", ".yml": "YAML", ".yaml": "YAML"}
_MANIFIESTOS = {"requirements.txt": "pip", "pyproject.toml": "pyproject", "Pipfile": "pipenv",
                "package.json": "npm", "go.mod": "Go modules", "Cargo.toml": "Cargo",
                "pom.xml": "Maven", "build.gradle": "Gradle", "composer.json": "Composer"}
_ENTRYPOINTS = {"main.py", "app.py", "manage.py", "wsgi.py", "__main__.py",
                "index.js", "server.js", "app.js", "main.go", "main.rs"}

# Patrones de secretos (escaneo de auditoría)
_SECRETOS = [
    ("Clave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Groq key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Secreto hardcodeado", re.compile(r"""(?i)(api[_-]?key|secret|token|password|passwd|contrase)\s*[=:]\s*['"][^'"\s]{8,}['"]""")),
]


# ── LOCAL ─────────────────────────────────────────────────────────────────────
def analizar_local(ruta):
    if not os.path.isdir(ruta):
        return {"ok": False, "error": f"No existe la carpeta: {ruta}"}
    lenguajes, loc = {}, {}
    entrypoints, manifiestos, tests = [], {}, 0
    readme = False
    secretos = []
    total_archivos = 0

    for raiz, dirs, files in os.walk(ruta):
        dirs[:] = [d for d in dirs if d not in _IGNORAR and not d.startswith(".")]
        for nombre in files:
            total_archivos += 1
            ext = os.path.splitext(nombre)[1].lower()
            ruta_f = os.path.join(raiz, nombre)
            rel = os.path.relpath(ruta_f, ruta)

            if nombre.lower().startswith("readme"):
                readme = True
            if nombre in _ENTRYPOINTS:
                entrypoints.append(rel)
            if nombre in _MANIFIESTOS:
                manifiestos[nombre] = _MANIFIESTOS[nombre]
            if re.search(r"(^test_|_test\.|\.test\.|\.spec\.)", nombre) or "test" in raiz.lower().split(os.sep):
                tests += 1
            if ext in _EXT_LANG:
                lenguajes[_EXT_LANG[ext]] = lenguajes.get(_EXT_LANG[ext], 0) + 1
                # LOC + secretos (solo archivos de texto razonables)
                try:
                    if os.path.getsize(ruta_f) < 1_500_000:
                        with open(ruta_f, encoding="utf-8", errors="ignore") as fp:
                            contenido = fp.read()
                        loc[_EXT_LANG[ext]] = loc.get(_EXT_LANG[ext], 0) + contenido.count("\n")
                        for etiqueta, pat in _SECRETOS:
                            if pat.search(contenido):
                                secretos.append({"archivo": rel, "tipo": etiqueta})
                except Exception:
                    pass

    deps = _leer_manifiestos_local(ruta, manifiestos)
    calidad = _calidad_python_local(ruta)

    return {"ok": True, "fuente": "local", "ruta": ruta, "total_archivos": total_archivos,
            "lenguajes": lenguajes, "loc": loc, "entrypoints": entrypoints[:8],
            "manifiestos": manifiestos, "dependencias": deps, "tests": tests,
            "readme": readme, "secretos": secretos[:20], "calidad_py": calidad}


def _leer_manifiestos_local(ruta, manifiestos):
    deps = {}
    if "requirements.txt" in manifiestos:
        try:
            with open(os.path.join(ruta, "requirements.txt"), encoding="utf-8", errors="ignore") as fp:
                deps["pip"] = [l.strip() for l in fp if l.strip() and not l.startswith("#")][:25]
        except Exception:
            pass
    if "package.json" in manifiestos:
        try:
            with open(os.path.join(ruta, "package.json"), encoding="utf-8", errors="ignore") as fp:
                pkg = json.load(fp)
            deps["npm"] = list((pkg.get("dependencies") or {}).keys())[:25]
        except Exception:
            pass
    return deps


def _calidad_python_local(ruta, max_archivos=15):
    """Corre el analizador de la habilidad python sobre una muestra de .py."""
    try:
        from nucleo.habilidades.python import analizador
    except Exception:
        return None
    revisados, con_problemas, problemas = 0, 0, []
    for raiz, dirs, files in os.walk(ruta):
        dirs[:] = [d for d in dirs if d not in _IGNORAR and not d.startswith(".")]
        for nombre in files:
            if not nombre.endswith(".py") or revisados >= max_archivos:
                continue
            try:
                with open(os.path.join(raiz, nombre), encoding="utf-8", errors="ignore") as fp:
                    codigo = fp.read()
                res = analizador.analizar(codigo)
                revisados += 1
                probs = (res.get("pyflakes") or []) + (res.get("ruff") or [])
                if not res.get("sintaxis_ok", True) or probs:
                    con_problemas += 1
                    if probs:
                        problemas.append(f"{nombre}: {probs[0]}")
            except Exception:
                pass
    return {"revisados": revisados, "con_problemas": con_problemas, "ejemplos": problemas[:6]}


# ── GITHUB ────────────────────────────────────────────────────────────────────
def _api(url):
    try:
        if _REQ:
            r = requests.get(url, timeout=10, headers={"User-Agent": _UA})
            return r.json() if r.status_code < 400 else None
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def analizar_github(owner, repo):
    base = f"https://api.github.com/repos/{owner}/{repo}"
    meta = _api(base)
    if not meta:
        return {"ok": False, "error": f"No pude leer el repo {owner}/{repo} (¿privado, no existe, o rate-limit?)."}
    langs = _api(base + "/languages") or {}
    rama = meta.get("default_branch", "main")
    tree = _api(f"{base}/git/trees/{rama}?recursive=1") or {}
    archivos = [n["path"] for n in tree.get("tree", []) if n.get("type") == "blob"]
    manifiestos = sorted({os.path.basename(a) for a in archivos if os.path.basename(a) in _MANIFIESTOS})
    entrypoints = sorted({a for a in archivos if os.path.basename(a) in _ENTRYPOINTS})[:8]
    tests = sum(1 for a in archivos if re.search(r"(^|/)(test_|.*_test\.|.*\.test\.|.*\.spec\.)", a))

    return {"ok": True, "fuente": "github", "repo": f"{owner}/{repo}",
            "descripcion": meta.get("description") or "", "estrellas": meta.get("stargazers_count"),
            "forks": meta.get("forks_count"), "issues_abiertas": meta.get("open_issues_count"),
            "ultimo_push": (meta.get("pushed_at") or "")[:10], "archivado": meta.get("archived"),
            "licencia": (meta.get("license") or {}).get("spdx_id"),
            "lenguajes": langs, "total_archivos": len(archivos),
            "manifiestos": manifiestos, "entrypoints": entrypoints, "tests": tests,
            "rama": rama}


def como_texto(f):
    if not f.get("ok"):
        return f.get("error", "sin datos")
    L = []
    if f["fuente"] == "github":
        L.append(f"Repo: {f['repo']}  (GitHub)")
        if f.get("descripcion"): L.append(f"Descripción: {f['descripcion']}")
        arch = " · ⚠ ARCHIVADO" if f.get("archivado") else ""
        L.append(f"⭐ {f.get('estrellas','?')} · {f.get('forks','?')} forks · {f.get('issues_abiertas','?')} issues · "
                 f"último push {f.get('ultimo_push','?')} · licencia {f.get('licencia') or '?'}{arch}")
        if f.get("lenguajes"):
            total = sum(f["lenguajes"].values()) or 1
            top = sorted(f["lenguajes"].items(), key=lambda x: -x[1])[:5]
            L.append("Lenguajes: " + ", ".join(f"{k} {round(100*v/total)}%" for k, v in top))
        L.append(f"Archivos: {f.get('total_archivos','?')} · manifiestos: {', '.join(f['manifiestos']) or '—'} · "
                 f"tests: {f.get('tests',0)}")
        if f.get("entrypoints"): L.append("Entry points: " + ", ".join(f["entrypoints"]))
    else:
        L.append(f"Proyecto local: {f['ruta']}")
        L.append(f"Archivos: {f['total_archivos']}")
        if f.get("lenguajes"):
            top = sorted(f["lenguajes"].items(), key=lambda x: -x[1])[:6]
            L.append("Lenguajes: " + ", ".join(f"{k} ({n} arch, {f['loc'].get(k,0)} LOC)" for k, n in top))
        L.append(f"Manifiestos: {', '.join(f['manifiestos'].keys()) or '—'} · tests: {f['tests']} · "
                 f"README: {'sí' if f['readme'] else 'no'}")
        if f.get("entrypoints"): L.append("Entry points: " + ", ".join(f["entrypoints"]))
        for eco, ds in (f.get("dependencias") or {}).items():
            L.append(f"Dependencias ({eco}): {', '.join(ds[:15])}")
        cal = f.get("calidad_py")
        if cal and cal.get("revisados"):
            L.append(f"\n[CALIDAD PYTHON] {cal['revisados']} archivos revisados, {cal['con_problemas']} con observaciones")
            for e in cal.get("ejemplos", []): L.append(f"  · {e}")
        # Secretos: lo más importante de auditar
        if f.get("secretos"):
            L.append(f"\n[⚠ SECRETOS EXPUESTOS] {len(f['secretos'])} hallazgo(s) — revisalos YA:")
            for s in f["secretos"]:
                L.append(f"  ⚠ {s['tipo']} en {s['archivo']}")
        else:
            L.append("\n[SECRETOS] ✓ no se detectaron claves/tokens hardcodeados")
    return "\n".join(L)