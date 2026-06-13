"""
nucleo/habilidades/python/explicador.py
El paso de RAZONAMIENTO — lo que faltaba. Las herramientas (lint, ejecución)
dan hechos exactos pero no entienden la LÓGICA ni la INTENCIÓN. Acá el modelo
de código lee el código + los hechos de las herramientas y razona en palabras:
qué hace, qué está mal de lógica, por qué no hace lo que debería.
"""
from . import _llm


def explicar_creacion(requerimiento: str, plan: str, codigo: str, tests_pasaron) -> str:
    """Narra, como un colega, QUÉ construyó y POR QUÉ — atado al plan y a los tests.
    Esto es lo conversacional: 'te hice esto, lo pensé así, lo probé y anda'."""
    if not _llm.disponible():
        return ""
    estado_tests = ("probé los casos y pasaron" if tests_pasaron is True
                    else "los tests no pasaron del todo" if tests_pasaron is False
                    else "no llegué a probarlo con tests")
    prompt = (
        f'El usuario pidió: "{requerimiento[:200]}".\n\n'
        f"Tu plan fue:\n{plan[:600]}\n\n"
        f"Resultado de pruebas: {estado_tests}.\n\n"
        "Contale en 2-3 oraciones, como un colega (español, voseo), QUÉ construiste y "
        "POR QUÉ lo encaraste así (el enfoque, los casos borde que cubriste). "
        "Natural, sin tecnicismos de más, sin repetir el código. No empieces con 'Entiendo'."
    )
    return _llm.chat(prompt, max_tokens=350, temperature=0.5).strip()


def explicar(codigo: str, analisis: dict) -> str:
    """Explica QUÉ hace el código y su calidad, en palabras (español)."""
    if not _llm.disponible():
        return ""
    hechos = _hechos(analisis)
    prompt = (
        f"Código:\n```python\n{codigo[:2500]}\n```\n\n"
        f"Datos exactos de herramientas (no opinión):\n{hechos}\n\n"
        "Hacé una revisión de senior, en español (voseo), en 3-5 oraciones. Cubrí:\n"
        "1) Qué HACE el código.\n"
        "2) COSTO REAL: ¿la complejidad por bucles que reportó la herramienta es la verdadera, "
        "o hay un costo oculto? (ej: concatenar strings en un bucle es O(n²) aunque haya un solo for; "
        "un `x in lista` dentro de un bucle también; recursión sin memoización). Si la herramienta "
        "subestima, DECILO con la complejidad real.\n"
        "3) Bugs o casos borde no contemplados, si los hay.\n"
        "4) Una mejora concreta.\n"
        "Concreto, sin relleno, sin repetir las métricas tal cual. No uses 'Entiendo'."
    )
    return _llm.chat(prompt, max_tokens=550, temperature=0.3).strip()


def diagnosticar(codigo: str, analisis: dict, ejecucion: dict) -> str:
    """RAZONA por qué el código falla o no hace lo que debería — incluida la LÓGICA."""
    if not _llm.disponible():
        return ""
    hechos = _hechos(analisis)
    if ejecucion.get("bloqueado"):
        hechos += f"\nNo se ejecutó: {ejecucion.get('stderr','')}"
    elif ejecucion.get("ok"):
        out = ejecucion.get("stdout", "").strip() or "(sin output)"
        hechos += f"\nAl ejecutarlo: corre sin excepción. Salida: {out[:500]}"
    else:
        hechos += f"\nAl ejecutarlo FALLA: {ejecucion.get('stderr','')[:800]}"

    prompt = (
        f"Código:\n```python\n{codigo[:2500]}\n```\n\n"
        f"Hechos de herramientas:\n{hechos}\n\n"
        "Diagnosticá en 2-4 oraciones, en español (voseo), POR QUÉ este código está mal "
        "o no hace lo que debería. IMPORTANTE: además de errores de sintaxis o ejecución, "
        "buscá errores de LÓGICA (cálculos incorrectos, casos borde no contemplados como lista "
        "vacía o división por cero, condiciones al revés). Si el código corre pero el resultado "
        "es conceptualmente incorrecto, decílo claro. Terminá con la corrección concreta. No uses 'Entiendo'."
    )
    return _llm.chat(prompt, max_tokens=500, temperature=0.2).strip()


def _hechos(analisis: dict) -> str:
    partes = []
    if not analisis.get("sintaxis_ok", True):
        partes.append("Error de sintaxis: " + "; ".join(analisis.get("errores", [])))
    m = analisis.get("metricas", {})
    if m:
        partes.append(f"métricas: {m}")
    if analisis.get("problemas"):
        partes.append("linting:\n- " + "\n- ".join(analisis["problemas"][:8]))
    return "\n".join(partes) or "sin hallazgos de herramientas"