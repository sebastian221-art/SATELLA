"""
nucleo/habilidades/python/generador.py — PIPELINE DE CREACIÓN (la "lógica de Claude")
No genera de un saque. Sigue el proceso de un ingeniero senior:
  1. PLAN     — entiende la spec: enfoque, casos borde, complejidad esperada.
  2. CÓDIGO   — escribe la solución guiada por el plan.
  3. TESTS    — escribe asserts (incluidos casos borde) y LOS CORRE.
  4. REFINA   — si un test falla, corrige y reintenta (hasta 2 ciclos).
Exprime mucho más del mismo modelo que un one-shot. Todo degrada con elegancia.
"""
import ast
import re

from . import _llm, ejecutor


def _extraer(texto: str) -> str:
    m = re.search(r"```(?:python|py)?\s*(.*?)```", texto, re.DOTALL)
    return (m.group(1).strip() if m else texto.strip())


def _valido(codigo: str) -> bool:
    try:
        ast.parse(codigo)
        return True
    except SyntaxError:
        return False


def _sin_main(codigo: str) -> str:
    idx = codigo.find("if __name__")
    return codigo[:idx].strip() if idx != -1 else codigo


def generar(requerimiento: str) -> dict:
    if not _llm.disponible():
        return {"ok": False}

    plan = _plan(requerimiento)
    codigo = _codigo(requerimiento, plan)
    if not _valido(codigo):
        codigo = _codigo(requerimiento, plan)        # un reintento
    if not codigo or not _valido(codigo):
        return {"ok": False}

    asserts = _tests(requerimiento, codigo)
    tests_pasaron, salida = (_correr_tests(codigo, asserts) if asserts else (None, ""))

    ciclos = 0
    while tests_pasaron is False and ciclos < 3:
        nuevo = _refinar(requerimiento, codigo, salida)
        if not nuevo or not _valido(nuevo) or nuevo == codigo:
            break
        codigo = nuevo
        tests_pasaron, salida = _correr_tests(codigo, asserts)
        ciclos += 1

    return {"ok": True, "codigo": codigo, "plan": plan, "tests": asserts,
            "tests_pasaron": tests_pasaron, "salida_tests": salida, "ciclos": ciclos}


# ── Pasos del pipeline ─────────────────────────────────────────────────────────
def _plan(requerimiento: str) -> str:
    prompt = (
        f'Tarea: "{requerimiento}"\n\n'
        "Antes de escribir código, hacé un plan BREVE (no escribas código todavía):\n"
        "- Entradas y salidas.\n- Casos borde a contemplar (vacío, negativos, tipos inválidos, etc.).\n"
        "- Enfoque/algoritmo y complejidad esperada.\n"
        "Respondé en 4-6 líneas, en español. Nada de código."
    )
    return _llm.chat(prompt, max_tokens=400, temperature=0.3)


def _codigo(requerimiento: str, plan: str) -> str:
    prompt = (
        f'Tarea: "{requerimiento}"\n\nPlan acordado:\n{plan}\n\n'
        "Escribí la solución en Python siguiendo el plan.\n"
        "- Comentarios y docstring en ESPAÑOL.\n"
        "- Manejá los casos borde del plan.\n"
        "- Código completo y correcto: elegí la estructura de datos adecuada y "
        "EVITÁ antipatrones (concatenar strings en un bucle → usá ''.join; "
        "defaults mutables; recursión sin caso base; búsquedas O(n) dentro de bucles).\n"
        '- Incluí un bloque if __name__ == "__main__": con un ejemplo real.\n'
        "Escribí TODO el código, sin recortar ni omitir partes. "
        "Respondé SOLO el código en un bloque ```python ... ```."
    )
    return _extraer(_llm.chat(prompt, max_tokens=3500, temperature=0.2))


def _tests(requerimiento: str, codigo: str) -> str:
    prompt = (
        f'Para esta tarea: "{requerimiento}"\n\nEste es el código:\n```python\n{codigo}\n```\n\n'
        "Escribí entre 3 y 6 asserts que comprueben que la función hace lo correcto, "
        "INCLUYENDO casos borde (vacío, negativos, tipos límite). Usá el MISMO nombre de función.\n"
        "Solo las líneas `assert ...` (o try/except para los que deban lanzar error). "
        "Respondé SOLO el bloque ```python ... ``` con los asserts, sin redefinir la función."
    )
    t = _extraer(_llm.chat(prompt, max_tokens=900, temperature=0.2))
    # Seguridad: solo conservar líneas de test, no una redefinición de la función.
    lineas = [ln for ln in t.splitlines() if not ln.strip().startswith("def ")]
    return "\n".join(lineas).strip()


def _correr_tests(codigo: str, asserts: str):
    script = _sin_main(codigo) + "\n\n# --- tests ---\n" + asserts + '\nprint("TESTS_OK")\n'
    r = ejecutor.ejecutar(script, timeout=8)
    if r["ok"] and "TESTS_OK" in r.get("stdout", ""):
        return True, ""
    return False, (r.get("stderr") or r.get("stdout") or "fallo desconocido")[:600]


def _refinar(requerimiento: str, codigo: str, salida: str) -> str:
    prompt = (
        f'Tarea: "{requerimiento}"\n\nEste código falló sus tests:\n```python\n{codigo}\n```\n\n'
        f"Salida del fallo:\n{salida}\n\n"
        "Corregí el código para que pase. Respondé SOLO el código corregido COMPLETO en ```python ... ```."
    )
    return _extraer(_llm.chat(prompt, max_tokens=3500, temperature=0.2))