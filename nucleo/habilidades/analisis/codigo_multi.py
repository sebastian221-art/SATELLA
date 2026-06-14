"""
nucleo/habilidades/analisis/codigo_multi.py
Analiza un ARCHIVO de código de cualquier lenguaje: métricas (LOC, funciones,
clases, imports) por heurística, y para Python reusa el analizador real (AST+lint)
de la habilidad python. El "qué hace" lo razona el LLM encima.
"""
import os
import re

_LANG = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "React",
         ".tsx": "React/TS", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
         ".java": "Java", ".c": "C", ".cpp": "C++", ".cs": "C#", ".sh": "Shell", ".sql": "SQL"}

# patrones aproximados de funciones/clases por familia
_FUNC = re.compile(r"(?m)^\s*(?:def |function |func |fn |sub |public |private |static |async ).*?[\w$]+\s*\(")
_CLASS = re.compile(r"(?m)^\s*(?:class |struct |interface |enum |type )\s+[\w$]+")
_IMPORT = re.compile(r"(?m)^\s*(?:import |from |require\(|use |#include|using )")


def analizar_archivo(ruta):
    if not os.path.isfile(ruta):
        return {"ok": False, "error": f"No existe el archivo: {ruta}"}
    ext = os.path.splitext(ruta)[1].lower()
    lang = _LANG.get(ext, "desconocido")
    try:
        with open(ruta, encoding="utf-8", errors="ignore") as fp:
            codigo = fp.read()
    except Exception as e:
        return {"ok": False, "error": f"No pude leer el archivo: {e}"}

    lineas = codigo.splitlines()
    f = {"ok": True, "archivo": os.path.basename(ruta), "lenguaje": lang,
         "loc": len(lineas), "vacias": sum(1 for l in lineas if not l.strip()),
         "funciones": len(_FUNC.findall(codigo)), "clases": len(_CLASS.findall(codigo)),
         "imports": len(_IMPORT.findall(codigo))}

    if lang == "Python":
        try:
            from nucleo.habilidades.python import analizador
            res = analizador.analizar(codigo)
            f["python"] = {"sintaxis_ok": res.get("sintaxis_ok", True),
                           "problemas": ((res.get("pyflakes") or []) + (res.get("ruff") or []))[:8]}
        except Exception:
            pass
    return f


def como_texto(f):
    if not f.get("ok"):
        return f.get("error", "sin datos")
    L = [f"Archivo: {f['archivo']}  ({f['lenguaje']})",
         f"Métricas: {f['loc']} líneas ({f['vacias']} vacías), {f['funciones']} funciones, "
         f"{f['clases']} clases, {f['imports']} imports"]
    py = f.get("python")
    if py:
        L.append(f"\n[CALIDAD PYTHON] sintaxis {'OK' if py['sintaxis_ok'] else 'CON ERRORES'}"
                 + (f", {len(py['problemas'])} observación(es)" if py["problemas"] else ", sin observaciones"))
        for p in py["problemas"]:
            L.append(f"  · {p}")
    return "\n".join(L)