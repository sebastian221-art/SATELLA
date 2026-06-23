"""
nucleo/habilidades/sistema/cerebro.py — INTÉRPRETE de comandos de sistema.
Groq traduce el pedido en lenguaje natural a UNA acción del registro (rápido, ~2s).
Si el pedido no es un comando de sistema, devuelve None y la skill cae a conversación.
"""
import json
import logging

from nucleo.habilidades.python import _llm
from . import acciones

log = logging.getLogger("satella.habilidad.sistema")


def _catalogo() -> str:
    lineas = []
    for nombre, e in acciones.REGISTRO.items():
        args = ", ".join(e["args"]) if e["args"] else "(sin args)"
        lineas.append(f"- {nombre}({args}) [{e['riesgo']}]")
    return "\n".join(lineas)


_PROMPT = """Sos el intérprete de comandos de sistema de Satella. Traducí el pedido del usuario a UNA acción del catálogo, o devolvé null si NO es un comando sobre la PC.

Catálogo de acciones permitidas:
{catalogo}

Mensaje del usuario: "{mensaje}"

Reglas:
- "abrí/abrime X": abrir_app si X es una app (notepad, code, chrome, spotify, calc...), abrir_ruta si es un archivo o carpeta (tiene ruta o extensión).
- volumen: params accion="subir"|"bajar"|"silenciar". multimedia: accion="play_pausa"|"siguiente"|"anterior"|"stop".
- "apagá": apagar. "reiniciá": apagar con params reiniciar=true.
- "borrá/eliminá X": borrar con params ruta=X. "mové X a Y": mover con origen=X, destino=Y.
- "creá carpeta X": crear_carpeta. "cerrá X": cerrar_app. "bloqueá": bloquear.
- info/batería/ram/qué apps: info_sistema o apps_abiertas.
- Si no corresponde a NINGUNA acción del catálogo, devolvé {{"accion": null}}.

Respondé SOLO JSON, sin texto afuera:
{{"accion": "<nombre exacto del catálogo>", "params": {{...}}}}  o  {{"accion": null}}"""


def interpretar(mensaje: str):
    """Devuelve {'accion':str,'params':dict} o None."""
    if not _llm.disponible():
        return None
    try:
        salida = _llm.chat(
            _PROMPT.format(catalogo=_catalogo(), mensaje=mensaje[:300]),
            max_tokens=200, temperature=0.1)
    except Exception as e:
        log.error(f"[SISTEMA] cerebro falló: {e}")
        return None
    if not salida:
        return None
    s = salida.replace("```json", "").replace("```", "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        return None
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return None
    accion = obj.get("accion")
    if not accion or accion not in acciones.REGISTRO:
        return None
    params = obj.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return {"accion": accion, "params": params}