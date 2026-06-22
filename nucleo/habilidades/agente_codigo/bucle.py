"""
nucleo/habilidades/agente_codigo/bucle.py
─────────────────────────────────────────────────────────────────────────────
EL LOOP ReAct con WORKSPACE — el corazón del agente, estilo Claude Code.

    juntar contexto -> el modelo decide UNA acción -> ejecutarla ->
    observar el resultado REAL -> repetir, hasta "terminar".

MANEJO DE CONTEXTO (la parte que lo hace serio):
El contexto que ve el modelo en cada paso tiene TRES zonas:
  1. FIJO        : objetivo + plan + lista de archivos del proyecto. Siempre visible.
  2. WORKSPACE   : los archivos que abrió, mostrados SIEMPRE con su contenido ACTUAL
                   (se refresca solo tras cada edición). El modelo nunca queda ciego
                   ni necesita releer: mira el workspace.
  3. BITÁCORA    : registro CORTO de las últimas acciones y sus resultados (sin volcar
                   archivos enteros — esos viven en el workspace).
Esto evita llenar la ventana de basura: "lo justo, siempre actualizado", no "todo".
Lo que no está abierto sigue alcanzable con buscar/leer (como un RAG sobre el repo).

Protocolo agnóstico de modelo: el modelo responde UN JSON por turno (no depende de
tool-calling nativo) → sirve con DeepSeek, Groq o un modelo local.
"""
import json
import logging
import re
import threading

from . import cerebro, manual
from .herramientas import Herramientas

log = logging.getLogger("satella.agente.bucle")

MAX_PASOS = 12
MAX_PROFUNDIDAD = 2          # un agente puede delegar en subagentes, pero no infinito
TOPE_ARCHIVO_WS = 8000       # chars por archivo en el workspace
TOPE_WORKSPACE = 32000       # chars totales del workspace (si se pasa, deja los últimos)

_lock = threading.Lock()
_en_curso = set()

_SISTEMA = (
    "Sos un agente de código de Satella trabajando dentro de UN proyecto. Cumplís el "
    "objetivo en pasos: en cada turno elegís UNA herramienta, ves el resultado real, y seguís.\n\n"
    "Herramientas:\n"
    "  listar(subdir?)                 -> lista los archivos del proyecto\n"
    "  leer_archivo(ruta)              -> abre un archivo en tu WORKSPACE\n"
    "  buscar(patron)                  -> busca texto en todo el proyecto (grep)\n"
    "  editar_archivo(ruta, cambios)   -> aplica varios reemplazos de una vez.\n"
    "      'cambios' = [{\"buscar\":\"texto EXACTO del archivo\",\"reemplazar\":\"nuevo\"}, ...]\n"
    "  correr_comando(comando)         -> corre python/pytest DENTRO del proyecto y te da la salida REAL\n"
    "      (ej: \"python main.py stats\", \"pytest\"). Para VERIFICAR que tu cambio funciona.\n"
    "  delegar(subtarea)               -> pasás una sub-tarea a un sub-agente aislado; te devuelve un resumen\n"
    "  terminar(resumen)               -> terminaste\n\n"
    "TU WORKSPACE: los archivos que abriste aparecen abajo SIEMPRE con su contenido ACTUAL, "
    "incluso después de editarlos. NO necesitás releer: miralos ahí.\n\n"
    "REGLAS (sé EFICIENTE — cada paso cuesta tokens):\n"
    "- Respondé SIEMPRE con UN solo objeto JSON y nada más:\n"
    '  {\"pensamiento\":\"...\",\"herramienta\":\"NOMBRE\",\"args\":{...}}\n'
    "- Abrí (leer_archivo) solo los archivos que vas a tocar. Si no sabés cuáles, listá o buscá.\n"
    "- Agrupá TODOS los cambios de un archivo en UNA sola llamada a editar_archivo (lista 'cambios').\n"
    "- En cada 'buscar' copiá el texto EXACTO como está en el workspace (poco contexto único).\n"
    "- Después de editar, VERIFICÁ con correr_comando (argumentos concretos, sin menús interactivos).\n"
    "- Resolvé en POCOS pasos: abrí lo justo, cambiá junto, verificá, terminá.\n"
    "- Cuando esté cumplido y verificado, llamá a terminar con un resumen honesto.\n"
    "- Si algo no se puede, terminá explicando qué quedó trabado."
)

_RX_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _parse_accion(texto: str):
    if not texto:
        return None
    t = re.sub(r"^```[a-zA-Z]*\n", "", texto.strip())
    t = re.sub(r"\n```$", "", t)
    m = _RX_JSON.search(t)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) and obj.get("herramienta") else None
    except Exception:
        return None


def _planificar(mision: str, inventario: str) -> str:
    sistema = ("Sos un planificador de cambios de código. Dado un objetivo y los archivos del "
               "proyecto, devolvé un plan CORTO y ordenado (3 a 6 pasos, una línea cada uno) de qué "
               "hacer y en qué archivo. Sin código, solo los pasos.")
    plan = cerebro.pensar_codigo(f"OBJETIVO: {mision}\n\n{inventario}", sistema, dificil=True)
    return plan.strip() if plan else ""


def _render_workspace(herr: Herramientas, vistos: list) -> str:
    if not vistos:
        return ""
    bloques = []
    total = 0
    # recorrer del más reciente al más viejo para que, si hay tope, queden los recientes
    for ruta in reversed(vistos):
        cont = herr.contenido_actual(ruta)
        if cont is None:
            continue
        if len(cont) > TOPE_ARCHIVO_WS:
            cont = cont[:TOPE_ARCHIVO_WS] + "\n…(truncado)…"
        bloque = f"### {ruta} (contenido ACTUAL):\n{cont}"
        if total + len(bloque) > TOPE_WORKSPACE:
            break
        bloques.append(bloque)
        total += len(bloque)
    if not bloques:
        return ""
    bloques.reverse()
    return "WORKSPACE — archivos abiertos, siempre con su contenido actual:\n" + "\n\n".join(bloques)


def ejecutar(mision: str, raiz_proyecto, proyecto: str = "", contexto_manual: str = "",
             max_pasos: int = MAX_PASOS) -> dict:
    if not cerebro.disponible():
        return {"estado": "error", "informe": "El cerebro de código no está disponible."}
    clave = proyecto or str(raiz_proyecto)
    with _lock:
        if clave in _en_curso:
            return {"estado": "ocupado",
                    "informe": f"Ya estoy trabajando en «{proyecto or clave}». Esperá a que termine antes de mandar otra (si no, dos agentes se pisan el archivo)."}
        _en_curso.add(clave)
    try:
        return _correr(mision, raiz_proyecto, proyecto, contexto_manual, max_pasos)
    finally:
        with _lock:
            _en_curso.discard(clave)


def _correr(mision: str, raiz_proyecto, proyecto: str, contexto_manual: str,
            max_pasos: int, profundidad: int = 0) -> dict:
    herr = Herramientas(raiz_proyecto)
    inventario = herr.listar()
    vistos = []          # rutas abiertas en el workspace (orden de aparición)
    bitacora = []        # registro corto de acciones
    ediciones_ok = 0
    fallos_parse = 0

    if proyecto and not contexto_manual:
        try:
            contexto_manual = manual.como_contexto(manual.recordar(proyecto, mision))
        except Exception:
            contexto_manual = ""

    # zona FIJA del contexto
    fijo = f"OBJETIVO: {mision}\n"
    if contexto_manual:
        fijo += f"\n{contexto_manual}\n"
    if profundidad == 0 and (len(mision) > 80 or inventario.count("\n") >= 2):
        plan = _planificar(mision, inventario)
        if plan:
            fijo += f"\nPLAN (seguilo, ajustá si hace falta):\n{plan}\n"
    fijo += f"\n{inventario}\n"

    for paso in range(1, max_pasos + 1):
        prompt = fijo
        ws = _render_workspace(herr, vistos)
        if ws:
            prompt += "\n" + ws
        if bitacora:
            prompt += "\nACCIONES RECIENTES:\n" + "\n".join(bitacora[-8:])
        prompt += f"\n\nPaso {paso}. Tu próxima acción (un JSON):"

        accion = _parse_accion(cerebro.pensar_codigo(prompt, _SISTEMA))
        if not accion:
            fallos_parse += 1
            bitacora.append(f"[{paso}] respuesta inválida (tiene que ser UN objeto JSON).")
            if fallos_parse >= 3:
                break
            continue
        fallos_parse = 0

        herramienta = accion.get("herramienta")
        args = accion.get("args", {}) or {}

        if herramienta == "terminar":
            resumen = args.get("resumen", "Listo.")
            estado = "ok" if ediciones_ok > 0 else "sin_cambios"
            if proyecto and ediciones_ok > 0:
                manual.registrar_exito(proyecto, mision, [], resumen)
            cola = f"\n({ediciones_ok} edición(es), {paso} pasos)" if ediciones_ok else f"\n(sin cambios, {paso} pasos)"
            return {"estado": estado, "informe": resumen + cola, "ediciones": ediciones_ok, "pasos": paso}

        if herramienta == "delegar":
            if profundidad >= MAX_PROFUNDIDAD:
                obs = "límite de sub-agentes alcanzado; resolvelo vos directamente."
            else:
                subtarea = args.get("subtarea") or args.get("tarea") or args.get("objetivo") or ""
                if not subtarea:
                    obs = "delegar necesita 'subtarea'."
                else:
                    log.info(f"[BUCLE] prof {profundidad} → delega: {subtarea[:80]}")
                    sub = _correr(subtarea, raiz_proyecto, proyecto, "", max_pasos, profundidad + 1)
                    ediciones_ok += sub.get("ediciones", 0)
                    obs = f"[sub-agente {sub.get('estado')}] {sub.get('informe', '')[:1000]}"
            bitacora.append(f"[{paso}] delegué → {obs[:800]}")
            log.info(f"[BUCLE] paso {paso} (prof {profundidad}): delegar")
            continue

        # — herramientas normales —
        if herramienta == "leer_archivo":
            ruta = args.get("ruta", "")
            cont = herr.contenido_actual(ruta)
            if cont is None:
                bitacora.append(f"[{paso}] leer {ruta} → no existe (revisá el nombre con listar)")
            else:
                if ruta not in vistos:
                    vistos.append(ruta)
                bitacora.append(f"[{paso}] abrí {ruta} en el workspace ({cont.count(chr(10)) + 1} líneas)")
        elif herramienta == "editar_archivo":
            obs = herr.usar(herramienta, args)
            ruta = args.get("ruta", "")
            if obs.startswith("OK:"):
                ediciones_ok += 1
                if ruta and ruta not in vistos:
                    vistos.append(ruta)
            bitacora.append(f"[{paso}] {obs[:300]}")
        elif herramienta in ("correr_comando", "buscar", "listar"):
            obs = herr.usar(herramienta, args)
            etiqueta = {"correr_comando": "corrí", "buscar": "busqué", "listar": "listé"}[herramienta]
            bitacora.append(f"[{paso}] {etiqueta}:\n{obs[:1500]}")
        else:
            bitacora.append(f"[{paso}] herramienta desconocida: {herramienta}")

        log.info(f"[BUCLE] paso {paso}: {herramienta} → {str(bitacora[-1])[:90]}")

    motivo = ("demasiadas respuestas mal formateadas" if fallos_parse >= 3
              else f"no terminó en {max_pasos} pasos")
    if proyecto:
        manual.registrar_escalacion(proyecto, mision, motivo, max_pasos)
    informe = (f"No pude cerrar la misión sola ({motivo}). Apliqué {ediciones_ok} edición(es). Te la escalo.\n"
               f"Cuando lo arregles, enseñámelo (\"aprendé que…\") y la próxima lo hago solo.")
    return {"estado": "escalado", "informe": informe, "ediciones": ediciones_ok, "escalado": True}