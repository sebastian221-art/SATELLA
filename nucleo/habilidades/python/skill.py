"""
nucleo/habilidades/python/skill.py — Orquestador de la habilidad de código.

GENERACIÓN → Claude Code (calidad frontera, aplica tu CLAUDE.md), multi-lenguaje.
EJECUTAR / DEBUG / ANALIZAR → herramientas locales de Satella (ejecutor con
guardia, analizador con Big-O). Eso es lo que ningún LLM hace solo: correr el
código de verdad y medirlo exacto.

Rol: snippets sueltos y código pegado, acá en el chat, con ejecución en vivo.
Para trabajo sobre PROYECTOS está agente_cc (Claude Code editando archivos).

detecta(texto, codigo_adjunto) -> bool
manejar(texto, contexto)       -> dict {ok, skill, modo, resumen, cuerpo}
"""
from . import (detector, analizador, ejecutor, generador, explicador, aprendiz)

NOMBRE = "python"


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_tarea_codigo(texto, codigo_adjunto)


def manejar(texto: str, contexto: dict = None) -> dict:
    codigo = detector.extraer_codigo(texto)
    modo = detector.detectar_modo(texto, codigo)
    if modo == "generacion":
        return _generar(texto, contexto)
    if modo == "ejecutar":
        return _ejecutar(codigo)
    if modo == "debug":
        return _debug(codigo)
    return _analizar(codigo)


def _contexto_conversacion(contexto: dict) -> str:
    """Arma un resumen corto de la charla reciente para que Claude Code resuelva
    referencias como 'eso' / 'lo que dijimos'. Sin esto, un pedido que depende del
    contexto le llega suelto y Claude Code pregunta '¿de qué me hablás?'."""
    if not contexto:
        return ""
    hist = contexto.get("historial") or []
    if not hist:
        return ""
    lineas = []
    for m in hist[-4:]:
        rol = "Sebas" if m.get("role") == "user" else "Satella"
        cont = str(m.get("content", "")).strip()[:300]
        if cont:
            lineas.append(f"{rol}: {cont}")
    return "\n".join(lineas)


# ── Generación: Claude Code + verificación local + análisis ────────────────────
def _generar(requerimiento: str, contexto: dict = None) -> dict:
    lenguaje = detector.detectar_lenguaje(requerimiento)
    ctx_txt = _contexto_conversacion(contexto)
    gen = generador.generar(requerimiento, lenguaje, ctx_txt)
    if not gen.get("ok"):
        # Claude Code pidió una aclaración (el pedido era ambiguo aun con contexto):
        # la relevamos tal cual, NO la ejecutamos como si fuera código.
        if gen.get("aclaracion"):
            return {
                "ok": True, "skill": NOMBRE, "modo": "generacion",
                "resumen": "Necesito un dato más para escribir el código",
                "cuerpo": gen["aclaracion"].strip(),
                "costo": gen.get("costo"),
            }
        return {
            "ok": True, "skill": NOMBRE, "modo": "generacion",
            "resumen": "No pude generar el código",
            "cuerpo": ("No tengo el cerebro generador disponible (Claude Code). "
                       "Revisá que `claude` esté instalado y logueado."),
        }

    codigo = gen["codigo"]
    es_python = (lenguaje == "python")
    desde_cache = gen.get("desde_cache")

    # Análisis exacto (Big-O/métricas) solo aplica a Python (es AST de Python).
    a = analizador.analizar(codigo) if es_python else {"resumen": "", "sintaxis_ok": True, "problemas": []}

    # Explicación conversacional (Groq, rápida) — qué hizo y por qué.
    explic = explicador.explicar_creacion(requerimiento, "", codigo, gen.get("tests_pasaron"))

    cuerpo = (explic + "\n\n") if explic else ""
    cuerpo += f"```{lenguaje}\n{codigo}\n```"

    # Estado honesto de verificación.
    tp = gen.get("tests_pasaron")
    if desde_cache:
        verif = "Recuperé esta solución del cuaderno (ya la habíamos resuelto)."
    elif not es_python:
        verif = f"Generado en {lenguaje} por Claude Code. (Ejecución automática solo para Python por ahora.)"
    elif tp is True:
        verif = "Lo generó Claude Code y lo corrí en tu máquina: anda."
    elif tp is False:
        verif = "Lo generó Claude Code, pero al correrlo acá dio error — revisalo."
    else:
        verif = "Generado por Claude Code (no llegué a ejecutarlo)."

    extra = (" " + a.get("resumen", "")) if (es_python and a.get("resumen")) else ""
    cuerpo += f"\n\n— {verif}{extra}"

    # Verificación semántica (predicción vs realidad), si se hizo.
    sem_txt = gen.get("semantica_txt")
    if sem_txt:
        cuerpo += "\n\n" + sem_txt

    if es_python and a.get("problemas"):
        cuerpo += "\n\nPara revisar:\n- " + "\n- ".join(a["problemas"][:8])

    meta = []
    if gen.get("turnos") is not None:
        meta.append(f"{gen['turnos']} turnos")
    if gen.get("costo") is not None:
        meta.append(f"${gen['costo']:.4f}")
    if meta and not desde_cache:
        cuerpo += f"\n\n— Claude Code · {' · '.join(meta)}"

    resumen = ("Recuperé la solución del cuaderno." if desde_cache
               else f"Generé la solución en {lenguaje} con Claude Code"
                    + (" y la probé, anda." if tp is True else "."))
    return {"ok": True, "skill": NOMBRE, "modo": "generacion", "resumen": resumen,
            "cuerpo": cuerpo, "costo": gen.get("costo")}


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

    return {"ok": True, "skill": NOMBRE, "modo": "debug", "resumen": "Diagnostiqué el código.", "cuerpo": cuerpo}


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