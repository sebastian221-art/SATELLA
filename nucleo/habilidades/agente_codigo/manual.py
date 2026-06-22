"""
nucleo/habilidades/agente_codigo/manual.py
─────────────────────────────────────────────────────────────────────────────
EL MANUAL DEL AGENTE — la memoria que crece por proyecto.

Cada proyecto tiene su propio manual: qué se hizo y funcionó, qué se le escaló
a Sebas y cómo lo arregló él. Lo que se aprende NO vive en pesos — vive acá,
en disco, y es tuyo. Da igual si el cerebro es Groq hoy o local mañana: el
manual queda.

Recuperación por similitud de palabras (Jaccard), igual que la memoria del
navegador. Suficientemente rápida para tiempo real en cualquier hardware.
"""
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

log = logging.getLogger("satella.agente.manual")

# datos/agentes/<proyecto>/manual.json  (subiendo 3 niveles desde este archivo)
_BASE = Path(__file__).resolve().parents[3] / "datos" / "agentes"

UMBRAL_SIMILITUD = 0.40   # qué tan parecida tiene que ser una misión para recordarla
MAX_RECUERDOS = 4         # cuántas entradas relevantes se inyectan al prompt

# Palabras vacías que no aportan al tema (no queremos que infle la similitud).
_VACIAS = {"que", "los", "las", "del", "una", "uno", "con", "por", "para",
           "este", "esta", "esto", "esos", "esas", "como", "pero", "mas",
           "muy", "ese", "esa", "the", "and", "for"}


# ── Normalización / similitud ────────────────────────────────────────────────
def _stem(p: str) -> str:
    """Stem por prefijo: corta conjugaciones/plurales (unificar/unifica → unifi)."""
    return p[:5] if len(p) > 5 else p


def _norm(texto: str) -> set:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palabras = re.findall(r"[a-z0-9_]+", t)
    return {_stem(p) for p in palabras if len(p) > 2 and p not in _VACIAS}


def _jaccard(a: set, b: set) -> float:
    """Coeficiente de solapamiento (intersección / menor) — más indulgente que
    Jaccard puro para misiones cortas, donde un texto suele ser más largo."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _slug(proyecto: str) -> str:
    s = unicodedata.normalize("NFKD", (proyecto or "default").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "default"


# ── Persistencia ─────────────────────────────────────────────────────────────
def _ruta(proyecto: str) -> Path:
    return _BASE / _slug(proyecto) / "manual.json"


def cargar(proyecto: str) -> dict:
    ruta = _ruta(proyecto)
    if ruta.exists():
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[MANUAL] {proyecto} corrupto, arranco vacío: {e}")
    return {"proyecto": proyecto, "exitos": [], "escalaciones": [], "arreglos": []}


def _guardar(proyecto: str, manual: dict):
    ruta = _ruta(proyecto)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(manual, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[MANUAL] no pude guardar {proyecto}: {e}")


# ── API que usa el agente ────────────────────────────────────────────────────
def recordar(proyecto: str, mision: str) -> list:
    """Devuelve las entradas pasadas más parecidas a esta misión (éxitos + arreglos).

    Esto es lo que hace que el agente 'ya sepa qué hacer' la próxima vez que
    aparece un problema parecido — sin reentrenar nada.
    """
    manual = cargar(proyecto)
    objetivo = _norm(mision)
    candidatos = []
    for tipo, lista in (("exito", manual["exitos"]), ("arreglo", manual["arreglos"])):
        for e in lista:
            sim = _jaccard(objetivo, _norm(e.get("mision", "")))
            if sim >= UMBRAL_SIMILITUD:
                candidatos.append((sim, tipo, e))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return [{"tipo": t, **e} for _, t, e in candidatos[:MAX_RECUERDOS]]


def registrar_exito(proyecto: str, mision: str, archivos: list, resumen: str):
    manual = cargar(proyecto)
    manual["exitos"].append({
        "mision": mision, "archivos": archivos, "resumen": resumen,
        "cuando": datetime.now().isoformat(timespec="seconds"),
    })
    manual["exitos"] = manual["exitos"][-200:]   # techo, no crece infinito
    _guardar(proyecto, manual)


def registrar_escalacion(proyecto: str, mision: str, error: str, intentos: int):
    """Registra que el agente no pudo y te lo escaló. Queda 'abierto' hasta que
    le enseñes el arreglo con aprender_de_arreglo()."""
    manual = cargar(proyecto)
    manual["escalaciones"].append({
        "mision": mision, "error": error, "intentos": intentos,
        "resuelto": False,
        "cuando": datetime.now().isoformat(timespec="seconds"),
    })
    manual["escalaciones"] = manual["escalaciones"][-100:]
    _guardar(proyecto, manual)


def aprender_de_arreglo(proyecto: str, mision: str, solucion: str):
    """Vos resolviste lo que el agente no pudo. Esto lo convierte en conocimiento:
    la próxima vez que aparezca algo parecido, recordar() se lo devuelve."""
    manual = cargar(proyecto)
    manual["arreglos"].append({
        "mision": mision, "solucion": solucion,
        "cuando": datetime.now().isoformat(timespec="seconds"),
    })
    # marcar la escalación abierta más parecida como resuelta
    objetivo = _norm(mision)
    mejor, mejor_sim = None, 0.0
    for esc in manual["escalaciones"]:
        if esc.get("resuelto"):
            continue
        sim = _jaccard(objetivo, _norm(esc.get("mision", "")))
        if sim > mejor_sim:
            mejor, mejor_sim = esc, sim
    if mejor is not None and mejor_sim >= UMBRAL_SIMILITUD:
        mejor["resuelto"] = True
    manual["arreglos"] = manual["arreglos"][-200:]
    _guardar(proyecto, manual)


def como_contexto(recuerdos: list) -> str:
    """Formatea los recuerdos para inyectarlos al prompt del cerebro de código."""
    if not recuerdos:
        return ""
    lineas = ["Lo que ya aprendí en este proyecto (usalo si aplica):"]
    for r in recuerdos:
        if r["tipo"] == "arreglo":
            lineas.append(f"- Cuando pediste «{r['mision']}», la solución correcta fue: {r['solucion']}")
        else:
            lineas.append(f"- Ya resolví «{r['mision']}»: {r.get('resumen','')}")
    return "\n".join(lineas)