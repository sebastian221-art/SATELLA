"""
nucleo/habilidades/python/analizador.py
Análisis EXACTO de código Python. AST siempre; radon/pyflakes/ruff si están.
Degrada con elegancia: si falta una herramienta, la saltea sin romper.
Ningún LLM produce métricas exactas — esto las calcula.
"""
import ast
import os
import subprocess
import sys
import tempfile


def analizar(codigo: str) -> dict:
    res = {
        "sintaxis_ok": True,
        "errores": [],
        "metricas": {},
        "problemas": [],   # lista de strings legibles
        "resumen": "",
    }
    if not codigo or not codigo.strip():
        res["resumen"] = "No hay código para analizar."
        return res

    # 1) AST — sintaxis y conteos (siempre disponible)
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as e:
        res["sintaxis_ok"] = False
        res["errores"].append(f"Línea {e.lineno}: {e.msg}")
        res["resumen"] = f"Error de sintaxis en la línea {e.lineno}: {e.msg}"
        return res

    funcs = [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    clases = [n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)]
    res["metricas"]["funciones"] = len(funcs)
    res["metricas"]["clases"] = len(clases)
    res["metricas"]["lineas"] = len([l for l in codigo.splitlines() if l.strip()])

    # 2) radon — complejidad ciclomática y mantenibilidad (exactos)
    try:
        from radon.complexity import cc_visit
        from radon.metrics import mi_visit
        ccs = cc_visit(codigo)
        if ccs:
            peor = max(ccs, key=lambda c: c.complexity)
            res["metricas"]["complejidad_max"] = peor.complexity
            res["metricas"]["complejidad_en"] = peor.name
        res["metricas"]["mantenibilidad"] = round(mi_visit(codigo, True), 1)
    except Exception:
        pass

    # 2b) complejidad ALGORÍTMICA estimada (Big-O por estructura) — lo que beats a un LLM
    try:
        from . import analizador_complejidad
        comp = analizador_complejidad.estimar(codigo)
        res["metricas"]["big_o"] = comp["big_o"]
        if comp["detalle"]:
            res["metricas"]["big_o_detalle"] = comp["detalle"]
    except Exception:
        pass

    # 3) pyflakes — variables no definidas, imports sin usar
    res["problemas"] += _correr_pyflakes(codigo)
    # 4) ruff — linting ultrarrápido
    res["problemas"] += _correr_ruff(codigo)

    res["resumen"] = _armar_resumen(res)
    return res


def _con_tmp(codigo: str, fn):
    ruta = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(codigo)
            ruta = f.name
        return fn(ruta)
    except Exception:
        return []
    finally:
        if ruta:
            try:
                os.unlink(ruta)
            except Exception:
                pass


def _correr_pyflakes(codigo: str) -> list:
    def fn(ruta):
        p = subprocess.run([sys.executable, "-m", "pyflakes", ruta],
                           capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
        out = (p.stdout + p.stderr).strip()
        prob = []
        for linea in out.splitlines():
            parte = linea.split(":", 1)
            msg = parte[1].strip() if len(parte) > 1 else linea.strip()
            if msg:
                prob.append(f"[pyflakes] {msg}")
        return prob[:8]
    return _con_tmp(codigo, fn)


def _correr_ruff(codigo: str) -> list:
    def fn(ruta):
        p = subprocess.run(["ruff", "check", "--quiet", ruta],
                           capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
        out = (p.stdout + p.stderr).strip()
        prob = []
        for linea in out.splitlines():
            s = linea.strip()
            if s and not s.startswith("Found") and "-->" not in s and "|" not in s:
                prob.append(f"[ruff] {s}")
        return prob[:8]
    return _con_tmp(codigo, fn)


def _armar_resumen(res: dict) -> str:
    m = res["metricas"]
    partes = []
    if "big_o" in m and m["big_o"] != "?":
        partes.append(f"complejidad estructural (por bucles) {m['big_o']}")
    if "complejidad_max" in m:
        cc = m["complejidad_max"]
        nivel = "baja" if cc <= 5 else "moderada" if cc <= 10 else "alta"
        partes.append(f"complejidad ciclomática {nivel} (CC={cc})")
    if "mantenibilidad" in m:
        mi = m["mantenibilidad"]
        est = "buena" if mi >= 65 else "regular" if mi >= 40 else "baja"
        partes.append(f"mantenibilidad {est} (MI={mi})")
    n_prob = len(res["problemas"])
    if n_prob == 0:
        partes.append("sin problemas de linting")
    else:
        partes.append(f"{n_prob} cosa(s) para revisar")
    return "Sintaxis correcta. " + ", ".join(partes) + "." if partes else "Sintaxis correcta."