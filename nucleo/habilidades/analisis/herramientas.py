"""
nucleo/habilidades/analisis/herramientas.py
Analiza una HERRAMIENTA/CLI instalada: verifica que exista en el PATH y corre
SOLO --version y --help (sin shell, con timeout) para describir qué es y sus
opciones. No ejecuta acciones, solo flags informativas.
"""
import shutil
import subprocess


def analizar(cmd):
    if not cmd or not cmd.replace("-", "").replace("_", "").replace(".", "").isalnum():
        return {"ok": False, "error": "Nombre de comando inválido."}
    ruta = shutil.which(cmd)
    if not ruta:
        return {"ok": False, "error": f"'{cmd}' no está instalado o no está en el PATH."}

    salidas = {}
    for flag in ("--version", "--help"):
        try:
            r = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=6,
                               encoding="utf-8", errors="replace")
            salidas[flag] = (r.stdout or r.stderr or "").strip()
        except Exception:
            salidas[flag] = ""

    return {"ok": True, "comando": cmd, "ruta": ruta,
            "version": salidas.get("--version", "")[:200],
            "help": salidas.get("--help", "")[:1800]}


def como_texto(f):
    if not f.get("ok"):
        return f.get("error", "sin datos")
    L = [f"Herramienta: {f['comando']}", f"Ubicación: {f['ruta']}"]
    if f.get("version"):
        L.append(f"Versión: {f['version'].splitlines()[0] if f['version'] else '?'}")
    if f.get("help"):
        L.append("\n[AYUDA (--help, recortada)]\n" + f["help"])
    return "\n".join(L)