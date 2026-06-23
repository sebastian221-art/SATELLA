"""
nucleo/prediccion.py — PREDECIR-Y-COMPARAR (verificación semántica).

Más allá de "¿corre sin error?": ¿hace lo CORRECTO? El flujo:
  1. PREDECIR: Claude Code (o Groq) propone casos de prueba con su resultado
     esperado — la INTENCIÓN ("para fibonacci(10) debería dar 55").
  2. COMPARAR: corre el código EN EL SANDBOX con esos casos y mide el resultado
     REAL.
  3. VEREDICTO: si predicción == realidad → verificado de verdad. Si no →
     hay un bug semántico, y se informa exactamente cuál caso falló.

Se apoya en nucleo/sandbox.py: los casos corren aislados, sin secretos, con
timeout. Si el código hace algo riesgoso, el sandbox no lo corre y se reporta.
"""
import json
import logging

from nucleo import sandbox

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None

try:
    from nucleo.habilidades.python import _llm
except Exception:  # pragma: no cover
    _llm = None

log = logging.getLogger("satella.prediccion")


# ── 1) Predecir casos ────────────────────────────────────────────────────────
def _prompt_predecir(codigo, descripcion, n):
    return (
        "Te doy un código Python. Generá de 3 a "
        f"{n} casos de prueba con su resultado ESPERADO, pensando qué DEBERÍA "
        "hacer el código (su intención), no qué hace.\n\n"
        f"Qué hace (según quien lo pidió): {descripcion}\n\n"
        f"Código:\n```python\n{codigo[:4000]}\n```\n\n"
        "Respondé SOLO un array JSON, sin texto afuera, con esta forma exacta:\n"
        '[{"llamada": "<expresión Python que llama al código, ej fibonacci(10)>", '
        '"esperado": <valor JSON: número, string, lista, bool o null>, '
        '"nota": "<qué caso cubre, breve>"}]\n'
        "La 'llamada' debe ser una expresión evaluable que use las funciones/clases del "
        "código. El 'esperado' debe ser serializable en JSON. Incluí casos borde."
    )


def _parsear_casos(texto):
    if not texto:
        return []
    s = texto.strip()
    i, j = s.find("["), s.rfind("]")
    if i == -1 or j == -1 or j < i:
        return []
    try:
        datos = json.loads(s[i:j + 1])
    except Exception:
        return []
    casos = []
    for d in datos:
        if isinstance(d, dict) and "llamada" in d and "esperado" in d:
            casos.append({"llamada": str(d["llamada"]),
                          "esperado": d["esperado"],
                          "nota": str(d.get("nota", ""))})
    return casos


def predecir(codigo, descripcion="", n=5):
    """Devuelve una lista de casos [{llamada, esperado, nota}] o []."""
    prompt = _prompt_predecir(codigo, descripcion, n)
    if claude_cli is not None and claude_cli.disponible():
        r = claude_cli.preguntar(prompt, allowed_tools="Read", max_turns=3, timeout=60,
                                 etiqueta="Prediciendo resultados",
                                 fases=["pensando los casos", "calculando lo esperado"])
        if r.get("ok"):
            casos = _parsear_casos(r.get("texto", ""))
            if casos:
                return casos
    if _llm is not None and _llm.disponible():
        return _parsear_casos(_llm.chat(prompt, max_tokens=900, temperature=0.2))
    return []


# ── 2) Comparar (correr en el sandbox y medir) ───────────────────────────────
_MARCA = "__PYCOMP__"


def _harness(codigo, casos):
    """Arma un script que corre cada llamada y emite su resultado real (repr)."""
    L = [codigo, "", "import json as __json", "__r = []"]
    for c in casos:
        ll = c["llamada"]
        L.append("try:")
        L.append(f"    __r.append([{ll!r}, repr({ll})])")
        L.append("except Exception as __e:")
        L.append(f"    __r.append([{ll!r}, '__ERROR__:' + type(__e).__name__ + ': ' + str(__e)])")
    L.append(f"print({_MARCA!r} + __json.dumps(__r))")
    return "\n".join(L)


def comparar(codigo, casos, timeout=10):
    """Corre los casos en el sandbox y compara real vs esperado."""
    if not casos:
        return {"ok": False, "razon": "no hubo casos para probar", "casos": []}

    harness = _harness(codigo, casos)
    r = sandbox.ejecutar_seguro(harness, timeout=timeout)
    if not r.get("ejecutado"):
        return {"ok": False, "razon": r.get("razon", "no se pudo ejecutar"),
                "casos": [], "no_seguro": True}

    salida = r.get("stdout", "")
    linea = next((l for l in salida.splitlines() if l.startswith(_MARCA)), None)
    if not linea:
        return {"ok": False, "razon": "el código no produjo resultados medibles "
                + ("(stderr: " + r.get("stderr", "")[:200] + ")" if r.get("stderr") else ""),
                "casos": []}

    try:
        reales = json.loads(linea[len(_MARCA):])
    except Exception:
        return {"ok": False, "razon": "no pude leer los resultados", "casos": []}

    reales_map = {ll: real for ll, real in reales}
    detalle = []
    coinciden = 0
    for c in casos:
        ll = c["llamada"]
        real = reales_map.get(ll, "(sin resultado)")
        esperado_repr = repr(c["esperado"])
        es_error = isinstance(real, str) and real.startswith("__ERROR__:")
        coincide = (not es_error) and (real == esperado_repr)
        if coincide:
            coinciden += 1
        detalle.append({"llamada": ll, "esperado": esperado_repr,
                        "real": real.replace("__ERROR__:", "⚠ ") if es_error else real,
                        "coincide": coincide, "nota": c.get("nota", "")})

    return {"ok": True, "total": len(casos), "coinciden": coinciden,
            "todos": coinciden == len(casos), "casos": detalle}


# ── 3) Orquestación ──────────────────────────────────────────────────────────
def verificar(codigo, descripcion="", timeout=10):
    """Predice casos y los compara. Devuelve el reporte completo."""
    casos = predecir(codigo, descripcion)
    if not casos:
        return {"hizo": False, "razon": "no se pudieron predecir casos de prueba"}
    comp = comparar(codigo, casos, timeout=timeout)
    comp["hizo"] = comp.get("ok", False)
    return comp


def como_texto(v):
    if not v.get("hizo"):
        return f"(verificación semántica no realizada: {v.get('razon', 'sin casos')})"
    if not v.get("ok"):
        return f"(no se pudo comparar: {v.get('razon', '')})"
    lineas = []
    for c in v["casos"]:
        tilde = "✓" if c["coincide"] else "✗"
        base = f"  {tilde} {c['llamada']} → esperado {c['esperado']}, real {c['real']}"
        lineas.append(base)
    cab = (f"Predicción vs realidad: {v['coinciden']}/{v['total']} casos coinciden"
           + (" ✓ verificado" if v["todos"] else " ⚠ hay diferencias"))
    return cab + "\n" + "\n".join(lineas)