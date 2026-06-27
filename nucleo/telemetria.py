"""
nucleo/telemetria.py — EL CUADERNO DE SATELLA.
─────────────────────────────────────────────────────────────────────────────
Registra cada invocación de habilidad: qué skill, en qué modo, cuánto tardó,
cuánto costó (si la skill lo expone), y si salió bien o falló.

Es el "tablero" de Satella: el motor anda igual con o sin esto, pero sin esto
Satella maneja a ciegas — no puede auditarse, no puede predecir su propia carga,
no sabe cuánto gasta. Esta capa es la quilla del auditor, del predictor interno
y del contador de costo.

DISEÑO (deliberado):
  - APPEND-ONLY JSONL: una línea JSON por evento. NUNCA reescribe el archivo
    entero (ese fue el bug de dataset_finetune.json, que cargaba+volcaba todo en
    cada turno → O(n) por mensaje). Acá cada evento es un append O(1).
  - NO INVASIVO: no toca el contrato de habilidades. El registro lo hace un único
    punto de ejecución (registro.ejecutar), no cada skill.
  - NUNCA ROMPE EL FLUJO: registrar() traga cualquier error. Si el cuaderno
    falla, Satella sigue como si nada — la telemetría jamás tumba una respuesta.
  - LECTURA SEPARADA: la agregación (resumen, por_skill, etc.) lee el JSONL solo
    cuando alguien pregunta (el auditor, o vos por chat), no en cada turno.

API de ESCRITURA:
  inicializar(ruta=None)
  registrar(skill, modo, ms, ok, costo=None, error=None, extra=None)

API de LECTURA (para el auditor / contador de costo / chat):
  eventos(limite=None, desde_iso=None)      -> list[dict]
  resumen(desde_iso=None)                    -> dict agregado global
  por_skill(desde_iso=None)                  -> dict {skill: stats}
  mas_usadas(n=5, desde_iso=None)            -> list[(skill, veces)]
  mas_lentas(n=5, desde_iso=None)            -> list[(skill, ms_promedio)]
  fallos_recientes(n=10)                     -> list[dict]
  costo_total(desde_iso=None)                -> float

MANTENIMIENTO (para el futuro job nocturno "sueño"):
  compactar(max_eventos=20000)               -> recorta a los últimos N eventos
"""
import json
import logging
import os
import threading
from collections import defaultdict
from datetime import datetime

log = logging.getLogger("satella.telemetria")

_ruta: str = ""
_lock = threading.Lock()   # los timers de agenda corren en hilos: el append va serializado


# ── Ruta del cuaderno ────────────────────────────────────────────────────────
def _derivar_ruta() -> str:
    """Deriva datos/telemetria.jsonl igual que Coral/HDC derivan los suyos."""
    try:
        from config import EPISODIOS_FILE
        return os.path.join(os.path.dirname(EPISODIOS_FILE), "telemetria.jsonl")
    except Exception:
        try:
            from config import DATOS_DIR
            return os.path.join(DATOS_DIR, "telemetria.jsonl")
        except Exception:
            return "telemetria.jsonl"


def inicializar(ruta: str = None):
    """Fija la ruta del cuaderno. Llamar una vez al arranque (main.py)."""
    global _ruta
    _ruta = ruta or _derivar_ruta()
    # No creamos el archivo todavía: se crea solo en el primer append. Pero sí
    # garantizamos que la carpeta exista, para que el primer registrar() no falle.
    try:
        carpeta = os.path.dirname(_ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
    except Exception as e:
        log.error(f"Telemetría: no pude preparar la carpeta: {e}")
    n = _contar_lineas()
    log.info(f"Telemetría: cuaderno listo | {n} eventos registrados | {_ruta}")


def _ruta_actual() -> str:
    """Devuelve la ruta, derivándola al vuelo si nadie llamó inicializar()."""
    global _ruta
    if not _ruta:
        _ruta = _derivar_ruta()
    return _ruta


# ── ESCRITURA ────────────────────────────────────────────────────────────────
def registrar(skill: str, modo: str, ms: int, ok: bool,
              costo=None, error: str = None, extra: dict = None) -> None:
    """
    Anota un evento en el cuaderno. NUNCA lanza: si algo falla, se calla y sigue.
    Una línea JSON = un evento. Append O(1).
    """
    try:
        evento = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "skill": skill or "?",
            "modo": modo or "?",
            "ms": int(ms) if ms is not None else None,
            "ok": bool(ok),
        }
        if costo is not None:
            try:
                evento["costo"] = round(float(costo), 6)
            except Exception:
                pass
        if error:
            evento["error"] = str(error)[:300]
        if extra:
            try:
                evento["extra"] = extra
            except Exception:
                pass

        linea = json.dumps(evento, ensure_ascii=False)
        ruta = _ruta_actual()
        with _lock:
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
    except Exception as e:
        # La telemetría jamás debe tumbar una respuesta de Satella.
        log.debug(f"Telemetría: no pude registrar ({e})")


# ── LECTURA / AGREGACIÓN ─────────────────────────────────────────────────────
def _contar_lineas() -> int:
    ruta = _ruta_actual()
    if not os.path.exists(ruta):
        return 0
    try:
        with open(ruta, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _leer_eventos() -> list:
    """Lee TODOS los eventos del cuaderno, saltando líneas corruptas."""
    ruta = _ruta_actual()
    if not os.path.exists(ruta):
        return []
    out = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    out.append(json.loads(linea))
                except Exception:
                    continue   # línea corrupta → la ignoramos, no rompemos
    except Exception as e:
        log.error(f"Telemetría: error leyendo cuaderno: {e}")
    return out


def _filtrar_desde(evs: list, desde_iso: str = None) -> list:
    if not desde_iso:
        return evs
    return [e for e in evs if str(e.get("ts", "")) >= desde_iso]


def eventos(limite: int = None, desde_iso: str = None) -> list:
    """Eventos crudos (los más recientes al final). limite = últimos N."""
    evs = _filtrar_desde(_leer_eventos(), desde_iso)
    if limite is not None and limite > 0:
        return evs[-limite:]
    return evs


def _percentil(valores: list, p: float) -> float:
    """Percentil simple (p en [0,1]) sin numpy, para no atar la lectura a numpy."""
    if not valores:
        return 0.0
    s = sorted(valores)
    i = int(round(p * (len(s) - 1)))
    return float(s[i])


def por_skill(desde_iso: str = None) -> dict:
    """
    Estadística agregada por habilidad. Esto es lo que el AUDITOR va a leer:
      {skill: {veces, ok, fallos, ok_rate, ms_promedio, ms_p95, costo_total, ultimo_error}}
    """
    evs = _filtrar_desde(_leer_eventos(), desde_iso)
    acc = defaultdict(lambda: {"veces": 0, "ok": 0, "fallos": 0,
                               "_ms": [], "costo_total": 0.0, "ultimo_error": None})
    for e in evs:
        s = acc[e.get("skill", "?")]
        s["veces"] += 1
        if e.get("ok"):
            s["ok"] += 1
        else:
            s["fallos"] += 1
            if e.get("error"):
                s["ultimo_error"] = e["error"]
        if isinstance(e.get("ms"), (int, float)):
            s["_ms"].append(e["ms"])
        if isinstance(e.get("costo"), (int, float)):
            s["costo_total"] += e["costo"]

    out = {}
    for skill, s in acc.items():
        ms = s["_ms"]
        out[skill] = {
            "veces": s["veces"],
            "ok": s["ok"],
            "fallos": s["fallos"],
            "ok_rate": round(s["ok"] / s["veces"], 3) if s["veces"] else 0.0,
            "ms_promedio": int(sum(ms) / len(ms)) if ms else 0,
            "ms_p95": int(_percentil(ms, 0.95)) if ms else 0,
            "costo_total": round(s["costo_total"], 6),
            "ultimo_error": s["ultimo_error"],
        }
    return out


def resumen(desde_iso: str = None) -> dict:
    """Foto global del cuaderno (para el contador de costo y el chat)."""
    evs = _filtrar_desde(_leer_eventos(), desde_iso)
    total = len(evs)
    ok = sum(1 for e in evs if e.get("ok"))
    costo = sum(e["costo"] for e in evs if isinstance(e.get("costo"), (int, float)))
    ms = [e["ms"] for e in evs if isinstance(e.get("ms"), (int, float))]
    primero = evs[0]["ts"] if evs else None
    ultimo = evs[-1]["ts"] if evs else None
    return {
        "total_eventos": total,
        "ok": ok,
        "fallos": total - ok,
        "ok_rate": round(ok / total, 3) if total else 0.0,
        "costo_total": round(costo, 6),
        "ms_promedio": int(sum(ms) / len(ms)) if ms else 0,
        "ms_p95": int(_percentil(ms, 0.95)) if ms else 0,
        "desde": primero,
        "hasta": ultimo,
        "skills_distintas": len({e.get("skill") for e in evs}),
    }


def mas_usadas(n: int = 5, desde_iso: str = None) -> list:
    ps = por_skill(desde_iso)
    orden = sorted(ps.items(), key=lambda kv: kv[1]["veces"], reverse=True)
    return [(k, v["veces"]) for k, v in orden[:n]]


def mas_lentas(n: int = 5, desde_iso: str = None) -> list:
    ps = por_skill(desde_iso)
    orden = sorted(ps.items(), key=lambda kv: kv[1]["ms_promedio"], reverse=True)
    return [(k, v["ms_promedio"]) for k, v in orden[:n]]


def fallos_recientes(n: int = 10) -> list:
    evs = [e for e in _leer_eventos() if not e.get("ok")]
    return evs[-n:]


def costo_total(desde_iso: str = None) -> float:
    return resumen(desde_iso)["costo_total"]


# ── MANTENIMIENTO (futuro job nocturno) ──────────────────────────────────────
def compactar(max_eventos: int = 20000) -> int:
    """
    Recorta el cuaderno a los últimos `max_eventos` (reescribe una sola vez,
    a propósito — esto NO corre por turno, lo llamará el job nocturno).
    Devuelve cuántos eventos quedaron.
    """
    evs = _leer_eventos()
    if len(evs) <= max_eventos:
        return len(evs)
    recortado = evs[-max_eventos:]
    ruta = _ruta_actual()
    try:
        tmp = ruta + ".tmp"
        with _lock:
            with open(tmp, "w", encoding="utf-8") as f:
                for e in recortado:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            os.replace(tmp, ruta)
        log.info(f"Telemetría: cuaderno compactado a {len(recortado)} eventos")
    except Exception as e:
        log.error(f"Telemetría: error compactando: {e}")
    return len(recortado)