"""
nucleo/habilidades/agenda/skill.py — AGENDA (autonomía controlada).

Permite a Sebas programar tareas en lenguaje natural ("recordame X cada hora",
"todos los días a las 9 dame el resumen"). Groq interpreta el CUÁNDO y el QUÉ, y
las registra en nucleo/agenda.py. El servidor las dispara a su hora.

Seguridad: las tareas sensibles (borrar/apagar/mover...) NO se auto-ejecutan; el
servidor las deja para confirmar. Acá solo se programan.
"""
import json
import logging
import re

from nucleo.habilidades import contrato
from nucleo import agenda
from nucleo.habilidades.python import _llm

log = logging.getLogger("satella.habilidad.agenda")

NOMBRE = "agenda"
DESCRIPCION = "Programa tareas y recordatorios que Satella ejecuta sola a su hora (autonomía controlada)."
EJEMPLOS = [
    "recordame tomar agua cada hora",
    "todos los días a las 9 dame el resumen del día",
    "qué tareas tengo agendadas",
]

_CREAR = ("recordame", "recuérdame", "recuerdame", "recordá", "recorda ", "avisame",
          "avísame", "avisá", "agendá", "agenda ", "agendame", "programá", "programa ",
          "programame", "cada hora", "cada día", "cada dia", "todos los días",
          "todos los dias", "cada mañana", "cada noche")
_LISTAR = ("qué tareas", "que tareas", "mis tareas", "listá las tareas", "lista las tareas",
           "tareas agendadas", "qué tengo agendado", "que tengo agendado")
_QUITAR = ("borrá la tarea", "borra la tarea", "quitá la tarea", "quita la tarea",
           "eliminá la tarea", "elimina la tarea", "cancelá la tarea", "cancela la tarea")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    if any(p in t for p in _LISTAR + _QUITAR):
        return True
    if any(p in t for p in _CREAR):
        return True
    # "cada N minutos/horas"
    if re.search(r"cada\s+\d+\s*(min|minuto|hora)", t):
        return True
    return False


_PROMPT = """Sebas quiere programar una tarea para que Satella la haga sola. Extraé QUÉ hacer y CUÁNDO.

Mensaje: "{mensaje}"

Respondé SOLO JSON:
{{"intencion": "<qué hacer, SIN las palabras de tiempo; ej 'recordarte tomar agua', 'darte el resumen del día'>",
 "cuando": <uno de estos formatos:
    {{"tipo":"intervalo","intervalo_seg":<segundos>}}        para 'cada N minutos/horas'
    {{"tipo":"diario","hora":<0-23>,"min":<0-59>}}           para 'todos los días a las HH:MM'
 >}}

Ejemplos:
- "recordame tomar agua cada hora" → {{"intencion":"recordarte tomar agua","cuando":{{"tipo":"intervalo","intervalo_seg":3600}}}}
- "todos los días a las 9 dame el resumen" → {{"intencion":"darte el resumen del día","cuando":{{"tipo":"diario","hora":9,"min":0}}}}"""


def _parsear(mensaje: str):
    if not _llm.disponible():
        return None
    try:
        salida = _llm.chat(_PROMPT.format(mensaje=mensaje[:300]), max_tokens=200, temperature=0.1)
    except Exception:
        return None
    if not salida:
        return None
    s = salida.replace("```json", "").replace("```", "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        return None
    try:
        obj = json.loads(s[i:j + 1])
        if obj.get("intencion") and isinstance(obj.get("cuando"), dict):
            return obj
    except Exception:
        return None
    return None


def manejar(texto: str, contexto: dict = None) -> dict:
    t = (texto or "").lower()

    # Listar
    if any(p in t for p in _LISTAR):
        tareas = agenda.listar()
        if not tareas:
            return contrato.resultado(NOMBRE, "listar", "sin tareas",
                                      "No tenés ninguna tarea agendada todavía.")
        cuerpo = "Tareas que tenés programadas:\n" + "\n".join(agenda.describir(x) for x in tareas)
        return contrato.resultado(NOMBRE, "listar", f"{len(tareas)} tarea(s)", cuerpo)

    # Quitar
    if any(p in t for p in _QUITAR):
        m = re.search(r"\b(\d+)\b", t)
        if m and agenda.quitar(int(m.group(1))):
            return contrato.resultado(NOMBRE, "quitar", "tarea quitada",
                                      f"Listo, borré la tarea #{m.group(1)}.")
        return contrato.resultado(NOMBRE, "quitar", "no encontrada",
                                  "No encontré esa tarea. Decime 'qué tareas tengo' para ver los números.")

    # Crear
    parsed = _parsear(texto)
    if not parsed:
        return {"ok": False}
    tarea = agenda.agregar(parsed["intencion"], parsed["cuando"])
    aviso = ""
    if agenda.es_intencion_sensible(parsed["intencion"]):
        aviso = ("\n\n⚠️ Ojo: es una acción delicada. A su hora NO la voy a ejecutar sola — "
                 "te la voy a recordar para que me la confirmes en el momento.")
    return contrato.resultado(NOMBRE, "agendar", "tarea programada",
                              f"Agendado: {agenda.describir(tarea)}.{aviso}")