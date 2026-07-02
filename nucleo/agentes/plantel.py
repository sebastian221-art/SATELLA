"""
nucleo/agentes/plantel.py — EL PLANTEL DE EMPLEADOS.
─────────────────────────────────────────────────────────────────────────────
Hasta la Capa 2, cada agente era de un solo uso: lo desplegabas, hacía la misión
y se iba. Acá nace el PLANTEL: empleados de planta, permanentes, guardados en disco.

Un empleado (ej. Laura) tiene:
  - nombre        → cómo lo llamás ("Laura")
  - dominio       → de qué es dueño ("PSI" / "ERP-PSI")
  - misión        → su trabajo permanente ("vigilar el ERP-PSI y reportar")
  - nivel_riesgo  → hasta dónde puede actuar (arranca en lectura)
  - herramientas  → su caja (vacía = todas las de su nivel)
  - responsabilidades → lista que CRECE con el tiempo
  - historial     → resumen de sus últimas corridas

Lo desplegás por nombre y ya sabe quién es. Sus responsabilidades crecen (hoy vigila
X, mañana también el chatbot nuevo). Es la diferencia entre correr un agente suelto
y tener un equipo.
"""
import json
import logging
import os
import re
from datetime import datetime

log = logging.getLogger("satella.plantel")

_dir = ""
_MAX_HISTORIAL = 20


def inicializar(dir_agentes: str = None):
    global _dir
    if dir_agentes:
        _dir = dir_agentes
    else:
        try:
            from config import DATOS_DIR
            _dir = os.path.join(DATOS_DIR, "agentes")
        except Exception:
            _dir = os.path.join("datos", "agentes")
    try:
        os.makedirs(_dir, exist_ok=True)
    except Exception as e:
        log.error(f"Plantel: no pude crear {_dir}: {e}")
    log.info(f"Plantel: {len(listar())} empleado(s) de planta")


def _slug(nombre: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "", (nombre or "").lower().strip().replace(" ", "_"))
    return s or "agente"


def _ruta(nombre: str) -> str:
    if not _dir:
        inicializar()
    return os.path.join(_dir, _slug(nombre) + ".json")


# ── Alta / baja ──────────────────────────────────────────────────────────────
def contratar(nombre: str, dominio: str = "", mision: str = "",
              nivel_riesgo: str = "lectura", herramientas=None,
              responsabilidades=None) -> dict:
    ficha = {
        "nombre": nombre.strip().capitalize(),
        "dominio": dominio.strip(),
        "mision": (mision or "").strip() or (f"Vigilar {dominio} y reportar lo que encuentre"
                                             if dominio else "Asistir en lo que se le pida"),
        "nivel_riesgo": nivel_riesgo,
        "herramientas": herramientas or [],
        "responsabilidades": responsabilidades or [],
        "creado": datetime.now().isoformat(),
        "historial": [],
    }
    _guardar(ficha)
    log.info(f"Plantel: contratado {ficha['nombre']} (dominio: {dominio or '—'})")
    return ficha


def despedir(nombre: str) -> bool:
    ruta = _ruta(nombre)
    if os.path.exists(ruta):
        try:
            os.remove(ruta)
            return True
        except Exception as e:
            log.error(f"Plantel: no pude despedir {nombre}: {e}")
    return False


# ── Lectura / escritura ──────────────────────────────────────────────────────
def obtener(nombre: str) -> dict:
    ruta = _ruta(nombre)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("nombre"):
            return data
        return None
    except Exception:
        return None


_NO_FICHAS = {"programadas.json", "bandeja.json", "agenda_agentes.json"}


def listar() -> list:
    if not _dir or not os.path.isdir(_dir):
        return []
    out = []
    for nombre in sorted(os.listdir(_dir)):
        if not nombre.endswith(".json") or nombre in _NO_FICHAS:
            continue
        try:
            with open(os.path.join(_dir, nombre), encoding="utf-8") as f:
                data = json.load(f)
            # Solo es ficha de empleado si es un dict con "nombre".
            if isinstance(data, dict) and data.get("nombre"):
                out.append(data)
        except Exception:
            continue
    return out


def _guardar(ficha: dict):
    try:
        with open(_ruta(ficha["nombre"]), "w", encoding="utf-8") as f:
            json.dump(ficha, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Plantel: no pude guardar {ficha.get('nombre')}: {e}")


# ── Crecimiento del empleado ─────────────────────────────────────────────────
def agregar_responsabilidad(nombre: str, responsabilidad: str) -> bool:
    ficha = obtener(nombre)
    if not ficha:
        return False
    responsabilidad = (responsabilidad or "").strip()
    if responsabilidad and responsabilidad not in ficha["responsabilidades"]:
        ficha["responsabilidades"].append(responsabilidad)
        _guardar(ficha)
    return True


def registrar_corrida(nombre: str, mision: str, estado: str, resumen: str = "") -> bool:
    ficha = obtener(nombre)
    if not ficha:
        return False
    ficha.setdefault("historial", []).append({
        "ts": datetime.now().isoformat(),
        "mision": mision[:200], "estado": estado, "resumen": resumen[:300],
    })
    ficha["historial"] = ficha["historial"][-_MAX_HISTORIAL:]
    _guardar(ficha)
    return True