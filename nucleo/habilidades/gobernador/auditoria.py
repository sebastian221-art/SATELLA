"""
nucleo/habilidades/gobernador/auditoria.py
Registro de auditoría append-only del Gobernador. Cada evento (evaluación,
confirmación, cambio de modo, kill switch) queda anotado en un .jsonl con
timestamp. Es la "caja negra": permite revisar después qué hizo Satella, cuándo
y con qué permiso. Sólo agrega, nunca reescribe.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("satella.gobernador")

_DIR = Path(__file__).resolve().parents[3] / "datos" / "seguridad"
_LOG = _DIR / "auditoria.jsonl"


def registrar(entrada: dict) -> None:
    """Anota un evento. Nunca lanza: si falla, sólo loguea el error."""
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        fila = {"ts": datetime.now().isoformat(timespec="seconds"), **entrada}
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"[GOB] no se pudo auditar: {e}")


def historial(n: int = 20) -> list:
    """Devuelve las últimas n entradas del registro (las más recientes al final)."""
    if not _LOG.exists():
        return []
    try:
        with open(_LOG, encoding="utf-8") as f:
            lineas = f.readlines()[-n:]
        return [json.loads(l) for l in lineas if l.strip()]
    except Exception as e:
        log.error(f"[GOB] no se pudo leer auditoría: {e}")
        return []