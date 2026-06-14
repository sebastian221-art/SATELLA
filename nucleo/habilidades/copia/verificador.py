"""
nucleo/habilidades/copia/verificador.py
Verifica el código generado: chequeo de sintaxis (AST, siempre) y un smoke test
acotado (lo ejecuta en subprocess con timeout, en archivo temporal). Reporta si
corre y qué error tira, sin romper el flujo.
"""
import ast
import os
import sys
import tempfile
import subprocess


_LARGA_DURACION = ("serve_forever", "while True", "while 1", "app.run(", "mainloop(",
                   "run_forever", "uvicorn.run", "socketio.run", ".serve(", "loop.run")


def verificar(codigo, ejecutar=True, timeout=8):
    if not codigo or not codigo.strip():
        return {"sintaxis_ok": False, "ejecuta": False, "error": "No se generó código."}

    # 1) Sintaxis (determinista, seguro)
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        return {"sintaxis_ok": False, "ejecuta": False, "error": f"SyntaxError: {e}"}

    res = {"sintaxis_ok": True, "ejecuta": None, "error": None, "salida": "", "largo": False}
    if not ejecutar:
        return res

    # Código de servicio / larga duración: NO ejecutar como smoke test (correría para siempre)
    if any(p in codigo for p in _LARGA_DURACION):
        res["largo"] = True
        return res

    # 2) Smoke test acotado
    ruta = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(codigo)
            ruta = f.name
        p = subprocess.run([sys.executable, ruta], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        res["ejecuta"] = (p.returncode == 0)
        res["salida"] = (p.stdout or "")[:500]
        if p.returncode != 0:
            res["error"] = (p.stderr or "").strip().splitlines()[-1] if p.stderr else "Salió con código != 0"
    except subprocess.TimeoutExpired:
        res["ejecuta"] = False
        res["error"] = f"Timeout (> {timeout}s)"
    except Exception as e:
        res["ejecuta"] = False
        res["error"] = str(e)[:160]
    finally:
        if ruta and os.path.exists(ruta):
            try:
                os.unlink(ruta)
            except Exception:
                pass
    return res


def como_texto(v):
    if not v.get("sintaxis_ok"):
        return f"✗ Sintaxis inválida: {v.get('error')}"
    if v.get("largo"):
        return "✓ Sintaxis OK · código de servicio/larga duración (no se ejecuta como smoke test)"
    if v.get("ejecuta") is None:
        return "✓ Sintaxis OK (no se ejecutó)"
    if v.get("ejecuta"):
        return "✓ Sintaxis OK · ✓ ejecuta sin errores"
    return f"✓ Sintaxis OK · ⚠ falla al ejecutar: {v.get('error')}"