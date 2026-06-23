"""
nucleo/sandbox.py — Ejecución SEGURA de código generado (defensa en capas).

NO es un búnker a prueba de balas (eso necesita Docker/VM). Es defensa en capas
que cierra los agujeros grandes para correr código generado por Claude Code/Groq
sin arriesgar la máquina:

  1. COMPUERTA ESTÁTICA (AST): escanea operaciones peligrosas (borrar/escribir
     archivos, red, subprocesos, eval/exec). Si las hay y no se autoriza, NO corre.
  2. EJECUCIÓN AISLADA: carpeta temporal (no toca el proyecto) + entorno LIMPIO
     (sin API keys, aunque el código lea os.environ) + timeout (mata loops).
  3. HONESTIDAD: informa qué corrió, qué no, y por qué.

API:
  analizar_riesgo(codigo) -> {seguro, riesgos:[(tipo, detalle)], parse_ok}
  ejecutar_seguro(codigo, timeout=10, permitir_riesgo=False) -> {ok, ejecutado, ...}
"""
import ast
import os
import sys
import shutil
import tempfile
import subprocess

# Módulos cuyo import ya es señal de riesgo (red / proceso / binario).
_MOD_RED = {"socket", "requests", "urllib", "http", "ftplib", "smtplib",
            "telnetlib", "httpx", "aiohttp", "websocket", "websockets"}
_MOD_PROC = {"subprocess", "multiprocessing", "ctypes", "winreg", "win32api"}

# Llamadas por nombre peligrosas.
_LLAMADAS = {"eval", "exec", "compile", "__import__"}
_BLOQUEANTES = {"input"}  # colgarían el subproceso esperando stdin

# Métodos destructivos por módulo.
_OS_DESTRUCTIVO = {"system", "popen", "remove", "unlink", "rmdir", "removedirs",
                   "rename", "replace", "chmod", "chown", "kill", "abort",
                   "truncate", "fork", "execv", "execve", "spawnv", "startfile"}
_SHUTIL_DESTRUCTIVO = {"rmtree", "move", "copy", "copytree", "copyfile", "copy2", "chown"}


def _nombre_base(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _nombre_base(node.value)
    return ""


def _modo_open(node):
    """Devuelve el string de modo de un open(...) si es literal, o ''."""
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
            and isinstance(node.args[1].value, str):
        return node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return ""


class _Escaner(ast.NodeVisitor):
    def __init__(self):
        self.riesgos = []

    def _add(self, tipo, detalle):
        self.riesgos.append((tipo, detalle))

    def visit_Import(self, node):
        for a in node.names:
            top = a.name.split(".")[0]
            if top in _MOD_RED:
                self._add("red", f"import {a.name}")
            elif top in _MOD_PROC:
                self._add("proceso", f"import {a.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        top = (node.module or "").split(".")[0]
        if top in _MOD_RED:
            self._add("red", f"from {node.module} import …")
        elif top in _MOD_PROC:
            self._add("proceso", f"from {node.module} import …")
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in _LLAMADAS:
                self._add("codigo_dinamico", f"{f.id}()")
            elif f.id in _BLOQUEANTES:
                self._add("bloqueante", f"{f.id}()")
            elif f.id == "open":
                modo = _modo_open(node)
                if modo and any(c in modo for c in "wax+"):
                    self._add("escritura_archivo", f"open(..., {modo!r})")
        elif isinstance(f, ast.Attribute):
            base = _nombre_base(f.value)
            attr = f.attr
            if base == "os" and attr in _OS_DESTRUCTIVO:
                self._add("sistema_archivos", f"os.{attr}()")
            elif base == "shutil" and attr in _SHUTIL_DESTRUCTIVO:
                self._add("sistema_archivos", f"shutil.{attr}()")
            elif base in _MOD_PROC:
                self._add("proceso", f"{base}.{attr}()")
            elif base in _MOD_RED:
                self._add("red", f"{base}.{attr}()")
        self.generic_visit(node)


def analizar_riesgo(codigo: str) -> dict:
    """Escaneo estático determinista. No ejecuta nada."""
    try:
        arbol = ast.parse(codigo or "")
    except SyntaxError as e:
        return {"seguro": False, "parse_ok": False,
                "riesgos": [("sintaxis", f"línea {e.lineno}: {e.msg}")]}
    esc = _Escaner()
    esc.visit(arbol)
    # sin duplicados, preservando orden
    vistos, riesgos = set(), []
    for r in esc.riesgos:
        if r not in vistos:
            vistos.add(r)
            riesgos.append(r)
    return {"seguro": not riesgos, "parse_ok": True, "riesgos": riesgos}


# Variables de entorno que SÍ se pasan (mínimo para que Python arranque en Windows/Unix).
_ENV_PERMITIDAS = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP",
                   "TMPDIR", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS",
                   "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL")


def _env_limpio() -> dict:
    """Entorno mínimo SIN secretos: aunque el código lea os.environ, no hay keys."""
    env = {k: os.environ[k] for k in _ENV_PERMITIDAS if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["SATELLA_SANDBOX"] = "1"  # el código puede detectar que corre aislado
    return env


def ejecutar_seguro(codigo: str, timeout: int = 10, permitir_riesgo: bool = False) -> dict:
    """
    Corre `codigo` Python en aislamiento. Devuelve:
      {ok, ejecutado, stdout, stderr, codigo_salida, riesgos, razon}
    - Si no compila → no ejecuta.
    - Si tiene operaciones riesgosas y permitir_riesgo=False → no ejecuta, las informa.
    - Si compila y es seguro (o se autoriza) → corre en temp + entorno limpio + timeout.
    """
    riesgo = analizar_riesgo(codigo)
    if not riesgo["parse_ok"]:
        return {"ok": False, "ejecutado": False, "razon": "no compila",
                "riesgos": riesgo["riesgos"], "stdout": "", "stderr": ""}

    if riesgo["riesgos"] and not permitir_riesgo:
        detalle = ", ".join(f"{t}: {d}" for t, d in riesgo["riesgos"][:6])
        return {"ok": False, "ejecutado": False,
                "razon": f"no lo ejecuté solo por seguridad ({detalle})",
                "riesgos": riesgo["riesgos"], "stdout": "", "stderr": ""}

    tmp = tempfile.mkdtemp(prefix="satella_sandbox_")
    script = os.path.join(tmp, "_run.py")
    try:
        with open(script, "w", encoding="utf-8") as fp:
            fp.write(codigo)
        p = subprocess.run([sys.executable, script], cwd=tmp, capture_output=True,
                           text=True, timeout=timeout, env=_env_limpio(),
                           encoding="utf-8", errors="replace")
        return {"ok": p.returncode == 0, "ejecutado": True,
                "stdout": (p.stdout or "")[-4000:], "stderr": (p.stderr or "")[-2000:],
                "codigo_salida": p.returncode, "riesgos": riesgo["riesgos"], "razon": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "ejecutado": True,
                "razon": f"timeout {timeout}s (posible loop infinito)",
                "riesgos": riesgo["riesgos"], "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "ejecutado": False, "razon": str(e),
                "riesgos": riesgo["riesgos"], "stdout": "", "stderr": ""}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def como_texto(r: dict) -> str:
    """Resumen legible del resultado del sandbox."""
    if not r.get("ejecutado"):
        base = f"⚠ No ejecutado: {r.get('razon', 'motivo desconocido')}"
        return base
    if r.get("ok"):
        out = (r.get("stdout") or "").strip()
        return "✓ Corrió aislado sin errores." + (f"\nSalida:\n{out}" if out else "")
    err = (r.get("stderr") or r.get("razon") or "").strip()
    return f"✗ Corrió aislado pero falló:\n{err[:600]}"