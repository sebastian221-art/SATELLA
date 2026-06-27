"""
nucleo/habilidades/python/generador.py — GENERACIÓN con Claude Code.
El cerebro generador ahora es Claude Code (calidad frontera, con tu CLAUDE.md
aplicado). No envolvemos un pipeline propio: Claude ya planifica/prueba/refina
por dentro. Lo que SÍ hace Satella (y ningún LLM solo): correr el código en tu
máquina para verificarlo, y analizarlo (Big-O/métricas). Multi-lenguaje.

Flujo:
  1. ¿Ya lo resolví casi igual antes? → recupero del cuaderno (rápido, sin gastar).
  2. Si no: se lo pido a Claude Code.
  3. Si es Python: lo EJECUTO acá para verificar que corre.
  4. Guardo la solución completa en el cuaderno.
Degrada con elegancia: si Claude Code no está, devuelve ok=False y la skill avisa.
"""
import ast
import time

from nucleo import prediccion
from . import _claude_code, aprendiz, ejecutor

# Techo de tiempo (segundos) para TODA la generación. La entrega nunca se cuelga:
# la verificación semántica y la autocorrección son extras best-effort dentro de esto.
_PRESUPUESTO = 150


def _prompt_correccion(requerimiento, codigo, fallidos):
    casos = "\n".join(f"- {c['llamada']}: esperado {c['esperado']}, pero da {c['real']}"
                      for c in fallidos[:8])
    return (
        f"Este código (que debía: {requerimiento}) corre sin crashear pero da resultados "
        f"INCORRECTOS en estos casos:\n{casos}\n\n"
        f"Código actual:\n```python\n{codigo}\n```\n\n"
        "Corregí el bug para que esos casos den el resultado esperado, sin romper el resto. "
        "Devolvé el código completo corregido."
    )


def _valido_python(codigo: str) -> bool:
    try:
        ast.parse(codigo)
        return True
    except SyntaxError:
        return False


def _verificar_python(codigo: str):
    """Corre el código Python en tu máquina. Devuelve (verdicto, salida).
    True = corrió bien | False = error | None = no se pudo evaluar."""
    if not _valido_python(codigo):
        return False, "El código no es Python válido (error de sintaxis)."
    r = ejecutor.ejecutar(codigo, timeout=8)
    if r.get("bloqueado"):
        return None, "No lo ejecuté (la guardia de seguridad lo frenó)."
    if r.get("ok"):
        return True, r.get("stdout", "")
    return False, (r.get("stderr") or "error desconocido")[:600]


def generar(requerimiento: str, lenguaje: str = "python", contexto: str = "") -> dict:
    t0 = time.time()  # presupuesto de tiempo: la entrega NUNCA se cuelga esperando

    # 1) ¿Está en el cuaderno (pedido casi idéntico, ya resuelto)?
    cache = aprendiz.buscar_similar(requerimiento, lenguaje)
    if cache:
        return {"ok": True, "codigo": cache["codigo"], "lenguaje": lenguaje,
                "plan": "", "tests": "", "tests_pasaron": cache.get("verdicto"),
                "salida_tests": "", "ciclos": 0, "desde_cache": True}

    # 2) Se lo pido a Claude Code (con el contexto de la charla, si lo hay).
    if not _claude_code.disponible():
        return {"ok": False}
    gen = _claude_code.generar_codigo(requerimiento, lenguaje, contexto)
    if not gen.get("ok"):
        out = {"ok": False, "razon": gen.get("razon", "")}
        # Si Claude Code pidió una aclaración (no es código), la pasamos hacia arriba.
        if gen.get("aclaracion"):
            out["aclaracion"] = gen["aclaracion"]
            out["costo"] = gen.get("costo")
        return out

    codigo = gen["codigo"]

    # 3) Verificación independiente: si es Python, lo corro acá.
    verdicto, salida = (None, "")
    if lenguaje == "python":
        verdicto, salida = _verificar_python(codigo)

    # 3b) Verificación SEMÁNTICA (predigo casos y comparo) — BEST-EFFORT con techo
    #     de tiempo. Si ya gastamos buena parte del presupuesto generando+corriendo,
    #     entrego el código sin colgarme; la semántica es un extra, no un bloqueo.
    semantica = None
    nota_tiempo = ""
    hay_tiempo_predecir = (time.time() - t0) < _PRESUPUESTO * 0.55
    if lenguaje == "python" and verdicto is True and hay_tiempo_predecir:
        semantica = prediccion.verificar(codigo, requerimiento)
        # Corregir SOLO si detectó un bug y todavía queda presupuesto.
        if (semantica.get("hizo") and semantica.get("ok") and not semantica.get("todos")
                and (time.time() - t0) < _PRESUPUESTO * 0.8):
            fallidos = [c for c in semantica["casos"] if not c["coincide"]]
            correg = _claude_code.generar_codigo(
                _prompt_correccion(requerimiento, codigo, fallidos), lenguaje)
            if correg.get("ok") and correg.get("codigo", "").strip() and correg["codigo"] != codigo:
                v2, s2 = _verificar_python(correg["codigo"])
                if v2 is True and (time.time() - t0) < _PRESUPUESTO:
                    sem2 = prediccion.verificar(correg["codigo"], requerimiento)
                    if sem2.get("hizo") and sem2.get("coinciden", 0) > semantica.get("coinciden", 0):
                        codigo, verdicto, salida, semantica = correg["codigo"], v2, s2, sem2
    elif lenguaje == "python" and verdicto is True and not hay_tiempo_predecir:
        nota_tiempo = "no alcancé a verificar la semántica por tiempo (el código corre igual)"

    # 4) Guardo la solución completa en el cuaderno.
    aprendiz.registrar("generacion", requerimiento,
                       {"resumen": "solución generada"},
                       codigo=codigo, lenguaje=lenguaje, verdicto=verdicto)

    semantica_txt = prediccion.como_texto(semantica) if semantica else ""
    if nota_tiempo:
        semantica_txt = f"({nota_tiempo})"

    return {"ok": True, "codigo": codigo, "lenguaje": lenguaje, "plan": "",
            "tests": "", "tests_pasaron": verdicto, "salida_tests": salida,
            "ciclos": 0, "desde_cache": False,
            "semantica_txt": semantica_txt,
            "semantica_ok": bool(semantica and semantica.get("todos")),
            "costo": gen.get("costo"), "turnos": gen.get("turnos")}