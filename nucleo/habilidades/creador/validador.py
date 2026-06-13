"""
nucleo/habilidades/creador/validador.py
Valida una habilidad generada SIN importarla en el proceso vivo de Satella:
  1) sintaxis (ast.parse)
  2) estructura mínima del contrato (NOMBRE, detecta, manejar)
  3) smoke test en SUBPROCESO aislado: importa el archivo y corre detecta()
     sobre un texto de prueba. Si algo explota, queda en el subproceso, no acá.
"""
import ast
import os
import subprocess
import sys
import tempfile

from config import SATELLA_ROOT

_SMOKE = '''
import importlib.util, sys
ruta = sys.argv[1]
spec = importlib.util.spec_from_file_location("skill_prueba", ruta)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert isinstance(getattr(m, "NOMBRE", None), str) and m.NOMBRE, "NOMBRE invalido"
assert callable(getattr(m, "detecta", None)), "falta detecta"
assert callable(getattr(m, "manejar", None)), "falta manejar"
r = m.detecta("una frase de prueba cualquiera")
assert isinstance(r, bool), "detecta() no devolvio bool"
print("OK")
'''


def validar(codigo: str) -> tuple:
    """Devuelve (ok: bool, problema: str)."""
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        return (False, f"Error de sintaxis (línea {e.lineno}): {e.msg}")

    faltan = [x for x in ("NOMBRE", "def detecta", "def manejar") if x not in codigo]
    if faltan:
        return (False, f"Faltan elementos del contrato: {faltan}")

    return _smoke(codigo)


def _smoke(codigo: str) -> tuple:
    archivo = runner = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(codigo)
            archivo = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as g:
            g.write(_SMOKE)
            runner = g.name

        env = dict(os.environ)
        env["PYTHONPATH"] = SATELLA_ROOT + os.pathsep + env.get("PYTHONPATH", "")

        proc = subprocess.run(
            [sys.executable, runner, archivo],
            cwd=SATELLA_ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0 and "OK" in proc.stdout:
            return (True, "")
        salida = (proc.stderr or proc.stdout or "falló el smoke test").strip().splitlines()
        return (False, salida[-1] if salida else "falló el smoke test")
    except subprocess.TimeoutExpired:
        return (False, "el smoke test se colgó (>20s) — ¿hay algo bloqueante al importar?")
    except Exception as e:
        return (False, str(e))
    finally:
        for p in (archivo, runner):
            try:
                if p:
                    os.unlink(p)
            except OSError:
                pass