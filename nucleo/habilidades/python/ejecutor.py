"""
nucleo/habilidades/python/ejecutor.py
Ejecuta código Python en un subproceso aislado, con guardia de seguridad y timeout.
Lo que ningún LLM puede hacer: ver el output REAL.
Corre en la máquina de Sebas → la guardia es para evitar accidentes, no ataques.
"""
import ast
import os
import subprocess
import sys
import tempfile
import time

_LLAMADAS_BLOQUEADAS = {"eval", "exec", "compile", "__import__"}
_ATRIBUTOS_PELIGROSOS = {
    ("os", "system"), ("os", "remove"), ("os", "rmdir"), ("os", "unlink"),
    ("shutil", "rmtree"), ("shutil", "move"),
    ("subprocess", "call"), ("subprocess", "run"), ("subprocess", "Popen"),
}

_TIMEOUT = 8
_MAX_OUT = 8000


def _es_seguro(codigo: str):
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Sintaxis: {e.msg} (línea {e.lineno})"
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if isinstance(f, ast.Name) and f.id in _LLAMADAS_BLOQUEADAS:
                return False, f"Operación bloqueada por seguridad: {f.id}()"
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if (f.value.id, f.attr) in _ATRIBUTOS_PELIGROSOS:
                    return False, f"Operación bloqueada por seguridad: {f.value.id}.{f.attr}()"
    return True, ""


def ejecutar(codigo: str, timeout: int = _TIMEOUT) -> dict:
    if not codigo or not codigo.strip():
        return {"ok": False, "stdout": "", "stderr": "No hay código.", "tiempo_ms": 0, "bloqueado": False}

    seguro, razon = _es_seguro(codigo)
    if not seguro:
        return {"ok": False, "stdout": "", "stderr": razon, "tiempo_ms": 0, "bloqueado": True}

    ruta = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(codigo)
            ruta = f.name
        t0 = time.time()
        p = subprocess.run([sys.executable, ruta], capture_output=True, text=True, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        return {
            "ok": p.returncode == 0,
            "stdout": p.stdout[:_MAX_OUT],
            "stderr": p.stderr[:4000],
            "tiempo_ms": ms,
            "bloqueado": False,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Se pasó del límite de {timeout}s (¿bucle infinito?).",
                "tiempo_ms": timeout * 1000, "bloqueado": False}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "tiempo_ms": 0, "bloqueado": False}
    finally:
        if ruta:
            try:
                os.unlink(ruta)
            except Exception:
                pass