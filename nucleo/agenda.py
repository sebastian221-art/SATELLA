"""
nucleo/agenda.py — AUTONOMÍA CONTROLADA: tareas que Satella ejecuta sola, a su hora.

Tres tipos de programación (sin dependencias para los dos primeros):
  - intervalo: "cada 30 minutos", "cada 2 horas".
  - diario:    "todos los días a las 09:00".
  - cron:      expresión cron completa (requiere croniter; opcional).

REGLA DE SEGURIDAD (la hace 'controlada', no suelta):
  La agenda solo DECIDE qué tareas vencieron. La EJECUCIÓN la hace el servidor con
  una compuerta: una tarea automática solo corre acciones VERDES (leer, buscar,
  recordar, avisar). Cualquier acción amarilla/roja (cerrar, mover, borrar, apagar)
  NO se auto-ejecuta: queda anotada y te la pide cuando estés. (Ver `es_intencion_seonsible`.)
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta

log = logging.getLogger("satella.agenda")

_tareas: list = []
_ruta: str = ""
_seq: int = 0

try:
    from croniter import croniter
    _HAY_CRON = True
except Exception:
    _HAY_CRON = False


def inicializar(ruta: str = None):
    global _ruta, _tareas, _seq
    if not ruta:
        try:
            from config import EPISODIOS_FILE
            ruta = os.path.join(os.path.dirname(EPISODIOS_FILE), "agenda.json")
        except Exception:
            ruta = "agenda.json"
    _ruta = ruta
    if os.path.exists(_ruta):
        try:
            with open(_ruta, encoding="utf-8") as f:
                _tareas = json.load(f)
        except Exception:
            _tareas = []
    else:
        _tareas = []
    _seq = max([t.get("id", 0) for t in _tareas], default=0)
    log.info(f"Agenda: {len(_tareas)} tarea(s) programada(s)"
             + ("" if _HAY_CRON else " | croniter no instalado (solo intervalo/diario)"))


def _guardar():
    if not _ruta:
        return
    try:
        os.makedirs(os.path.dirname(_ruta) or ".", exist_ok=True)
        with open(_ruta, "w", encoding="utf-8") as f:
            json.dump(_tareas, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Agenda: error guardando: {e}")


# ── Cálculo de la próxima ejecución ──────────────────────────────────────────
def _proxima(tarea: dict, desde: datetime) -> datetime:
    tipo = tarea["tipo"]
    if tipo == "intervalo":
        return desde + timedelta(seconds=tarea["intervalo_seg"])
    if tipo == "diario":
        hh, mm = tarea["hora"], tarea["min"]
        cand = desde.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= desde:
            cand += timedelta(days=1)
        return cand
    if tipo == "cron" and _HAY_CRON:
        return croniter(tarea["cron"], desde).get_next(datetime)
    # tipo desconocido → muy lejos (no dispara)
    return desde + timedelta(days=3650)


# ── Crear / listar / quitar ──────────────────────────────────────────────────
def agregar(intencion: str, cuando: dict, ahora: datetime = None) -> dict:
    """
    cuando = {"tipo":"intervalo","intervalo_seg":1800}
           | {"tipo":"diario","hora":9,"min":0}
           | {"tipo":"cron","cron":"0 9 * * *"}
    """
    global _seq
    ahora = ahora or datetime.now()
    _seq += 1
    tarea = {"id": _seq, "intencion": intencion.strip(), "activa": True,
             "creado": ahora.isoformat(), "ultima": None, **cuando}
    tarea["proxima"] = _proxima(tarea, ahora).isoformat()
    _tareas.append(tarea)
    _guardar()
    return tarea


def listar() -> list:
    return [t for t in _tareas if t.get("activa")]


def quitar(id_tarea: int) -> bool:
    global _tareas
    n = len(_tareas)
    _tareas = [t for t in _tareas if t.get("id") != id_tarea]
    _guardar()
    return len(_tareas) < n


def describir(tarea: dict) -> str:
    t = tarea["tipo"]
    if t == "intervalo":
        seg = tarea["intervalo_seg"]
        cuando = f"cada {seg // 3600}h" if seg >= 3600 else f"cada {seg // 60} min"
    elif t == "diario":
        cuando = f"todos los días {tarea['hora']:02d}:{tarea['min']:02d}"
    elif t == "cron":
        cuando = f"cron «{tarea.get('cron','')}»"
    else:
        cuando = "?"
    return f"#{tarea['id']} {cuando} → {tarea['intencion']}"


# ── Qué venció (lo llama el servidor periódicamente) ─────────────────────────
def vencidas(ahora: datetime = None) -> list:
    """Devuelve las tareas cuya 'proxima' ya pasó, y reprograma su siguiente corrida."""
    ahora = ahora or datetime.now()
    listas = []
    cambio = False
    for t in _tareas:
        if not t.get("activa"):
            continue
        try:
            prox = datetime.fromisoformat(t["proxima"])
        except Exception:
            continue
        if prox <= ahora:
            listas.append(t)
            t["ultima"] = ahora.isoformat()
            t["proxima"] = _proxima(t, ahora).isoformat()
            cambio = True
    if cambio:
        _guardar()
    return listas


# ── Compuerta de seguridad: ¿esta intención es sensible para auto-ejecutar? ──
_SENSIBLES = ("borr", "elimin", "mov", "apag", "reinici", "cerr", "format",
              "desinstal", "bloque", "shutdown", "delete", "remove")


def es_intencion_sensible(intencion: str) -> bool:
    """True si la intención parece tocar algo amarillo/rojo → NO auto-ejecutar."""
    t = (intencion or "").lower()
    return any(s in t for s in _SENSIBLES)