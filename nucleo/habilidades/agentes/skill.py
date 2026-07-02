"""
nucleo/habilidades/agentes/skill.py — DESPLEGAR Y GESTIONAR AGENTES.
─────────────────────────────────────────────────────────────────────────────
La cara de chat del sistema de agentes. Ahora maneja el PLANTEL de empleados:

  - CONTRATAR:  "contratá un agente llamado Laura para PSI"
  - DESPLEGAR (empleado de planta): "Laura, revisá la facturación" / "mandá a Laura a…"
  - DESPLEGAR (ad-hoc, de un solo uso): "desplegá un agente que revise X"
  - LISTAR:     "qué empleados tengo" / "mostrame el plantel"
  - DESPEDIR:   "despedí a Laura"

Un empleado de planta se despliega por nombre y ya sabe quién es: su dominio, su
misión y su nivel de riesgo. Cada corrida queda en su historial.

Capa 3: los empleados siguen siendo de SOLO LECTURA (revisar, analizar, leer
memoria). Crear y ejecutar código llega en la Capa 4, con la correa puesta.
"""
import json
import logging
import re

from nucleo.habilidades import contrato

try:
    from nucleo.agentes import loop as _loop
    from nucleo.agentes import plantel as _plantel
    from nucleo.agentes import supervisor as _supervisor
    _OK = True
except Exception:  # pragma: no cover
    _OK = False
    _loop = _plantel = _supervisor = None

try:
    from nucleo import progreso as _prog
except Exception:  # pragma: no cover
    _prog = None

log = logging.getLogger("satella.habilidad.agentes")

NOMBRE = "agentes"
DESCRIPCION = ("Despliega y gestiona agentes que cumplen misiones encadenando las "
               "habilidades de Satella. Maneja un plantel de empleados de planta "
               "(contratar, desplegar por nombre, listar, despedir). Capa 3: solo lectura.")
EJEMPLOS = [
    "contratá un agente llamado Laura para PSI",
    "Laura, revisá qué sabe Satella de PSI y reportá",
    "desplegá un agente que revise la telemetría y reporte",
    "qué empleados tengo",
]

# ── Disparadores por intención ───────────────────────────────────────────────
_T_LISTAR = ("qué empleados", "que empleados", "mi plantel", "el plantel", "mostrame el plantel",
             "mostrá el plantel", "mis agentes", "qué agentes tengo", "que agentes tengo",
             "listá los agentes", "lista los agentes", "listá el plantel", "quiénes trabajan",
             "quienes trabajan")
_T_CONTRATAR = ("contratá", "contrata ", "contratar", "creá un empleado", "crea un empleado",
                "creá un agente llamado", "crea un agente llamado", "nuevo empleado",
                "sumá un agente", "suma un agente", "dale de alta")
_T_DESPEDIR = ("despedí", "despedi ", "despedir", "echá a", "echa a", "dar de baja",
               "eliminá al agente", "elimina al agente", "borrá al agente", "borra al agente")
_T_DESPLEGAR = ("desplegá un agente", "desplega un agente", "mandá un agente", "manda un agente",
                "lanzá un agente", "lanza un agente", "que un agente", "un agente que")
_T_PROGRAMAR = ("programá", "programa a", "programar", "que corra cada", "que revise cada",
                "agendá un agente", "agenda un agente", "que trabaje cada", "automatizá")
_T_PROGRAMADOS = ("qué agentes están programados", "que agentes estan programados",
                  "qué hay programado", "que hay programado", "cartelera de agentes",
                  "agentes programados", "qué tenés programado", "lista de programados")
_T_DESPROGRAMAR = ("desprogramá", "desprograma", "cancelá el agente programado",
                   "cancela el agente programado", "quitá la programación", "sacá de la cartelera")
_T_BANDEJA = ("qué hicieron los agentes", "que hicieron los agentes", "mostrame la bandeja",
              "mi bandeja", "la bandeja", "reportes de los agentes", "qué pasó con los agentes",
              "que paso con los agentes", "qué reportaron", "novedades de los agentes",
              "qué dejaron los agentes")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    if any(k in t for k in (_T_LISTAR + _T_CONTRATAR + _T_DESPEDIR + _T_DESPLEGAR
                            + _T_BANDEJA + _T_PROGRAMAR + _T_PROGRAMADOS + _T_DESPROGRAMAR)):
        return True
    if "agente" in t and any(v in t for v in ("desplegá", "desplega", "creá", "crea",
                                              "mandá", "manda", "lanzá", "lanza",
                                              "hicieron", "hicieron los", "programá",
                                              "programados", "reportaron")):
        return True
    # ¿menciona a un empleado de planta con un verbo de acción?
    if _OK and _empleado_mencionado(t):
        return True
    return False


def _avisar(t: str):
    if _prog is not None:
        try:
            _prog.emitir(t)
        except Exception:
            pass


# Una misión de crear código necesita nivel de ejecución. El sandbox la mantiene
# segura igual (corre aislado, sin tocar nada real), así que es seguro elevarla.
# Usamos raíces para tolerar conjugaciones (cree/creá/crea/crear…).
_STEM_CREAR_SK = ("cre", "hac", "arm", "escrib", "gener", "program", "implement",
                  "construi", "construí", "codific", "desarroll")
_SUST_CODIGO_SK = ("script", "código", "codigo", "programa", "función", "funcion",
                   "snippet", "algoritmo", "rutina")


def _nivel_para_mision(mision: str, base: str) -> str:
    t = (mision or "").lower()
    pide_codigo = any(s in t for s in _STEM_CREAR_SK) and any(n in t for n in _SUST_CODIGO_SK)
    if pide_codigo and _ORDEN_RIESGO_IDX(base) < _ORDEN_RIESGO_IDX("ejecucion"):
        return "ejecucion"
    return base


def _ORDEN_RIESGO_IDX(nivel: str) -> int:
    orden = ["lectura", "escritura", "navegacion", "ejecucion", "sistema"]
    return orden.index(nivel) if nivel in orden else 0


def manejar(texto: str, contexto: dict = None) -> dict:
    if not _OK:
        return contrato.resultado(NOMBRE, "agentes", "sistema de agentes no disponible",
                                  "No pude cargar el loop/plantel de agentes.", ok=True)
    t = (texto or "").lower()

    if any(k in t for k in _T_LISTAR):
        return _listar_plantel()
    if any(k in t for k in _T_BANDEJA):
        return _ver_bandeja()
    if any(k in t for k in _T_PROGRAMADOS):
        return _listar_programados()
    if any(k in t for k in _T_DESPROGRAMAR):
        return _desprogramar(texto)
    if any(k in t for k in _T_PROGRAMAR):
        return _programar(texto)
    if any(k in t for k in _T_DESPEDIR):
        return _despedir(texto)
    if any(k in t for k in _T_CONTRATAR):
        return _contratar(texto)

    # ¿es un empleado de planta? → desplegarlo con su ficha.
    emp = _empleado_mencionado(t)
    if emp and not any(k in t for k in _T_DESPLEGAR):
        return _desplegar_empleado(emp, texto, contexto)

    # ad-hoc, de un solo uso.
    return _desplegar_adhoc(texto, contexto)


# ── Plantel: listar ──────────────────────────────────────────────────────────
def _listar_plantel() -> dict:
    empleados = _plantel.listar()
    if not empleados:
        return contrato.resultado(
            NOMBRE, "plantel", "plantel vacío",
            "Todavía no tenés empleados de planta. Contratá uno: «contratá un agente "
            "llamado Laura para PSI».", ok=True)
    lineas = []
    for e in empleados:
        resp = len(e.get("responsabilidades", []))
        corridas = len(e.get("historial", []))
        dom = e.get("dominio") or "—"
        lineas.append(f"- {e['nombre']} (dominio: {dom}) — {resp} responsabilidad(es), "
                      f"{corridas} corrida(s). Misión: {e.get('mision', '')[:70]}")
    cuerpo = f"Tu plantel ({len(empleados)} empleado(s)):\n" + "\n".join(lineas)
    return contrato.resultado(NOMBRE, "plantel", f"{len(empleados)} empleado(s)", cuerpo, ok=True)


# ── Plantel: despedir ────────────────────────────────────────────────────────
def _despedir(texto: str) -> dict:
    nombre = _nombre_suelto(texto)
    if not nombre:
        return contrato.resultado(NOMBRE, "despedir", "¿a quién?",
                                  "Decime a quién despido. Ej: «despedí a Laura».", ok=True)
    if _plantel.despedir(nombre):
        return contrato.resultado(NOMBRE, "despedir", f"{nombre} despedido",
                                  f"Listo, di de baja a {nombre.capitalize()} del plantel.", ok=True)
    return contrato.resultado(NOMBRE, "despedir", "no encontré ese empleado",
                              f"No tengo a nadie llamado «{nombre}» en el plantel.", ok=True)


# ── Plantel: contratar ───────────────────────────────────────────────────────
_PROMPT_CONTRATAR = """De esta orden de contratación de un agente, extraé los datos.

Orden: «{texto}»

Respondé SOLO JSON:
{{"nombre": "<nombre propio del agente>", "dominio": "<de qué se encarga, ej PSI / hospital / ''>", "mision": "<su trabajo permanente, una frase, o ''>"}}"""


def _contratar(texto: str) -> dict:
    datos = _extraer_contratacion(texto)
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        return contrato.resultado(
            NOMBRE, "contratar", "¿cómo se llama?",
            "Decime el nombre del agente. Ej: «contratá un agente llamado Laura para PSI».",
            ok=True)
    if _plantel.obtener(nombre):
        return contrato.resultado(
            NOMBRE, "contratar", "ya existe",
            f"Ya tengo a {nombre.capitalize()} en el plantel. Si querés cambiarle algo, "
            f"despedila y volvé a contratarla, o agregale responsabilidades.", ok=True)

    ficha = _plantel.contratar(nombre, dominio=datos.get("dominio", ""),
                               mision=datos.get("mision", ""), nivel_riesgo="lectura")
    cuerpo = (f"Contraté a {ficha['nombre']} 🎉\n"
              f"- Dominio: {ficha['dominio'] or '—'}\n"
              f"- Misión: {ficha['mision']}\n"
              f"- Nivel de riesgo: {ficha['nivel_riesgo']} (solo lectura por ahora)\n\n"
              f"Desplegala cuando quieras: «{ficha['nombre']}, revisá …».")
    return contrato.resultado(NOMBRE, "contratar", f"contraté a {ficha['nombre']}", cuerpo, ok=True)


def _extraer_contratacion(texto: str) -> dict:
    # 1) intento con el modelo (robusto)
    try:
        from nucleo.habilidades.python import _llm
        if _llm.disponible():
            salida = _llm.chat(_PROMPT_CONTRATAR.format(texto=texto),
                               max_tokens=1500, temperature=0.1, reasoning_effort="low")
            obj = _parsear_json(salida)
            if obj and obj.get("nombre"):
                return obj
    except Exception:
        pass
    # 2) fallback regex
    nombre = ""
    m = re.search(r"(?:llamado|llamada|agente|empleado)\s+([A-ZÁÉÍÓÚ][\wáéíóúñ]+)", texto)
    if m:
        nombre = m.group(1)
    dominio = ""
    m = re.search(r"\b(?:para|de|encargad[oa] de|del dominio)\s+([A-Za-z0-9\-\s]{2,30})", texto)
    if m:
        dominio = m.group(1).strip().split(" con ")[0].strip()
    return {"nombre": nombre, "dominio": dominio, "mision": ""}


# ── Daemon: programar / cartelera / bandeja ──────────────────────────────────
def _parsear_cuando(texto: str) -> dict:
    """Saca el 'cada cuánto' del texto natural. Devuelve un dict cuando, o None."""
    t = (texto or "").lower()
    m = re.search(r"cron[:\s]+([\d\*/,\-\s]{5,})", t)
    if m:
        return {"tipo": "cron", "cron": m.group(1).strip()}
    m = re.search(r"cada\s+(\d+)\s*(min|minuto|minutos|h|hora|horas)", t)
    if m:
        n = int(m.group(1))
        seg = n * 60 if m.group(2).startswith("min") else n * 3600
        return {"tipo": "intervalo", "intervalo_seg": seg}
    if "cada hora" in t:
        return {"tipo": "intervalo", "intervalo_seg": 3600}
    if "cada media hora" in t:
        return {"tipo": "intervalo", "intervalo_seg": 1800}
    m = re.search(r"a las\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m|p\.?m)?", t)
    if m and any(k in t for k in ("todos los días", "todos los dias", "diariamente",
                                  "cada día", "cada dia", "diario")):
        hh = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        if m.group(3) and m.group(3).startswith("p") and hh < 12:
            hh += 12
        return {"tipo": "diario", "hora": hh, "min": mm}
    if any(k in t for k in ("todos los días", "todos los dias", "diariamente", "diario")):
        return {"tipo": "diario", "hora": 9, "min": 0}
    return None


def _mision_de_programacion(texto: str) -> str:
    m = re.search(r"(?:para que|que)\s+(.+)", texto, re.IGNORECASE)
    mis = m.group(1).strip() if m else texto
    mis = re.sub(r"(todos los días|todos los dias|diariamente|cada\s+\d+\s*\w+|"
                 r"cada (hora|media hora|día|dia|minuto)|a las\s+\d+(:\d+)?\s*([ap]\.?m)?|"
                 r"cron[:\s].*)", "", mis, flags=re.IGNORECASE).strip(" ,.")
    return mis


def _programar(texto: str) -> dict:
    emp = _empleado_mencionado(texto.lower())
    nombre = emp["nombre"] if emp else _nombre_suelto(texto)
    cuando = _parsear_cuando(texto)
    mision = _mision_de_programacion(texto)
    if not nombre:
        return contrato.resultado(NOMBRE, "programar", "¿a quién?",
                                  "Decime qué empleado programar. Ej: «programá a Laura para "
                                  "que revise PSI todos los días a las 9».", ok=True)
    if not cuando:
        return contrato.resultado(NOMBRE, "programar", "¿cada cuánto?",
                                  f"¿Cada cuánto corre {nombre}? Ej: «todos los días a las 9», "
                                  "«cada 2 horas», «cada 30 minutos».", ok=True)
    if not mision or len(mision) < 3:
        mision = (emp or {}).get("mision", "revisar y reportar")
    try:
        from nucleo.agentes import programador
        t = programador.programar(nombre, mision, cuando)
        cuerpo = (f"Programado ✓\n{programador.describir(t)}\n\n"
                  f"El daemon lo va a correr solo. Acordate de tenerlo prendido en otra "
                  f"terminal: «python daemon_agentes.py». Lo que encuentre te lo deja en la "
                  f"bandeja, y te escala lo que necesite tu ojo.")
        return contrato.resultado(NOMBRE, "programar",
                                  f"programé a {nombre}", cuerpo, ok=True)
    except Exception as e:
        return contrato.resultado(NOMBRE, "programar", "no pude programar",
                                  f"Falló la programación: {e}", ok=True)


def _listar_programados() -> dict:
    try:
        from nucleo.agentes import programador
        tareas = programador.listar()
    except Exception as e:
        return contrato.resultado(NOMBRE, "programados", "error",
                                  f"No pude leer la cartelera: {e}", ok=True)
    if not tareas:
        return contrato.resultado(NOMBRE, "programados", "cartelera vacía",
                                  "No hay agentes programados. Ej: «programá a Laura para que "
                                  "revise PSI todos los días a las 9».", ok=True)
    lineas = [programador.describir(t) for t in tareas]
    cuerpo = f"Cartelera ({len(tareas)} programado/s):\n" + "\n".join(lineas)
    return contrato.resultado(NOMBRE, "programados", f"{len(tareas)} programado/s", cuerpo, ok=True)


def _desprogramar(texto: str) -> dict:
    m = re.search(r"#?(\d+)", texto)
    if not m:
        return contrato.resultado(NOMBRE, "desprogramar", "¿cuál?",
                                  "Decime el número. Ej: «desprogramá #1». Mirá la cartelera "
                                  "con «qué agentes están programados».", ok=True)
    try:
        from nucleo.agentes import programador
        if programador.quitar(int(m.group(1))):
            return contrato.resultado(NOMBRE, "desprogramar", "listo",
                                      f"Saqué el #{m.group(1)} de la cartelera.", ok=True)
    except Exception:
        pass
    return contrato.resultado(NOMBRE, "desprogramar", "no encontré",
                              f"No encontré el #{m.group(1)} en la cartelera.", ok=True)


def _ver_bandeja() -> dict:
    try:
        from nucleo.agentes import bandeja
        filas = bandeja.listar(n=12)
    except Exception as e:
        return contrato.resultado(NOMBRE, "bandeja", "error",
                                  f"No pude leer la bandeja: {e}", ok=True)
    if not filas:
        return contrato.resultado(NOMBRE, "bandeja", "bandeja vacía",
                                  "La bandeja está vacía. Cuando el daemon corra agentes "
                                  "programados, lo que encuentren va a aparecer acá.", ok=True)
    escaladas = [f for f in filas if f.get("escalado")]
    lineas = []
    if escaladas:
        lineas.append(f"⚠️ {len(escaladas)} cosa(s) piden tu atención:")
        for f in escaladas[:6]:
            lineas.append(f"  • [{f['ts'][11:16]}] {f['empleado']} "
                          f"({f.get('veredicto') or f['estado']}): {f['resumen'][:90]}")
        lineas.append("")
    lineas.append("Últimas corridas:")
    for f in filas[:8]:
        marca = "⚠️" if f.get("escalado") else "✓"
        lineas.append(f"  {marca} [{f['ts'][5:16]}] {f['empleado']} → {f['estado']}: "
                      f"{f['resumen'][:70]}")
    cuerpo = "\n".join(lineas)
    return contrato.resultado(NOMBRE, "bandeja",
                              f"{len(filas)} en bandeja, {len(escaladas)} escalada/s",
                              cuerpo, ok=True)


# ── Desplegar un empleado de planta ──────────────────────────────────────────
def _empleado_mencionado(texto_lower: str):
    """Devuelve la ficha de un empleado de planta si su nombre aparece en el texto."""
    try:
        for e in _plantel.listar():
            n = e.get("nombre", "").lower()
            if n and re.search(rf"\b{re.escape(n)}\b", texto_lower):
                return e
    except Exception:
        pass
    return None


def _desplegar_empleado(ficha: dict, texto: str, contexto: dict) -> dict:
    nombre = ficha["nombre"]
    dominio = ficha.get("dominio", "")
    # La instrucción específica de Sebas (lo que sigue al nombre), o su misión de planta.
    pedido = _pedido_tras_nombre(texto, nombre)
    if pedido:
        mision = f"En el dominio {dominio}: {pedido}" if dominio else pedido
    else:
        mision = ficha.get("mision", f"Vigilar {dominio}")

    ctx = dict(contexto or {})
    if dominio:
        ctx["dominio"] = dominio

    _avisar(f"🤖 Desplegando a {nombre} (dominio: {dominio or '—'})…")
    nivel = _nivel_para_mision(mision, ficha.get("nivel_riesgo", "lectura"))
    rep = _loop.desplegar(mision, nombre=nombre,
                          nivel_riesgo=nivel,
                          herramientas=ficha.get("herramientas") or None,
                          contexto=ctx, avisar=_avisar)

    # Registrar la corrida en el historial del empleado.
    try:
        resumen = (rep.get("sintesis") or "")[:300]
        _plantel.registrar_corrida(nombre, mision, rep.get("estado", "?"), resumen)
    except Exception:
        pass

    cuerpo = _formatear(rep, ficha=ficha)
    resumen = f"{nombre}: {rep.get('estado', '?')} ({len(rep.get('plan', []))} pasos)"
    return contrato.resultado(NOMBRE, "desplegar_empleado", resumen, cuerpo, ok=True)


def _pedido_tras_nombre(texto: str, nombre: str) -> str:
    """Saca lo que Sebas le pide al empleado tras nombrarlo. Ej: 'Laura, revisá X' → 'revisá X'."""
    t = texto.strip()
    # "Laura, <pedido>"  /  "Laura <pedido>"  /  "mandá a Laura a que <pedido>"
    m = re.search(rf"(?:mand[áa]|despleg[áa]|lanz[áa])\s+a\s+{re.escape(nombre)}\s+"
                  rf"(?:a\s+que|para\s+que|que|a)\s+(.+)", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(rf"\b{re.escape(nombre)}\b[\s,:]+(.+)", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# ── Desplegar ad-hoc (de un solo uso) ────────────────────────────────────────
def _desplegar_adhoc(texto: str, contexto: dict) -> dict:
    nombre, mision = _extraer_nombre_y_mision(texto)
    if not mision or len(mision) < 3:
        return contrato.resultado(
            NOMBRE, "agentes", "¿qué misión?",
            "Decime qué querés que haga el agente. Ej: «desplegá un agente que revise "
            "la telemetría y reporte».", ok=True)
    _avisar(f"🤖 Desplegando a {nombre}…")
    nivel = _nivel_para_mision(mision, "lectura")
    rep = _loop.desplegar(mision, nombre=nombre, nivel_riesgo=nivel,
                          contexto=contexto, avisar=_avisar)
    cuerpo = _formatear(rep)
    resumen = f"{nombre}: {rep.get('estado', '?')} ({len(rep.get('plan', []))} pasos)"
    return contrato.resultado(NOMBRE, "desplegar", resumen, cuerpo, ok=True)


def _extraer_nombre_y_mision(texto: str):
    t = (texto or "").strip()
    nombre = "agente"
    m = re.search(r"(?:mand[áa]|despleg[áa]|lanz[áa])\s+a\s+([A-ZÁÉÍÓÚ][\wáéíóúñ]+)\s+"
                  r"(?:a\s+que|para\s+que|que|a)\s+(.+)", t, re.IGNORECASE)
    if m:
        return m.group(1).strip().capitalize(), m.group(2).strip()
    for g in ("que revise", "que analice", "que busque", "que lea", "que reporte",
              "un agente que", "un agente para", "un agente"):
        idx = t.lower().find(g)
        if idx != -1:
            mision = t[idx + len(g):].strip(" :,.")
            if g.startswith("que "):
                mision = g[4:] + " " + mision
            if mision:
                return nombre, mision
    return nombre, t


# ── Utilidades ───────────────────────────────────────────────────────────────
def _nombre_suelto(texto: str) -> str:
    m = re.search(r"\b(?:a|al)\s+([A-ZÁÉÍÓÚ][\wáéíóúñ]+)", texto)
    if m:
        return m.group(1)
    m = re.search(r"([A-ZÁÉÍÓÚ][\wáéíóúñ]+)\s*$", texto.strip())
    return m.group(1) if m else ""


def _parsear_json(salida: str) -> dict:
    if not salida:
        return {}
    s = re.sub(r"```json|```", "", salida)
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    spans, pila = [], []
    for i, ch in enumerate(s):
        if ch == "{":
            pila.append(i)
        elif ch == "}" and pila:
            spans.append(s[pila.pop():i + 1])
    for cand in sorted(set(spans), key=len, reverse=True):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


# ── Formateo del reporte ─────────────────────────────────────────────────────
def _formatear(rep: dict, ficha: dict = None) -> str:
    nombre = rep.get("nombre", "agente")
    estado = rep.get("estado", "?")
    plan = rep.get("plan", [])
    bitacora = rep.get("bitacora", [])
    obs = rep.get("observaciones", [])

    if estado == "sin_herramientas":
        return rep.get("mensaje", "No tengo herramientas para esta misión.")

    cab = f"🤖 Agente {nombre}"
    if ficha and ficha.get("dominio"):
        cab += f" (dominio: {ficha['dominio']})"
    out = [f"{cab} — misión: {rep.get('mision', '')}", ""]

    out.append(f"PLAN ({len(plan)} paso(s)):")
    for i, p in enumerate(plan, 1):
        out.append(f"  {i}. {p}")
    out.append("")

    out.append("EJECUCIÓN:")
    iconos = {"ok": "✓", "reusado": "✓", "bloqueado": "⚠", "saltado": "•",
              "denegado": "🔒", "pendiente_aprobacion": "⏸"}
    for i, b in enumerate(bitacora, 1):
        ic = iconos.get(b["estado"], "·")
        herr = f" [{b['herramienta']}]" if b.get("herramienta") else ""
        # Paso de constructor: mostrar el código y la prueba del sandbox.
        if b.get("herramienta") == "constructor" and b.get("codigo"):
            out.append(f"  {ic} Paso {i} [constructor]:")
            out.append("    ```python")
            for ln in (b["codigo"] or "")[:1200].splitlines():
                out.append(f"    {ln}")
            out.append("    ```")
            res = (b.get("resultado") or "").strip()
            for ln in res.splitlines():
                out.append(f"    {ln}")
        else:
            res = (b.get("resultado") or "").strip().replace("\n", " ")
            out.append(f"  {ic} Paso {i}{herr}: {res[:220]}")
    out.append("")

    sintesis = (rep.get("sintesis") or "").strip()
    if sintesis:
        out.append("INFORME:")
        out.append(f"  {sintesis}")
        out.append("")

    # EL SUPERVISOR revisa el informe y separa lo confirmado de lo inventado.
    if _supervisor is not None and sintesis:
        try:
            dictamen = _supervisor.revisar(rep)
            bloque = _supervisor.formatear(dictamen)
            if bloque:
                out.append(bloque)
                out.append("")
        except Exception:
            pass

    if obs:
        out.append("OBSERVACIONES Y PROPUESTAS:")
        for o in obs:
            out.append(f"  - {o}")
        out.append("")

    cierre = {
        "listo": "Estado: LISTO. Seguí el plan completo. ¿Lo dejo así o querés correcciones?",
        "listo_con_observaciones": ("Estado: LISTO, con observaciones. Seguí el plan, pero "
                                    "anoté lo de arriba. ¿Lo dejo así o aplico/ajusto algo?"),
        "bloqueado": "Estado: BLOQUEADO. No pude avanzar. Te lo escalo para que lo revisemos.",
        "pendiente_aprobacion": ("Estado: PENDIENTE DE TU APROBACIÓN. Hay pasos que requieren "
                                 "tu OK antes de ejecutarse (revisá los pendientes del gobernador)."),
    }.get(estado, f"Estado: {estado}.")
    out.append(cierre)
    return "\n".join(out)