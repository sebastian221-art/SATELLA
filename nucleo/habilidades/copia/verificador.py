"""
nucleo/habilidades/copia/verificador.py
Verifica el código generado: chequeo de sintaxis (AST, siempre) y un smoke test
ejecutado EN EL SANDBOX (aislado, entorno sin secretos, timeout). Si el código
hace cosas riesgosas (red, escribir/borrar archivos, subprocesos), el sandbox NO
lo corre solo y lo reporta — más seguro que ejecutarlo a ciegas.
"""
import ast

from nucleo import sandbox

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

    res = {"sintaxis_ok": True, "ejecuta": None, "error": None, "salida": "",
           "largo": False, "no_seguro": False, "riesgos": []}
    if not ejecutar:
        return res

    # Código de servicio / larga duración: NO ejecutar (correría para siempre)
    if any(p in codigo for p in _LARGA_DURACION):
        res["largo"] = True
        return res

    # 2) Smoke test EN EL SANDBOX
    r = sandbox.ejecutar_seguro(codigo, timeout=timeout)
    res["riesgos"] = r.get("riesgos", [])
    if not r.get("ejecutado"):
        # No se corrió: o no compila (ya filtrado) o tiene operaciones riesgosas.
        res["ejecuta"] = None
        res["no_seguro"] = True
        res["error"] = r.get("razon", "no ejecutado")
        return res

    res["ejecuta"] = bool(r.get("ok"))
    res["salida"] = (r.get("stdout") or "")[:500]
    if not r.get("ok"):
        err = (r.get("stderr") or r.get("razon") or "").strip()
        res["error"] = err.splitlines()[-1] if err.splitlines() else "Salió con código != 0"
    return res


def como_texto(v):
    if not v.get("sintaxis_ok"):
        return f"✗ Sintaxis inválida: {v.get('error')}"
    if v.get("largo"):
        return "✓ Sintaxis OK · código de servicio/larga duración (no se ejecuta como smoke test)"
    if v.get("no_seguro"):
        riesgos = ", ".join(f"{t}: {d}" for t, d in (v.get("riesgos") or [])[:5])
        return ("✓ Sintaxis OK · ⚠ no lo corrí en el sandbox por seguridad "
                f"({riesgos or v.get('error')}). Revisalo antes de usarlo.")
    if v.get("ejecuta") is None:
        return "✓ Sintaxis OK (no se ejecutó)"
    if v.get("ejecuta"):
        return "✓ Sintaxis OK · ✓ corrió aislado en el sandbox sin errores"
    return f"✓ Sintaxis OK · ⚠ falla al ejecutar en el sandbox: {v.get('error')}"