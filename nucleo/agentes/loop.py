"""
nucleo/agentes/loop.py — EL CEREBRO DEL AGENTE (Capa 1).
─────────────────────────────────────────────────────────────────────────────
Un agente recibe una MISIÓN y la cumple encadenando las habilidades de Satella
como herramientas. La filosofía (definida por Sebas):

  1. PLANEA PRIMERO, NUNCA IMPROVISA. Antes de tocar nada, descompone la misión
     en pasos (con el planificador) y sigue ESE plan.
  2. RESUELVE LO CHICO, NO PARA TODO. Un error de sintaxis, un fallo a la primera,
     no lo frenan: reintenta hasta N veces. Solo escala lo que de verdad bloquea.
  3. OBSERVA CON CRITERIO, EN REVISIÓN. Sigue el plan aunque vea que algo no quedó
     bien, PERO lo anota y al final propone: "esto no salió como esperabas, ¿lo
     dejo o aplico mi fix?". Autonomía controlada — Sebas tiene la última palabra.
  4. CORREA. Cada herramienta pasa por el nivel de riesgo permitido. En la Capa 1
     los agentes solo reciben herramientas de LECTURA (cero efecto en el mundo).

Esta capa es de SOLO LECTURA: ningún agente escribe archivos, corre código ni
navega todavía. Eso llega en capas siguientes, con la correa del gobernador.
"""
import json
import logging
import re

log = logging.getLogger("satella.agentes")

# ── Escalera de riesgo (espejo de la del gobernador) ─────────────────────────
_ORDEN_RIESGO = ["lectura", "escritura", "navegacion", "ejecucion", "sistema"]
_RIESGO_SKILL = {
    "analisis": "lectura", "busqueda": "lectura", "telemetria": "lectura",
    "planificador": "lectura", "ingestor": "lectura", "introspeccion": "lectura",
    "creador": "escritura", "copia": "escritura", "mezclador": "escritura",
    "navegador": "navegacion",
    "python": "ejecucion", "agente_cc": "ejecucion", "sandbox": "ejecucion",
    "sistema": "sistema",
}

_REINTENTOS_POR_PASO = 3


# ── Catálogo de herramientas disponibles para el agente ──────────────────────
def _modulos_por_nombre() -> dict:
    try:
        from nucleo.habilidades import registro
        return {getattr(m, "NOMBRE", "?"): m for m in registro.habilidades()}
    except Exception as e:
        log.error(f"Agente: no pude listar habilidades: {e}")
        return {}


def _permitida(skill_nombre: str, nivel_riesgo: str) -> bool:
    """¿La skill está dentro del nivel de riesgo que el agente tiene permitido?"""
    riesgo = _RIESGO_SKILL.get(skill_nombre)
    if riesgo is None:
        return False  # desconocida → no
    try:
        return _ORDEN_RIESGO.index(riesgo) <= _ORDEN_RIESGO.index(nivel_riesgo)
    except ValueError:
        return False


def _catalogo(nivel_riesgo: str, herramientas=None) -> dict:
    """Mapa {nombre: modulo} de las herramientas que el agente puede usar:
    dentro de su nivel de riesgo y, si se dio una lista, solo esas."""
    todos = _modulos_por_nombre()
    cat = {}
    for nombre, mod in todos.items():
        if nombre in ("gobernador", "agentes", "agenda"):
            continue  # infraestructura, no son herramientas de agente
        if herramientas and nombre not in herramientas:
            continue
        if _permitida(nombre, nivel_riesgo):
            cat[nombre] = mod
    return cat


def _catalogo_texto(catalogo: dict) -> str:
    lineas = []
    for nombre, mod in catalogo.items():
        desc = getattr(mod, "DESCRIPCION", "") or ""
        lineas.append(f"- {nombre}: {desc[:120]}")
    return "\n".join(lineas)


# ── Elegir la herramienta para un paso ───────────────────────────────────────
_PROMPT_ELEGIR = """Sos un agente de Satella ejecutando un plan. Misión general: «{mision}».

Paso actual a resolver: «{paso}»

Herramientas disponibles (elegí UNA, la más adecuada para ESTE paso):
{catalogo}

Lo ya hecho hasta ahora:
{historial}

Respondé SOLO JSON, sin texto afuera:
{{"herramienta": "<nombre exacto de la lista>", "instruccion": "<qué pedirle, en una frase clara>"}}

Si ninguna herramienta sirve para este paso, respondé:
{{"herramienta": null, "instruccion": "<por qué ninguna sirve>"}}"""


def _elegir_herramienta(paso: str, catalogo: dict, historial: str, mision: str):
    """Devuelve (nombre_skill, instruccion) o (None, motivo)."""
    try:
        from nucleo.habilidades.python import _llm
        if not _llm.disponible():
            return (None, "no hay modelo disponible")
        prompt = _PROMPT_ELEGIR.format(
            mision=mision, paso=paso,
            catalogo=_catalogo_texto(catalogo),
            historial=historial or "(nada todavía)")
        salida = _llm.chat(prompt, max_tokens=2000, temperature=0.2,
                           reasoning_effort="low")
        if not salida:
            salida = _llm.chat(prompt, max_tokens=3500, temperature=0.2)
        obj = _parsear_eleccion(salida)
        if not obj:
            return (None, "no pude decidir la herramienta")
        herr = obj.get("herramienta")
        instr = (obj.get("instruccion") or paso).strip()
        if not herr or herr not in catalogo:
            return (None, instr or "ninguna herramienta aplica")
        return (herr, instr)
    except Exception as e:
        log.error(f"Agente: elegir herramienta falló: {e}")
        return (None, f"error eligiendo herramienta: {e}")


def _parsear_eleccion(salida: str) -> dict:
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
            if isinstance(obj, dict) and "herramienta" in obj:
                return obj
        except Exception:
            continue
    return {}


# ── La correa del gobernador ─────────────────────────────────────────────────
def _permiso_gobernador(skill_nombre: str, instruccion: str, desatendido: bool = False) -> dict:
    """Pasa la acción por el gobernador ANTES de ejecutarla. Devuelve su veredicto
    {veredicto, razon, token?}. Si el gobernador no está, solo deja pasar LECTURA."""
    nivel = _RIESGO_SKILL.get(skill_nombre, "sistema")
    # FASE 2: un agente DESATENDIDO (daemon) nunca ejecuta efecto real por su cuenta.
    # Todo lo que no sea lectura requiere tu OK → se escala, no se hace.
    if desatendido and nivel != "lectura":
        return {"veredicto": "confirmar",
                "razon": f"acción de nivel «{nivel}» corriendo sola — requiere tu OK"}
    try:
        from nucleo.habilidades.gobernador import motor as gob_motor
        return gob_motor.evaluar(accion=instruccion, nivel=nivel,
                                 objetivo=skill_nombre, propio=True,
                                 detalle="acción de agente")
    except Exception as e:
        log.warning(f"Agente: gobernador no disponible ({e}); solo permito lectura.")
        if nivel == "lectura":
            return {"veredicto": "permitido", "razon": "lectura sin gobernador"}
        return {"veredicto": "denegado",
                "razon": "el gobernador no está y la acción tiene efecto"}


def _firma(skill_nombre: str, instruccion: str) -> str:
    return f"{skill_nombre}::{(instruccion or '').strip().lower()[:120]}"


# ── ¿Este paso/misión pide CREAR código? (Capa 4) ────────────────────────────
# Usamos raíces (stems) para tolerar conjugaciones: cree/creá/crea/crear, etc.
_STEM_CREAR = ("cre", "hac", "arm", "escrib", "gener", "program", "implement",
               "construi", "construí", "codific", "desarroll")
_STEM_COMPUTAR = ("calcul", "comput", "orden", "sumar", "sumá", "multiplic", "convert",
                  "transform", "parse", "filtr", "cuent", "cont", "factori", "fibonacc",
                  "primo", "invert", "buscar en", "algoritm")
_SUST_CODIGO = ("script", "código", "codigo", "programa", "función", "funcion",
                "snippet", "algoritmo", "clase en python", "rutina")


def _mision_pide_codigo(mision: str) -> bool:
    """La misión global pide crear código: verbo de creación + sustantivo de código."""
    t = (mision or "").lower()
    crear = any(s in t for s in _STEM_CREAR)
    noun = any(n in t for n in _SUST_CODIGO)
    return crear and noun


def _es_paso_de_codigo(paso: str) -> bool:
    """El paso, por sí solo, ya pide código (creá un script / escribí el código…)."""
    t = (paso or "").lower()
    if any(n in t for n in _SUST_CODIGO) and any(s in t for s in _STEM_CREAR):
        return True
    return False


def _es_paso_de_reporte(paso: str) -> bool:
    """Pasos de cierre que NO se construyen (reportar, consolidar, informar…)."""
    t = (paso or "").lower()
    return any(k in t for k in ("report", "consolid", "inform", "resum", "escal", "avis"))


def _construir_codigo(paso, mision, nivel_riesgo, avisar):
    """Ruta del constructor: genera código y lo prueba en sandbox. Solo si el agente
    tiene nivel de ejecución (crear código es una capacidad real, no de lectura)."""
    try:
        permite = _ORDEN_RIESGO.index("ejecucion") <= _ORDEN_RIESGO.index(nivel_riesgo)
    except ValueError:
        permite = False
    if not permite:
        return {"paso": paso, "herramienta": "constructor",
                "resultado": "(no tengo nivel para crear código; soy de lectura)",
                "estado": "denegado",
                "observacion": f"El paso «{paso}» pide crear código, pero mi nivel es "
                               f"{nivel_riesgo}. Subime a ejecución si querés que construya."}
    from nucleo.agentes import constructor
    # La instrucción de construcción: el paso, con la misión como contexto.
    instr = paso if not mision else f"{paso} (contexto de la misión: {mision})"
    r = constructor.construir(instr, avisar=avisar)
    estado = "ok" if r.get("ok") else "bloqueado"
    return {"paso": paso, "herramienta": "constructor",
            "resultado": r.get("evidencia", ""), "estado": estado,
            "codigo": r.get("codigo", ""), "sandbox": r.get("sandbox", {}),
            "observacion": None if r.get("ok") else
            f"El código de «{paso}» no logró correr en sandbox: {r.get('resumen', '')}"}


# ── Ejecutar un paso (correa + dedup + reintentos para errores chicos) ────────
def _ejecutar_paso(paso, catalogo, historial_txt, mision, contexto, avisar, hechos,
                   nivel_riesgo="lectura", desatendido=False):
    """Devuelve un dict: {paso, herramienta, resultado, estado, observacion}.
    `hechos` es el cache de firmas ya ejecutadas (anti-estancamiento / dedup)."""
    from nucleo.habilidades import registro

    # CAPA 4: si el paso pide crear código —o la misión global es de crear código
    # y este paso no es de cierre/reporte— lo construye y lo prueba en sandbox.
    if _es_paso_de_codigo(paso) or (_mision_pide_codigo(mision) and not _es_paso_de_reporte(paso)):
        return _construir_codigo(paso, mision, nivel_riesgo, avisar)

    skill_nombre, instr = _elegir_herramienta(paso, catalogo, historial_txt, mision)
    if skill_nombre is None:
        return {"paso": paso, "herramienta": None,
                "resultado": instr, "estado": "saltado",
                "observacion": f"No encontré herramienta para «{paso}»: {instr}"}

    # ANTI-ESTANCAMIENTO: si ya hice exactamente esto, reuso el resultado y no repito.
    firma = _firma(skill_nombre, instr)
    if firma in hechos:
        return {"paso": paso, "herramienta": skill_nombre,
                "resultado": f"(ya lo había hecho antes, reusé el resultado) {hechos[firma][:200]}",
                "estado": "reusado", "observacion": None}

    # CORREA: el gobernador decide si esta acción puede ejecutarse.
    permiso = _permiso_gobernador(skill_nombre, instr, desatendido)
    vered = (permiso or {}).get("veredicto", "denegado")
    if vered == "denegado":
        razon = permiso.get("razon", "denegado por política")
        return {"paso": paso, "herramienta": skill_nombre,
                "resultado": f"(el gobernador lo denegó: {razon})", "estado": "denegado",
                "observacion": f"El paso «{paso}» fue denegado por seguridad: {razon}"}
    if vered == "confirmar":
        token = permiso.get("token", "?")
        razon = permiso.get("razon", "requiere tu confirmación")
        return {"paso": paso, "herramienta": skill_nombre,
                "resultado": f"(requiere tu aprobación — token {token}: {razon})",
                "estado": "pendiente_aprobacion",
                "observacion": f"El paso «{paso}» necesita tu OK (aprobá {token}): {razon}"}

    # PERMITIDO: ejecutar con reintentos para errores chicos.
    mod = catalogo[skill_nombre]
    ultimo_error = ""
    for intento in range(1, _REINTENTOS_POR_PASO + 1):
        if intento > 1:
            avisar(f"  reintento {intento}/{_REINTENTOS_POR_PASO} de «{paso[:40]}»…")
        try:
            res = registro.ejecutar(mod, instr, contexto)
            if res and res.get("ok"):
                cuerpo = (res.get("cuerpo") or res.get("resumen") or "").strip()
                hechos[firma] = cuerpo[:400]
                return {"paso": paso, "herramienta": skill_nombre,
                        "resultado": cuerpo[:1200], "estado": "ok",
                        "observacion": None}
            ultimo_error = (res or {}).get("resumen", "la herramienta no resolvió")
        except Exception as e:
            ultimo_error = str(e)
            log.warning(f"Agente: paso «{paso[:40]}» intento {intento} falló: {e}")

    # Agotó reintentos → bloqueado, pero NO frena todo: anota y sigue.
    return {"paso": paso, "herramienta": skill_nombre,
            "resultado": f"(no pude tras {_REINTENTOS_POR_PASO} intentos: {ultimo_error})",
            "estado": "bloqueado",
            "observacion": f"El paso «{paso}» quedó bloqueado: {ultimo_error}"}


# ── Consolidación final (el agente sintetiza sus hallazgos él mismo) ──────────
def _consolidar(mision: str, bitacora: list) -> str:
    """Cierra el hueco que Laura encontró: el agente NO necesita una herramienta
    aparte para 'resumir' — sintetiza sus propios resultados en un informe ejecutivo.
    Si el modelo no está, devuelve vacío y el reporte queda sin consolidación."""
    utiles = [b for b in bitacora if b["estado"] in ("ok", "reusado") and b.get("resultado")]
    if not utiles:
        return ""
    crudo = "\n\n".join(f"[{b['herramienta']}] {b['resultado']}" for b in utiles)
    try:
        from nucleo.habilidades.python import _llm
        if not _llm.disponible():
            return ""
        prompt = (
            f"Sos un agente de Satella. Tu misión fue: «{mision}».\n"
            f"Estos son los resultados que junté ejecutando mis herramientas:\n\n{crudo[:4000]}\n\n"
            "Escribí un informe ejecutivo BREVE (4-6 líneas, en español voseo) que consolide "
            "los hallazgos.\n"
            "REGLAS ESTRICTAS:\n"
            "- Usá ÚNICAMENTE lo que está en los resultados de arriba. Es tu única verdad.\n"
            "- PROHIBIDO agregar riesgos, advertencias, recomendaciones de seguridad, "
            "'cuellos de botella', 'monitorear', 'actualizar', o cualquier cosa que NO esté "
            "literalmente en los resultados. Si no lo viste en los datos, no existe.\n"
            "- Nada de relleno de consultor. Solo hechos que puedas señalar en los resultados.\n"
            "- Si querés marcar algo como opinión tuya, empezá esa línea con 'Opinión:' "
            "y dejá claro que es una hipótesis, no un dato."
        )
        sint = _llm.chat(prompt, max_tokens=1200, temperature=0.3, reasoning_effort="low")
        return (sint or "").strip()
    except Exception as e:
        log.warning(f"Agente: consolidación falló: {e}")
        return ""


# ── El loop principal ────────────────────────────────────────────────────────
def desplegar(mision: str, nombre: str = "agente", herramientas=None,
              nivel_riesgo: str = "lectura", limite_pasos: int = 8,
              contexto: dict = None, avisar=None, desatendido: bool = False) -> dict:
    """
    Despliega un agente para cumplir una misión.
    Si desatendido=True (daemon), la correa es estricta: nada con efecto real se
    ejecuta solo — se marca pendiente de tu OK y se escala.
    Devuelve un reporte estructurado para que Sebas valide o corrija.
    """
    def _av(t):
        if avisar:
            try:
                avisar(t)
            except Exception:
                pass

    catalogo = _catalogo(nivel_riesgo, herramientas)
    if not catalogo:
        return {"nombre": nombre, "mision": mision, "estado": "sin_herramientas",
                "plan": [], "bitacora": [], "observaciones": [],
                "mensaje": "No tengo herramientas disponibles para este nivel de riesgo."}

    # 1) PLANEAR (nunca improvisar).
    _av(f"🤖 {nombre}: planeando la misión…")
    pasos = []
    try:
        from nucleo.habilidades.planificador import planificador as plan_mod
        pasos = plan_mod.planificar(mision) or []
    except Exception as e:
        log.warning(f"Agente: planificador falló ({e}); uso la misión como paso único.")
    if not pasos:
        pasos = [mision]
    pasos = pasos[:limite_pasos]
    _av(f"🤖 {nombre}: plan de {len(pasos)} paso(s). Ejecutando…")

    # 2) EJECUTAR el plan, paso por paso.
    bitacora, observaciones = [], []
    hechos = {}  # firmas ya ejecutadas (anti-estancamiento / dedup)
    for i, paso in enumerate(pasos, 1):
        _av(f"  Paso {i}/{len(pasos)}: {paso[:70]}")
        historial_txt = "\n".join(
            f"- {b['paso'][:50]} → {b['estado']}" for b in bitacora) or ""
        r = _ejecutar_paso(paso, catalogo, historial_txt, mision, contexto, _av, hechos,
                           nivel_riesgo, desatendido)
        bitacora.append(r)
        if r.get("observacion"):
            observaciones.append(r["observacion"])

    # 3) CONSOLIDAR: el agente sintetiza sus propios hallazgos (sin herramienta extra).
    _av(f"🤖 {nombre}: consolidando hallazgos…")
    sintesis = _consolidar(mision, bitacora)

    # 4) ESTADO final.
    malos = [b for b in bitacora if b["estado"] in ("bloqueado", "saltado", "denegado")]
    pendientes = [b for b in bitacora if b["estado"] == "pendiente_aprobacion"]
    if pendientes:
        estado = "pendiente_aprobacion"
    elif not malos:
        estado = "listo"
    elif len(malos) == len(bitacora):
        estado = "bloqueado"
    else:
        estado = "listo_con_observaciones"

    return {"nombre": nombre, "mision": mision, "estado": estado,
            "plan": pasos, "bitacora": bitacora, "observaciones": observaciones,
            "sintesis": sintesis, "nivel_riesgo": nivel_riesgo,
            "herramientas_disponibles": list(catalogo.keys())}