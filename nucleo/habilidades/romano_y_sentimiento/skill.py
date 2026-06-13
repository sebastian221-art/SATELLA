# Habilidad compuesta: romano_y_sentimiento
# Creada por el mezclador a partir de un plan que funcionó.
# Objetivo original: convertí 50 a romano y después analizá el sentimiento de "esto es genial"
# Paso 1: convertí 50 a romano
# Paso 2: analizá el sentimiento de "esto es genial"

from nucleo.habilidades import contrato

COMPUESTA = True
NOMBRE = 'romano_y_sentimiento'
DESCRIPCION = 'Tarea compuesta: convertí 50 a romano y después analizá el sentimiento de "esto es genial"'
EJEMPLOS = ['convertí 50 a romano y después analizá el sentimiento de "esto es genial"']
# Un grupo de palabras por sub-tarea; la habilidad dispara solo si el
# pedido toca al menos _MIN_GRUPOS sub-tareas distintas.
_GRUPOS = [['romano'], ['sentimiento', 'genial']]
_MIN_GRUPOS = 2


def detecta(texto, codigo_adjunto=""):
    t = (texto or "").lower()
    tocados = sum(1 for grupo in _GRUPOS if any(k in t for k in grupo))
    return tocados >= _MIN_GRUPOS


def manejar(texto, contexto=None):
    # Delega en el planificador: recombina las habilidades necesarias
    # en tiempo de ejecución, adaptándose al pedido concreto.
    from nucleo.habilidades.planificador import skill as _plan
    res = _plan.manejar(texto, contexto)
    return contrato.resultado(NOMBRE, "compuesta",
                              res.get("resumen", "tarea compuesta"),
                              res.get("cuerpo", ""))
