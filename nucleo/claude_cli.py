"""
nucleo/claude_cli.py — Invocador genérico de Claude Code (reusable).
Cualquier habilidad puede pedirle a Claude Code que razone sobre algo y recibir
el texto. Robusto en Windows (claude.cmd vía cmd /c, prompt por stdin para no
romper el quoting). Avisa progreso por nucleo.progreso mientras trabaja.

Distinto de habilidades/python/_claude_code.py (que es específico de GENERAR
código): esto es de propósito general — preguntar y recibir texto.
"""
import os
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

log = logging.getLogger("satella.claude_cli")


def _avisar(texto):
    if progreso is not None:
        progreso.emitir(texto)


def _dirs_npm():
    dirs = []
    if os.environ.get("APPDATA"):
        dirs.append(os.path.join(os.environ["APPDATA"], "npm"))
    if os.environ.get("USERPROFILE"):
        dirs.append(os.path.join(os.environ["USERPROFILE"], "AppData", "Roaming", "npm"))
    dirs.append(r"C:\Program Files\nodejs")
    return dirs


def _buscar_cmd():
    for cand in ("claude.cmd", "claude.exe", "claude"):
        r = shutil.which(cand)
        if r:
            return r
    for d in _dirs_npm():
        c = os.path.join(d, "claude.cmd")
        if os.path.exists(c):
            return c
    return None


def _prefijo():
    exe = _buscar_cmd()
    if not exe:
        return None
    return ["cmd", "/c", exe] if exe.lower().endswith(".cmd") else [exe]


def disponible() -> bool:
    return _prefijo() is not None


def preguntar(prompt: str, allowed_tools: str = "Read", max_turns: int = 8,
              timeout: int = 240, etiqueta: str = "Claude Code",
              fases=None, cwd: str = None) -> dict:
    """
    Le pasa `prompt` a Claude Code (por stdin) y devuelve {ok, texto, costo, turnos}
    o {ok: False, razon}. Avisa progreso mientras trabaja.
    `cwd`: si se da, corre ahí (para que pueda leer archivos de ese proyecto).
    """
    prefijo = _prefijo()
    if not prefijo:
        return {"ok": False, "razon": "No encuentro Claude Code (claude)."}

    fases = fases or ["analizando", "razonando", "armando el informe"]
    tmp = None
    work = cwd
    if not work:
        tmp = tempfile.mkdtemp(prefix="satella_cli_")
        work = tmp

    cmd = prefijo + ["-p", "--output-format", "json",
                     "--allowedTools", allowed_tools, "--max-turns", str(max_turns)]

    _stop = threading.Event()

    def _latido():
        t0 = time.time()
        i = 0
        _avisar(f"{etiqueta} arrancando…")
        while not _stop.wait(5):
            seg = int(time.time() - t0)
            _avisar(f"{etiqueta} {fases[min(i, len(fases)-1)]}… ({seg}s)")
            i += 1

    hilo = threading.Thread(target=_latido, daemon=True)
    hilo.start()
    try:
        proc = subprocess.run(cmd, input=prompt, cwd=work, capture_output=True,
                              text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "razon": f"{etiqueta} se pasó de {timeout}s."}
    except Exception as e:
        return {"ok": False, "razon": f"No pude lanzar {etiqueta}: {e}"}
    finally:
        _stop.set()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    salida = (proc.stdout or "").strip()
    data = None
    try:
        data = json.loads(salida)
    except Exception:
        import re
        m = re.search(r"\{.*\}", salida, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None

    if data is None:
        return {"ok": False, "razon": f"{etiqueta} no devolvió JSON. "
                + (proc.stderr or "").strip()[:200]}
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        return {"ok": False, "razon": f"{etiqueta} reportó error."}

    texto = (data.get("result") or "").strip()
    if not texto:
        return {"ok": False, "razon": f"{etiqueta} devolvió respuesta vacía."}

    return {"ok": True, "texto": texto, "costo": data.get("total_cost_usd"),
            "turnos": data.get("num_turns")}