"""
nucleo/habilidades/python/skill.py — Orquestador de la habilidad Python.

detecta(texto, codigo_adjunto) -> bool
manejar(texto, contexto)       -> dict {ok, skill, modo, resumen, cuerpo}
"""
from . import (detector, analizador, ejecutor, generador, verificador,
               explicador, aprendiz)

NOMBRE = "python"


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_tarea_codigo(texto, codigo_adjunto)


def manejar(texto: str, contexto: dict = None) -> dict:
    codigo = detector.extraer_codigo(texto)
    modo = detector.detectar_modo(texto, codigo)
    if modo == "generacion":
        res = _generar(texto)
    elif modo == "ejecutar":
        res = _ejecutar(codigo)
    elif modo == "debug":
        res = _debug(codigo)
    else:
        res = _analizar(codigo)
    if res.get("ok"):
        aprendiz.registrar(res.get("modo", modo), texto, res)
    return res


# ── Generación: pipeline (plan→código→tests→refinar) + explicación conversacional ─
def _generar(requerimiento: str) -> dict:
    gen = generador.generar(requerimiento)
    if not gen.get("ok"):
        return {"ok": False}

    codigo = gen["codigo"]
    a = analizador.analizar(codigo)
    explic = explicador.explicar_creacion(requerimiento, gen.get("plan", ""),
                                          codigo, gen.get("tests_pasaron"))

    cuerpo = (explic + "\n\n") if explic else ""
    cuerpo += f"```python\n{codigo}\n```"

    # Estado honesto de verificación.
    tp = gen.get("tests_pasaron")
    if tp is True:
        verif = f"Lo probé con tests (incluidos casos borde) y pasaron"
        if gen.get("ciclos"):
            verif += f" (lo corregí en {gen['ciclos']} ciclo/s)"
        verif += "."
    elif tp is False:
        verif = "Atención: algunos tests no pasaron — revisá los casos borde."
    else:
        verif = "Pasó sintaxis y linting (no llegué a probarlo con tests)."
    cuerpo += f"\n\n— {verif} {a.get('resumen','')}"

    resumen = ("Generé la solución y la probé con tests; pasaron." if tp is True
               else "Generé la solución (revisá los tests)." if tp is False
               else "Generé la solución, verificada por sintaxis y linting.")
    return {"ok": True, "skill": NOMBRE, "modo": "generacion", "resumen": resumen, "cuerpo": cuerpo}


# ── Análisis: razonamiento + métricas (incluye Big-O) ──────────────────────────
def _analizar(codigo: str) -> dict:
    if not codigo:
        return {"ok": False}
    a = analizador.analizar(codigo)
    razon = explicador.explicar(codigo, a)
    cuerpo = razon.strip() if razon else a["resumen"]
    if a["sintaxis_ok"] and razon:
        cuerpo += f"\n\nMétricas: {a['resumen']}"
    if a["problemas"]:
        cuerpo += "\n\nPuntos para revisar:\n- " + "\n- ".join(a["problemas"][:10])
    resumen = "Analicé el código: " + (a["errores"][0] if a["errores"] else a["resumen"])
    return {"ok": True, "skill": NOMBRE, "modo": "analisis", "resumen": resumen, "cuerpo": cuerpo}


# ── Debug: herramientas + razonamiento de lógica ───────────────────────────────
def _debug(codigo: str) -> dict:
    if not codigo:
        return {"ok": False}
    a = analizador.analizar(codigo)
    ejec = ejecutor.ejecutar(codigo) if a["sintaxis_ok"] else {
        "ok": False, "bloqueado": False, "stdout": "", "stderr": "no se ejecutó (sintaxis)"}
    diag = explicador.diagnosticar(codigo, a, ejec)

    cuerpo = (diag or "").strip()
    hechos = []
    if not a["sintaxis_ok"]:
        hechos.append("Sintaxis: " + "; ".join(a["errores"]))
    if a["problemas"]:
        hechos.append("Linting:\n- " + "\n- ".join(a["problemas"][:6]))
    if ejec.get("bloqueado"):
        hechos.append(f"No ejecutado: {ejec['stderr']}")
    elif not ejec["ok"]:
        hechos.append(f"Ejecución falló: {ejec['stderr'][:400]}")
    if hechos:
        cuerpo += ("\n\n" if cuerpo else "") + "Hechos de herramientas:\n" + "\n".join(hechos)
    if not cuerpo:
        cuerpo = "No encontré problemas de sintaxis, lint, ejecución ni lógica evidentes."

    resumen = "Diagnostiqué el código."
    return {"ok": True, "skill": NOMBRE, "modo": "debug", "resumen": resumen, "cuerpo": cuerpo}


# ── Ejecutar ───────────────────────────────────────────────────────────────────
def _ejecutar(codigo: str) -> dict:
    if not codigo:
        return {"ok": False}
    ejec = ejecutor.ejecutar(codigo)
    if ejec["bloqueado"]:
        cuerpo, resumen = f"No lo ejecuté: {ejec['stderr']}", "No ejecuté el código por seguridad."
    elif ejec["ok"]:
        cuerpo = f"Salida ({ejec['tiempo_ms']}ms):\n{ejec['stdout'] or '(sin output)'}"
        resumen = f"Lo corrí: terminó bien en {ejec['tiempo_ms']}ms."
    else:
        cuerpo, resumen = f"Falló:\n{ejec['stderr'][:1500]}", "Lo corrí y dio error."
    return {"ok": True, "skill": NOMBRE, "modo": "ejecutar", "resumen": resumen, "cuerpo": cuerpo}