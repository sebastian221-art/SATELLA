"""
nucleo/habilidades/agente_cc/skill.py — AGENTE (Claude Code).
─────────────────────────────────────────────────────────────────────────────
EL agente de código de Satella. Satella ORQUESTA; Claude Code EJECUTA.
Vos pedís la misión, el gobernador controla, Claude Code la hace, y Satella se
queda con el resultado y la voz. Claude Code es el obrero, no el jefe.

Tres modos (los detecta solo):
  1. MISIÓN   — «en <proyecto>: <qué hacer>» → Claude Code edita ese proyecto.
  2. CLONAR   — «cloná https://github.com/u/repo» → git clone a proyectos/, y si
                hay misión después, la corre.
  3. CREAR    — «creá un proyecto llamado X que ...» → crea proyectos/X y Claude
                Code lo construye.

Seguridad — TODO pasa por el GOBERNADOR antes de actuar:
  - Editar/crear archivos en TUS proyectos = ESCRITURA → en modo normal, permitido.
  - Si pedís que VERIFIQUE corriendo (tests/build) = EJECUCIÓN → pide confirmación.
  - Clonar a tu carpeta de proyectos = ESCRITURA sobre lo tuyo → permitido en normal.
  - Modo seguro: todo confirma. Kill switch: nada se ejecuta.

Siempre devuelve ok=True una vez que detecta() disparó: la respuesta es SUYA
(éxito o error), así generacion.py no la descarta ni inventa una respuesta.
"""
import os
import re
import json
import shutil
import logging
import subprocess
from pathlib import Path

from nucleo.habilidades import contrato

try:
    from nucleo.habilidades.gobernador import motor as _gob, politica as _pol
    _GOB_OK = True
except Exception:  # pragma: no cover
    _GOB_OK = False
    _gob = None
    _pol = None

log = logging.getLogger("satella.habilidad.agente_cc")

NOMBRE = "agente_cc"
COMPUESTA = False
DESCRIPCION = (
    "Agente de código de Satella, ejecutado por Claude Code. Recibe misiones "
    "sobre tus proyectos (editar), cloná repos de GitHub y crea proyectos "
    "nuevos. Satella orquesta y el gobernador controla; Claude Code ejecuta. "
    "Edita archivos directo; corre comandos solo si lo pedís y se confirma."
)
EJEMPLOS = [
    "agente cc en prueba_cc: creá hola.py que imprima hola",
    "en bellavista, en index.html agregá un botón de WhatsApp",
    "cloná https://github.com/sebastian221-art/bellavista",
    "creá un proyecto llamado agenda que sea una to-do list en html",
    "agente, en bellavista, verificá: corré los tests y arreglá lo que falle",
]

# ── Triggers / verbos (absorbe la superficie del agente viejo) ───────────────
_TRIGGERS_CC = ("agente cc", "agente claude", "claude code",
                "usá claude code", "usa claude code", "con claude code")
_VERBOS_MISION = ("agente", "encargate", "encargá", "hacete cargo", "ocupate",
                  "ocupá", "mantené", "manten", "mantener", "en el proyecto",
                  "en bellavista", "misión en", "mision en", "tarea en")
_VERBOS_CLONAR = ("cloná", "clona", "clonar", "cloname", "cloná el repo",
                  "descargá el repo", "bajá el repo", "baja el repo", "git clone")
_VERBOS_CREAR = ("creá un proyecto", "crea un proyecto", "creame un proyecto",
                 "créame un proyecto", "hazme un proyecto", "hacéme un proyecto",
                 "haceme un proyecto", "creá una app", "crea una app",
                 "hacé una app", "hace una app", "armá un proyecto",
                 "arma un proyecto", "generá un proyecto", "genera un proyecto",
                 "proyecto desde cero")
_VERBOS_ANALISIS = ("analizá", "analiza", "auditá", "audita", "revisá la seguridad")

# Tools de Claude Code. Sin Bash = solo edita archivos (ESCRITURA).
_TOOLS_EDICION = "Read,Write,Edit,Glob,Grep"
_TOOLS_VERIFICA = "Read,Write,Edit,Glob,Grep,Bash"
_PIDE_VERIFICAR = ("verificá", "verifica", "verificar", "corré los tests",
                   "corre los tests", "corré el", "build", "compilá", "compila")

_MAX_TURNS = int(os.environ.get("SATELLA_CC_MAX_TURNS", "20"))
_TIMEOUT_S = int(os.environ.get("SATELLA_CC_TIMEOUT", "900"))


def _raiz_proyectos() -> Path:
    env = os.environ.get("SATELLA_PROYECTOS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3].parent / "proyectos"


def _url_github(texto: str):
    m = re.search(r"https?://github\.com/[\w\-.]+/[\w\-.]+", texto or "", re.I)
    if m:
        return m.group(0).rstrip("/.")
    m2 = re.search(r"\bgithub\.com/[\w\-.]+/[\w\-.]+", texto or "", re.I)
    return ("https://" + m2.group(0).rstrip("/.")) if m2 else None


# ── detecta() ────────────────────────────────────────────────────────────────
def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()

    if any(k in t for k in _TRIGGERS_CC):
        return True
    if any(v in t for v in _VERBOS_CLONAR):
        return True
    if any(v in t for v in _VERBOS_CREAR):
        return True
    if any(re.search(r"\b" + re.escape(v) + r"\b", t) for v in _VERBOS_MISION):
        return True
    if _url_github(t) and not any(v in t for v in _VERBOS_ANALISIS):
        return True

    raiz = _raiz_proyectos()
    for cand in re.findall(r"\ben\s+([\w\-.]+)", t):
        try:
            if (raiz / cand).is_dir():
                return True
        except Exception:
            continue
    return False


# ── Parseo ───────────────────────────────────────────────────────────────────
def _quitar_triggers(texto: str) -> str:
    s = texto
    for k in _TRIGGERS_CC:
        s = re.sub(re.escape(k), "", s, flags=re.IGNORECASE)
    return s


def _proyecto_existente(texto: str):
    raiz = _raiz_proyectos()
    for cand in re.findall(r"\ben\s+([\w\-.]+)", texto, flags=re.IGNORECASE):
        try:
            if (raiz / cand).is_dir():
                return cand
        except Exception:
            continue
    return None


def _mision_desde(texto: str, proyecto: str = None) -> str:
    if ":" in texto:
        return texto.split(":", 1)[1].strip()
    s = _quitar_triggers(texto)
    if proyecto:
        s = re.sub(r"\ben\s+" + re.escape(proyecto), "", s, flags=re.IGNORECASE)
    return s.strip(" ,.:").strip()


def _nombre_nuevo_proyecto(texto: str):
    m = re.search(r"(?:llamad[oa]|se llame|llamálo|llamalo|de nombre|nombre)\s+([a-zA-Z0-9_\-]{2,})",
                  texto or "", re.I)
    return m.group(1) if m else None


# ── Binarios ─────────────────────────────────────────────────────────────────
def _buscar_bin(nombre: str):
    for cand in (nombre, nombre + ".cmd", nombre + ".exe"):
        p = shutil.which(cand)
        if p:
            return p
    return None


def _git_clone(url: str, dest: Path) -> dict:
    git = _buscar_bin("git")
    if not git:
        return {"_falla": "No encuentro `git`. Instalalo o agregalo al PATH."}
    try:
        proc = subprocess.run(
            [git, "clone", url, str(dest)],
            capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace",
        )
    except Exception as e:
        return {"_falla": f"No pude clonar: {e}"}
    if proc.returncode != 0:
        return {"_falla": "git clone falló: " + (proc.stderr or "").strip()[:400]}
    return {"ok": True}


# ── Claude Code headless ─────────────────────────────────────────────────────
def _correr_claude(mision: str, cwd: Path, tools: str) -> dict:
    binario = _buscar_bin("claude")
    if not binario:
        return {"_falla": ("No encuentro el comando `claude`. ¿Está instalado "
                           "Claude Code? Probá `claude --version`.")}
    cmd = [
        binario, "-p", mision,
        "--output-format", "json",
        "--allowedTools", tools,
        "--permission-mode", "acceptEdits",
        "--max-turns", str(_MAX_TURNS),
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            timeout=_TIMEOUT_S, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"_falla": f"Claude Code se pasó de {_TIMEOUT_S}s. Probá una misión "
                          "más chica o subí SATELLA_CC_TIMEOUT."}
    except Exception as e:
        return {"_falla": f"No pude lanzar Claude Code: {e}"}

    salida = (proc.stdout or "").strip()
    data = None
    try:
        data = json.loads(salida)
    except Exception:
        m = re.search(r"\{.*\}", salida, flags=re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None

    if data is None:
        if proc.returncode != 0:
            return {"_falla": f"Claude Code salió con código {proc.returncode}. "
                              f"stderr: {(proc.stderr or '').strip()[:600] or '(vacío)'}"}
        return {"_falla": "Claude Code no devolvió JSON. Salida: "
                          + (salida[:400] or "(vacía)")}

    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        return {"_falla": "Claude Code reportó error: "
                          + str(data.get("result") or data.get("subtype") or "desconocido")}

    res = (data.get("result") or "").strip()
    if not res:
        return {"_falla": "Claude Code devolvió respuesta vacía. Hacé la misión más concreta."}

    return {
        "resultado": res,
        "costo": data.get("total_cost_usd"),
        "turnos": data.get("num_turns"),
        "duracion_ms": data.get("duration_ms"),
    }


# ── Gobernador ───────────────────────────────────────────────────────────────
def _gate(accion: str, objetivo: str, nivel) -> dict:
    """Devuelve {'pasa': True} si se puede actuar, o {'_bloqueo': <resultado>} si no."""
    if not _GOB_OK:
        return {"_bloqueo": contrato.resultado(
            NOMBRE, "bloqueado", "No puedo verificar el gobernador, no actúo",
            "No pude cargar la capa de control (gobernador). Por seguridad no ejecuto nada.")}
    v = _gob.evaluar(accion=accion, nivel=nivel, objetivo=objetivo, propio=True)
    ver = v.get("veredicto")
    if ver == _pol.DENEGADO:
        return {"_bloqueo": contrato.resultado(
            NOMBRE, "denegado", "El gobernador denegó la acción",
            f"Razón: {v.get('razon', 'sin detalle')}")}
    if ver == _pol.CONFIRMAR:
        token = v.get("token", "?")
        return {"_bloqueo": contrato.resultado(
            NOMBRE, "confirmar", "Necesito tu confirmación antes de actuar",
            f"{v.get('razon', '')}\n\nPara autorizar: «aprobá {token}». Después repetí el pedido.")}
    return {"pasa": True}


def _meta_txt(r: dict) -> str:
    meta = []
    if r.get("turnos") is not None:
        meta.append(f"{r['turnos']} turnos")
    if r.get("costo") is not None:
        meta.append(f"${r['costo']:.4f}")
    if r.get("duracion_ms") is not None:
        meta.append(f"{r['duracion_ms'] / 1000:.1f}s")
    return ("  ·  " + " · ".join(meta)) if meta else ""


# ── manejar() ────────────────────────────────────────────────────────────────
def manejar(texto: str, contexto: dict = None) -> dict:
    t = (texto or "").lower()
    raiz = _raiz_proyectos()

    # ── MODO CLONAR ───────────────────────────────────────────────────────────
    url = _url_github(texto)
    if url or any(v in t for v in _VERBOS_CLONAR):
        if not url:
            return contrato.resultado(
                NOMBRE, "aviso", "Para clonar necesito la URL del repo",
                "Pasámela completa, ej: «cloná https://github.com/usuario/repo».")
        nombre = url.rstrip("/").split("/")[-1].replace(".git", "")
        dest = raiz / nombre

        if not dest.is_dir():
            g = _gate(f"clonar {url}", str(dest), _pol.ESCRITURA if _GOB_OK else None)
            if "_bloqueo" in g:
                return g["_bloqueo"]
            cl = _git_clone(url, dest)
            if "_falla" in cl:
                return contrato.resultado(NOMBRE, "error", "No pude clonar", cl["_falla"])

        # Misión sólo si hay tarea explícita tras ":". Saco la URL primero para que
        # el ":" de "https://" no se confunda con el separador de tarea.
        resto = texto.replace(url, "")
        mision = resto.split(":", 1)[1].strip() if ":" in resto else ""
        if not mision:
            return contrato.resultado(
                NOMBRE, "clonado", f"{nombre} listo",
                f"El repo {nombre} está en {dest}. Para trabajarlo: «en {nombre}: <qué hacer>».")
        return _ejecutar_mision(texto, t, nombre, dest)

    # ── MODO CREAR ────────────────────────────────────────────────────────────
    if any(v in t for v in _VERBOS_CREAR):
        nombre = _nombre_nuevo_proyecto(texto) or "proyecto_nuevo"
        dest = raiz / nombre
        mision = _mision_desde(texto)
        g = _gate(f"crear proyecto {nombre}", str(dest), _pol.ESCRITURA if _GOB_OK else None)
        if "_bloqueo" in g:
            return g["_bloqueo"]
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return contrato.resultado(NOMBRE, "error", "No pude crear la carpeta", str(e))
        r = _correr_claude(mision or "Inicializá el proyecto.", dest, _TOOLS_EDICION)
        if "_falla" in r:
            return contrato.resultado(NOMBRE, "error", f"No pude crear {nombre}", r["_falla"])
        return contrato.resultado(
            NOMBRE, "creado", f"Proyecto '{nombre}' creado",
            r["resultado"] + f"\n\n— Claude Code{_meta_txt(r)}")

    # ── MODO MISIÓN ───────────────────────────────────────────────────────────
    proyecto = _proyecto_existente(texto)
    if not proyecto:
        disponibles = []
        try:
            disponibles = sorted([d.name for d in raiz.iterdir() if d.is_dir()])
        except Exception:
            pass
        lista = ", ".join(disponibles) if disponibles else "(no encontré proyectos)"
        return contrato.resultado(
            NOMBRE, "aviso", "¿Sobre qué proyecto?",
            f"Decime el proyecto con «en <nombre>: <misión>». En {raiz}: {lista}.")
    return _ejecutar_mision(texto, t, proyecto, raiz / proyecto)


def _ejecutar_mision(texto, t, proyecto, cwd) -> dict:
    mision = _mision_desde(texto, proyecto)
    if not mision:
        return contrato.resultado(
            NOMBRE, "aviso", "¿Qué querés que haga?",
            f"Decímelo así: «en {proyecto}: <qué hacer>».")
    if not cwd.is_dir():
        return contrato.resultado(
            NOMBRE, "aviso", f"No existe '{proyecto}'", f"No encontré la carpeta {cwd}.")

    quiere_verificar = any(k in t for k in _PIDE_VERIFICAR)
    tools = _TOOLS_VERIFICA if quiere_verificar else _TOOLS_EDICION
    nivel = (_pol.EJECUCION if quiere_verificar else _pol.ESCRITURA) if _GOB_OK else None

    g = _gate(f"Claude Code: {mision}", str(cwd), nivel)
    if "_bloqueo" in g:
        return g["_bloqueo"]

    r = _correr_claude(mision, cwd, tools)
    if "_falla" in r:
        return contrato.resultado(NOMBRE, "error", f"Claude Code no pudo en {proyecto}", r["_falla"])
    return contrato.resultado(
        NOMBRE, "ejecutado", f"Listo en {proyecto}",
        r["resultado"] + f"\n\n— Claude Code{_meta_txt(r)}")