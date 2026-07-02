"""
nucleo/agentes/programador.py — LA AGENDA DE LOS AGENTES.
─────────────────────────────────────────────────────────────────────────────
La agenda normal (nucleo/agenda.py) programa intenciones conversacionales. Esto
es distinto: programa EMPLEADOS para que corran solos. Cada entrada dice qué
empleado, con qué misión, y cada cuánto.

Reusa el mismo modelo de tiempo de la agenda (intervalo / diario / cron) para no
duplicar la lógica de croniter. El daemon (gerente.py) consulta `vencidas()` y
despliega lo que toca.

Ejemplo: "programá a Laura para que revise PSI todos los días a las 9".
"""
import json
import logging
import os
from datetime import datetime, timedelta

log = logging.getLogger("satella.programador")

try:
    from croniter import croniter
    _HAY_CRON = True
except Exception:
    _HAY_CRON = False

_ruta = ""
_tareas = []
_seq = 0


def inicializar(ruta: str = None):
    global _ruta, _tareas, _seq
    if ruta:
        _ruta = ruta
    else:
        try:
            from config import DATOS_DIR
            _ruta = os.path.join(DATOS_DIR, "agentes", "programadas.json")
        except Exception:
            _ruta = os.path.join("datos", "agentes", "programadas.json")
    try:
        os.makedirs(os.path.dirname(_ruta) or ".", exist_ok=True)
    except Exception:
        pass
    _tareas = []
    _seq = 0
    if os.path.exists(_ruta):
        try:
            with open(_ruta, encoding="utf-8") as f:
                _tareas = json.load(f)
            _seq = max([t.get("id", 0) for t in _tareas], default=0)
        except Exception as e:
            log.error(f"Programador: no pude leer {_ruta}: {e}")
    log.info(f"Programador: {len(listar())} agente(s) programado(s)"
             + ("" if _HAY_CRON else " | croniter no instalado (solo intervalo/diario)"))


def _guardar():
    try:
        with open(_ruta, "w", encoding="utf-8") as f:
            json.dump(_tareas, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Programador: error guardando: {e}")


def _proxima(tarea: dict, desde: datetime) -> datetime:
    tipo = tarea.get("tipo")
    if tipo == "intervalo":
        return desde + timedelta(seconds=tarea["intervalo_seg"])
    if tipo == "diario":
        cand = desde.replace(hour=tarea["hora"], minute=tarea["min"],
                             second=0, microsecond=0)
        if cand <= desde:
            cand += timedelta(days=1)
        return cand
    if tipo == "cron" and _HAY_CRON:
        return croniter(tarea["cron"], desde).get_next(datetime)
    return desde + timedelta(days=3650)  # tipo desconocido → no dispara


def programar(empleado: str, mision: str, cuando: dict, ahora: datetime = None) -> dict:
    """cuando = {"tipo":"intervalo","intervalo_seg":3600}
              | {"tipo":"diario","hora":9,"min":0}
              | {"tipo":"cron","cron":"0 9 * * *"}"""
    global _seq
    ahora = ahora or datetime.now()
    _seq += 1
    tarea = {"id": _seq, "empleado": empleado, "mision": mision.strip(),
             "activa": True, "creado": ahora.isoformat(), "ultima": None,
             "corridas": 0, **cuando}
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


def describir(t: dict) -> str:
    tipo = t.get("tipo")
    if tipo == "intervalo":
        seg = t["intervalo_seg"]
        cuando = f"cada {seg // 3600}h" if seg >= 3600 else f"cada {seg // 60} min"
    elif tipo == "diario":
        cuando = f"todos los días {t['hora']:02d}:{t['min']:02d}"
    elif tipo == "cron":
        cuando = f"cron «{t.get('cron', '')}»"
    else:
        cuando = "?"
    return f"#{t['id']} {t['empleado']} — {cuando} → {t['mision'][:60]}"


def vencidas(ahora: datetime = None) -> list:
    """Tareas cuya 'proxima' ya pasó. Reprograma la siguiente corrida."""
    ahora = ahora or datetime.now()
    listas, cambio = [], False
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
            t["corridas"] = t.get("corridas", 0) + 1
            t["proxima"] = _proxima(t, ahora).isoformat()
            cambio = True
    if cambio:
        _guardar()
    return listas