"""
nucleo/agentes/bandeja.py — LA BANDEJA DE ENTRADA.
─────────────────────────────────────────────────────────────────────────────
Cuando los agentes corren solos en segundo plano (el daemon), nadie está mirando
la pantalla. Necesitan un lugar donde dejar lo que hicieron y, sobre todo, dónde
ESCALAR lo que requiere tu atención.

La bandeja es eso: un cuaderno append-only (datos/agentes/bandeja.jsonl) donde cada
corrida del daemon deja una entrada. Las marcadas como `escalado=True` son las que
piden tu ojo: el supervisor las observó/rechazó, o el agente quedó bloqueado.

Después, desde el chat, le preguntás a Satella "¿qué hicieron los agentes?" y te
muestra la bandeja, con lo escalado arriba.
"""
import json
import logging
import os
from datetime import datetime

log = logging.getLogger("satella.bandeja")

_ruta = ""


def inicializar(ruta: str = None):
    global _ruta
    if ruta:
        _ruta = ruta
    else:
        try:
            from config import DATOS_DIR
            _ruta = os.path.join(DATOS_DIR, "agentes", "bandeja.jsonl")
        except Exception:
            _ruta = os.path.join("datos", "agentes", "bandeja.jsonl")
    try:
        os.makedirs(os.path.dirname(_ruta) or ".", exist_ok=True)
    except Exception as e:
        log.error(f"Bandeja: no pude preparar {_ruta}: {e}")


def _asegurar():
    if not _ruta:
        inicializar()


def anotar(empleado: str, mision: str, estado: str, veredicto: str = "",
           escalado: bool = False, resumen: str = "", cuerpo: str = "") -> dict:
    _asegurar()
    entrada = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "empleado": empleado, "mision": mision[:200], "estado": estado,
        "veredicto": veredicto, "escalado": escalado,
        "resumen": resumen[:400], "cuerpo": cuerpo[:4000], "leido": False,
    }
    try:
        with open(_ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"Bandeja: no pude anotar: {e}")
    return entrada


def listar(n: int = 20, solo_escalado: bool = False) -> list:
    _asegurar()
    if not os.path.exists(_ruta):
        return []
    filas = []
    try:
        with open(_ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    e = json.loads(linea)
                except Exception:
                    continue
                if solo_escalado and not e.get("escalado"):
                    continue
                filas.append(e)
    except Exception as e:
        log.error(f"Bandeja: no pude leer: {e}")
    return filas[-n:][::-1]  # más recientes primero


def pendientes() -> int:
    """Cuántas entradas escaladas hay (lo que pide tu atención)."""
    return len([e for e in listar(n=500, solo_escalado=True)])


def marcar_leidas():
    """Reescribe la bandeja marcando todo como leído (cuando ya las miraste)."""
    _asegurar()
    if not os.path.exists(_ruta):
        return
    filas = []
    try:
        with open(_ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    e = json.loads(linea)
                    e["leido"] = True
                    filas.append(e)
                except Exception:
                    continue
        with open(_ruta, "w", encoding="utf-8") as f:
            for e in filas:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"Bandeja: no pude marcar leídas: {e}")