"""
nucleo/habilidades/python/ejecutor.py
Ejecuta código Python para ver su output REAL — lo que ningún LLM puede hacer.
Ahora corre EN EL SANDBOX compartido (nucleo/sandbox.py): aislado en carpeta
temporal, con entorno SIN secretos (no fuga API keys), guardia estática ampliada
(archivos, red, subprocesos, código dinámico) y timeout.

Mantiene la interfaz de siempre: {ok, stdout, stderr, tiempo_ms, bloqueado}.
"""
import time

from nucleo import sandbox

_TIMEOUT = 8
_MAX_OUT = 8000


def ejecutar(codigo: str, timeout: int = _TIMEOUT) -> dict:
    if not codigo or not codigo.strip():
        return {"ok": False, "stdout": "", "stderr": "No hay código.", "tiempo_ms": 0, "bloqueado": False}

    t0 = time.time()
    r = sandbox.ejecutar_seguro(codigo, timeout=timeout)
    ms = int((time.time() - t0) * 1000)

    # No se ejecutó: o no compila, o tiene operaciones riesgosas → "bloqueado"
    if not r.get("ejecutado"):
        razon = r.get("razon", "no ejecutado")
        riesgos = r.get("riesgos") or []
        detalle = razon
        if riesgos:
            detalle = razon + " — " + ", ".join(f"{t}: {d}" for t, d in riesgos[:5])
        return {"ok": False, "stdout": "", "stderr": detalle, "tiempo_ms": ms,
                "bloqueado": True}

    return {
        "ok": bool(r.get("ok")),
        "stdout": (r.get("stdout") or "")[:_MAX_OUT],
        "stderr": (r.get("stderr") or r.get("razon") or "")[:4000],
        "tiempo_ms": ms,
        "bloqueado": False,
    }