"""
nucleo/habilidades/python/_claude_code.py — Cerebro generador vía Claude Code.
Le pide el código a Claude Code (CLI, headless), que trae calidad frontera y
aplica tu CLAUDE.md global. Devuelve el código como TEXTO; no escribe archivos
(corre read-only en un dir temporal aislado).

Clave en Windows: el prompt se pasa por STDIN (no como argumento). Así el shim
claude.cmd corre por `cmd /c` sin que las comillas ni los saltos de línea del
prompt rompan nada (probado). `-p` sin argumento lee el prompt de stdin.
"""
import os
import re
import json
import time
import shutil
import threading
import tempfile
import logging
import subprocess

try:
    from nucleo import progreso
except Exception:  # pragma: no cover
    progreso = None

log = logging.getLogger("satella.habilidad.python")


def _avisar(texto: str) -> None:
    """Manda un mensaje de progreso al chat (si hay canal). Nunca rompe."""
    if progreso is not None:
        progreso.emitir(texto)

_TIMEOUT = int(os.environ.get("SATELLA_PY_CC_TIMEOUT", "120"))
_MAX_TURNS = "6"


def _dirs_npm():
    dirs = []
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        dirs.append(os.path.join(appdata, "npm"))
    perfil = os.environ.get("USERPROFILE", "")
    if perfil:
        dirs.append(os.path.join(perfil, "AppData", "Roaming", "npm"))
    dirs.append(r"C:\Program Files\nodejs")
    return dirs


def _buscar_cmd():
    """Encuentra el ejecutable de Claude Code (PATH o rutas npm de Windows)."""
    for cand in ("claude.cmd", "claude.exe", "claude"):
        r = shutil.which(cand)
        if r:
            return r
    for d in _dirs_npm():
        c = os.path.join(d, "claude.cmd")
        if os.path.exists(c):
            return c
    return None


def _prefijo_comando():
    """
    Lista-prefijo para lanzar Claude Code:
      - Windows (.cmd) → ['cmd', '/c', '<claude.cmd>']
      - Otro           → ['<claude>']
    None si no se encuentra.
    """
    exe = _buscar_cmd()
    if not exe:
        return None
    if exe.lower().endswith(".cmd"):
        return ["cmd", "/c", exe]
    return [exe]


def disponible() -> bool:
    return _prefijo_comando() is not None


def _extraer_bloque(texto: str, lenguaje: str) -> str:
    if not texto:
        return ""
    m = re.search(r"```(?:[\w+]*)\n(.*?)```", texto, re.DOTALL)
    if m:
        return m.group(1).strip()
    return texto.strip()


def generar_codigo(requerimiento: str, lenguaje: str = "python") -> dict:
    """Pide el código a Claude Code (prompt por stdin). Devuelve {ok, codigo, ...}."""
    prefijo = _prefijo_comando()
    if not prefijo:
        return {"ok": False, "razon": "Claude Code (claude) no está instalado o no lo encuentro."}

    prompt = (
        f"Escribí en {lenguaje} lo siguiente:\n{requerimiento}\n\n"
        f"Devolvé ÚNICAMENTE el código, completo y correcto, en un solo bloque "
        f"```{lenguaje} ... ```. No escribas archivos, no des explicaciones largas. "
        f"Comentarios y nombres en español. Manejá los casos borde."
    )

    # -p SIN argumento → lee el prompt de stdin (esquiva el quoting de cmd.exe).
    tmp = tempfile.mkdtemp(prefix="satella_py_")
    cmd = prefijo + [
        "-p",
        "--output-format", "json",
        "--allowedTools", "Read",
        "--max-turns", _MAX_TURNS,
    ]

    # Latido: mientras Claude Code trabaja (subproceso bloqueante), un hilo avisa
    # al chat cada pocos segundos para que la espera no se vea congelada.
    _stop = threading.Event()

    def _latido():
        t0 = time.time()
        fases = ["pensando la solución", "escribiendo el código",
                 "revisando los casos borde", "afinando los detalles"]
        i = 0
        _avisar("Claude Code arrancando…")
        while not _stop.wait(5):
            seg = int(time.time() - t0)
            fase = fases[min(i, len(fases) - 1)]
            _avisar(f"Claude Code {fase}… ({seg}s)")
            i += 1

    hilo = threading.Thread(target=_latido, daemon=True)
    hilo.start()
    try:
        proc = subprocess.run(
            cmd, input=prompt, cwd=tmp, capture_output=True, text=True,
            timeout=_TIMEOUT, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "razon": f"Claude Code se pasó de {_TIMEOUT}s."}
    except Exception as e:
        return {"ok": False, "razon": f"No pude lanzar Claude Code: {e}"}
    finally:
        _stop.set()
        shutil.rmtree(tmp, ignore_errors=True)

    salida = (proc.stdout or "").strip()
    data = None
    try:
        data = json.loads(salida)
    except Exception:
        m = re.search(r"\{.*\}", salida, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None

    if data is None:
        err = (proc.stderr or "").strip()[:300]
        return {"ok": False, "razon": f"Claude Code no devolvió JSON. {err}"}
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        return {"ok": False, "razon": "Claude Code reportó error."}

    raw = (data.get("result") or "").strip()
    codigo = _extraer_bloque(raw, lenguaje)
    if not codigo:
        return {"ok": False, "razon": "Claude Code no devolvió código."}

    return {"ok": True, "codigo": codigo, "raw": raw,
            "costo": data.get("total_cost_usd"), "turnos": data.get("num_turns")}