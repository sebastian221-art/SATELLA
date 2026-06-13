"""
nucleo/habilidades/mezclador/compositor.py
Convierte un objetivo + plan en el CÓDIGO de una habilidad nueva.

metadata()        → deriva nombre/triggers/descripción de forma DETERMINISTA.
construir_skill() → arma el skill.py por plantilla. La habilidad resultante:
   • marca COMPUESTA = True (el registro la prioriza por encima de las atómicas);
   • dispara SOLO cuando el pedido toca 2+ de sus sub-tareas (detecta por GRUPOS,
     un grupo de palabras por paso) — así no le roba pedidos de una sola parte a
     las habilidades atómicas, y tampoco se autorrutea cuando el planificador
     descompone el pedido en pasos simples;
   • delega en el planificador en runtime (se adapta a variaciones del pedido).
"""
import re

_STOP = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "con",
    "para", "que", "a", "en", "al", "del", "por", "su", "sus", "lo", "le", "me",
    "se", "tu", "mi", "este", "esta", "esto", "ese", "esa", "como", "luego",
    "despues", "después", "primero", "analiza", "analizá", "convertir", "convertí",
    "dame", "decime", "hacé", "hace", "quiero", "necesito",
}


def _palabras_clave(texto: str, limite: int = 4):
    palabras = re.findall(r"[a-záéíóúñ0-9]+", (texto or "").lower())
    contenido = [p for p in palabras if len(p) > 3 and p not in _STOP]
    return list(dict.fromkeys(contenido))[:limite]  # sin duplicados, en orden


def metadata(objetivo: str, nombre_dado: str = None) -> dict:
    contenido = _palabras_clave(objetivo, limite=5)
    nombre = nombre_dado or ("_".join(contenido[:3]) if contenido else "tarea_compuesta")
    nombre = re.sub(r"[^a-z0-9_]", "", nombre.lower()) or "tarea_compuesta"
    triggers = tuple(contenido) or (nombre,)
    descripcion = "Tarea compuesta: " + (objetivo or "").strip()[:120]
    ejemplos = [(objetivo or "").strip()[:120]]
    return {"nombre": nombre, "descripcion": descripcion,
            "ejemplos": ejemplos, "triggers": triggers}


def _grupos(pasos: list, triggers: tuple) -> list:
    """Un grupo de palabras clave por paso. Fallback: los triggers como un grupo."""
    grupos = []
    for p in (pasos or []):
        kws = _palabras_clave(p, limite=4)
        if kws:
            grupos.append(tuple(kws))
    if not grupos:
        grupos = [tuple(triggers)]
    return grupos


def construir_skill(meta: dict, objetivo: str, pasos: list) -> str:
    """Devuelve el código (str) de una habilidad lista para validar y estacionar."""
    grupos = _grupos(pasos, meta["triggers"])
    min_grupos = min(2, len(grupos))  # con 1 paso basta 1 grupo; con 2+ exige 2

    # Encabezado con el plan congelado, como COMENTARIOS (a prueba de comillas).
    cab = "# Habilidad compuesta: " + meta["nombre"] + "\n"
    cab += "# Creada por el mezclador a partir de un plan que funcionó.\n"
    cab += "# Objetivo original: " + (objetivo or "").replace("\n", " ")[:200] + "\n"
    for i, p in enumerate(pasos or [], 1):
        cab += "# Paso " + str(i) + ": " + str(p).replace("\n", " ")[:120] + "\n"

    cuerpo = (
        "from nucleo.habilidades import contrato\n\n"
        "COMPUESTA = True\n"
        "NOMBRE = " + repr(meta["nombre"]) + "\n"
        "DESCRIPCION = " + repr(meta["descripcion"]) + "\n"
        "EJEMPLOS = " + repr(list(meta["ejemplos"])) + "\n"
        "# Un grupo de palabras por sub-tarea; la habilidad dispara solo si el\n"
        "# pedido toca al menos _MIN_GRUPOS sub-tareas distintas.\n"
        "_GRUPOS = " + repr([list(g) for g in grupos]) + "\n"
        "_MIN_GRUPOS = " + repr(min_grupos) + "\n\n\n"
        "def detecta(texto, codigo_adjunto=\"\"):\n"
        "    t = (texto or \"\").lower()\n"
        "    tocados = sum(1 for grupo in _GRUPOS if any(k in t for k in grupo))\n"
        "    return tocados >= _MIN_GRUPOS\n\n\n"
        "def manejar(texto, contexto=None):\n"
        "    # Delega en el planificador: recombina las habilidades necesarias\n"
        "    # en tiempo de ejecución, adaptándose al pedido concreto.\n"
        "    from nucleo.habilidades.planificador import skill as _plan\n"
        "    res = _plan.manejar(texto, contexto)\n"
        "    return contrato.resultado(NOMBRE, \"compuesta\",\n"
        "                              res.get(\"resumen\", \"tarea compuesta\"),\n"
        "                              res.get(\"cuerpo\", \"\"))\n"
    )
    return cab + "\n" + cuerpo