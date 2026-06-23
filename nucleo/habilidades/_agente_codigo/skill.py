"""
nucleo/habilidades/agente_codigo/skill.py
─────────────────────────────────────────────────────────────────────────────
Habilidad: agente_codigo — el orquestador que convierte la skill de código en
un AGENTE. Cumple el contrato de Satella (NOMBRE, detecta, manejar) y se
autodescubre por registro.py.

Tres cosas que sabe hacer:
  1. CLONAR un repo de GitHub a la carpeta externa proyectos/ ("cloná bellavista").
  2. MISIÓN sobre un proyecto ya clonado ("en bellavista, en X.html: hacé Y").
     → resuelve los archivos por nombre dentro de proyectos/<proyecto>/,
       así no andás dando rutas locales nunca más.
  3. APRENDER de tu arreglo cuando te escaló algo.

Va ANTES que 'analisis' y 'python' en la prioridad del registro: una misión de
agente la toma el agente, no el analizador.
"""
import re
from pathlib import Path

from nucleo.habilidades import contrato
from . import agente, proyectos, constructor, bucle

NOMBRE = "agente_codigo"
COMPUESTA = False
DESCRIPCION = ("Agente de código: clona repos de GitHub a proyectos/, recibe misiones "
               "sobre ellos, edita, verifica por ejecución, escala lo difícil y aprende.")
EJEMPLOS = [
    "cloná https://github.com/sebastian221-art/bellavista",
    "agente, en bellavista, en panela-bloque.html: agregá un botón de WhatsApp",
    "aprendé que para el cursor la solución era el media query pointer:fine",
]

# ── Gobernador (para la escritura del clone en proyectos/) ───────────────────
try:
    from nucleo.habilidades.gobernador import motor as _gob, politica as _gpol
    _gob_ok = True
except Exception:
    _gob_ok = False

# ── Disparadores ─────────────────────────────────────────────────────────────
_VERBOS_CLONAR = (
    "cloná", "clona ", "clonar", "cloname", "clonalo",
    "traé el repo", "trae el repo", "traé el proyecto", "trae el proyecto",
    "bajá el repo", "baja el repo", "bajá el proyecto", "importá", "importa el",
    "descargá el repo", "descarga el repo", "traé de github", "bajá de github",
)
_VERBOS_CREAR = (
    "creá un proyecto", "crea un proyecto", "creame un proyecto", "créame un proyecto",
    "hazme un proyecto", "hacéme un proyecto", "haceme un proyecto",
    "creá una app", "crea una app", "hacé una app", "hace una app",
    "creá un programa", "crea un programa", "creá un script de", "crea un script de",
    "armá un proyecto", "arma un proyecto", "generá un proyecto", "genera un proyecto",
    "construí un proyecto", "proyecto desde cero",
)
_VERBOS_MISION = (
    "encargate", "encargá", "hacete cargo", "mantené", "manten", "mantener",
    "agente", "vigilá", "vigila", "monitoreá", "ocupate", "ocupá",
    "actualizá las", "actualiza las", "en todas las", "en las paginas",
    "en las páginas", "en el proyecto", "en bellavista",
)
_VERBOS_ARREGLO = (
    "la solución era", "la solucion era", "se arreglaba", "aprendé que",
    "aprende que", "para la próxima", "se resolvía", "se resolvia",
    "el arreglo es", "recordá que para",
)
_FRASES_BULK = (
    "todas las páginas", "todas las paginas", "todos los html", "todos los archivos",
    "en todo el proyecto", "cada página", "cada pagina", "las 6 páginas",
    "las seis páginas", "todas las de producto", "las páginas de producto",
)
_RX_FILE = r"[\w\-:~/\\.]+\.(?:py|html?|css|js|json)"


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    if "github.com/" in t:
        return True
    if any(v in t for v in _VERBOS_CREAR):
        return True
    if any(v in t for v in _VERBOS_CLONAR):
        return True
    if any(v in t for v in _VERBOS_ARREGLO):
        return True
    if any(v in t for v in _VERBOS_MISION):
        return True
    return False


def _nombre_proyecto_explicito(texto: str):
    m = re.search(r"(?:llamad[oa]|se llame|llamálo|llamalo|de nombre|nombre)\s+([a-zA-Z0-9_\-]{2,})",
                  texto or "", re.I)
    return m.group(1) if m else None


def _es_clonar(t: str) -> bool:
    return ("github.com/" in t) or any(v in t for v in _VERBOS_CLONAR)


def _inferir_proyecto(texto: str, contexto: dict) -> str:
    if contexto and contexto.get("proyecto"):
        return contexto["proyecto"]
    m = re.search(r"(?:proyecto|en)\s+([a-zA-Z0-9_\-]{3,})", texto or "")
    return m.group(1) if m else "default"


def _archivos_mencionados(texto: str) -> list:
    return re.findall(_RX_FILE, texto or "")


def _es_bulk(t: str) -> bool:
    return any(f in t for f in _FRASES_BULK)


def manejar(texto: str, contexto: dict = None) -> dict:
    contexto = contexto or {}
    t = (texto or "").lower()

    # ── 0) CREAR un proyecto desde cero ──────────────────────────────────────
    if any(v in t for v in _VERBOS_CREAR):
        nombre = _nombre_proyecto_explicito(texto)
        res = constructor.crear_proyecto(texto, nombre)
        return contrato.resultado(NOMBRE, "crear",
                                  "Proyecto creado." if res["estado"] == "ok" else "No pude crear el proyecto.",
                                  res["informe"], ok=True)

    # ── 1) CLONAR repo de GitHub ─────────────────────────────────────────────
    if _es_clonar(t):
        # la escritura en proyectos/ pasa por el gobernador (es tuyo → permitido en normal)
        if _gob_ok:
            v = _gob.evaluar("clonar repo a proyectos/", nivel=_gpol.ESCRITURA,
                             objetivo=str(proyectos.base()), propio=True)
            if v["veredicto"] == _gpol.DENEGADO:
                return contrato.resultado(NOMBRE, "clonar", "Bloqueado por el gobernador.",
                                          v["razon"], ok=True)
            if v["veredicto"] == _gpol.CONFIRMAR:
                return contrato.resultado(NOMBRE, "clonar", "Necesito que confirmes.",
                                          f"El gobernador pide confirmación (token {v.get('token')}) antes de clonar.", ok=True)
        res = proyectos.clonar(texto)
        return contrato.resultado(NOMBRE, "clonar",
                                  "Repo clonado." if res["ok"] else "No pude clonar.",
                                  res["mensaje"], ok=True)

    # ── 2) APRENDER de tu arreglo ────────────────────────────────────────────
    if any(v in t for v in _VERBOS_ARREGLO):
        proyecto = _inferir_proyecto(texto, contexto)
        res = agente.aprender_de_arreglo(proyecto, texto, contexto.get("solucion", texto))
        return contrato.resultado(NOMBRE, "aprender", "Arreglo guardado en el manual.",
                                  res["informe"], ok=True)

    # ── 3) MISIÓN sobre un proyecto ──────────────────────────────────────────
    proyecto = _inferir_proyecto(texto, contexto)

    if proyectos.existe(proyecto):
        # fast-lane masivo ("todas las páginas de producto"): flujo probado multi-archivo
        if _es_bulk(t):
            archivos = [a for a in proyectos.listar_archivos(proyecto)
                        if Path(a).suffix.lower() in (".html", ".htm")]
            if "producto" in t:
                archivos = [a for a in archivos if Path(a).name.lower() != "index.html"]
            if archivos:
                res = agente.ejecutar_mision(texto, proyecto, archivos)
                return contrato.resultado(NOMBRE, "mision", _resumen_estado(res["estado"]), res["informe"], ok=True)

        # general: LOOP ReAct — el agente explora, decide y edita paso a paso
        res = bucle.ejecutar(texto, proyectos.ruta(proyecto), proyecto=proyecto)
        return contrato.resultado(NOMBRE, "mision", _resumen_estado(res["estado"]), res["informe"], ok=True)

    # ── fallback: proyecto NO clonado → rutas locales sueltas ────────────────
    mencionados = _archivos_mencionados(texto)
    archivos = list(contexto.get("archivos") or []) or [a for a in mencionados if Path(a).exists()]
    if not archivos:
        cuerpo = (f"No tengo el proyecto «{proyecto}» en proyectos/. "
                  f"Cloná el repo (ej: «cloná https://github.com/tu-usuario/{proyecto}») y te lo manejo "
                  f"por nombre, o pasame la ruta completa del archivo.")
        return contrato.resultado(NOMBRE, "mision", "Falta el proyecto.", cuerpo, ok=True)
    res = agente.ejecutar_mision(texto, proyecto, archivos)
    return contrato.resultado(NOMBRE, "mision", _resumen_estado(res["estado"]), res["informe"], ok=True)


def _resumen_estado(estado: str) -> str:
    return {
        "ok": "Misión cumplida.",
        "escalado": "No pude solo — te lo escalo (y aprendo cuando lo arregles).",
        "sin_cambios": "Revisé y no hizo falta cambiar nada.",
        "ocupado": "Ya estoy con otra misión en ese proyecto.",
        "error": "El agente no pudo arrancar.",
    }.get(estado, "Listo.")