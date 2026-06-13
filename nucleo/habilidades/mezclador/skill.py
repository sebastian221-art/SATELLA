"""
nucleo/habilidades/mezclador/skill.py — El mezclador.

Dos modos:
  componer    → toma un objetivo, usa el PLANIFICADOR para combinar habilidades
                y ejecutarlo, muestra el resultado y recuerda la composición.
  cristalizar → toma la última composición y la CONGELA como una habilidad nueva
                (reusa el validador y el escritor del creador → misma compuerta de
                aprobación). La habilidad nueva delega en el planificador, así se
                adapta a variaciones del pedido.

Flujo típico:
  «mezclá: convertí 50 a romano y analizá el sentimiento de "genial"»
  → muestra el resultado y ofrece congelarlo
  «congelá esto como romano_y_sentimiento»
  → queda en revisión
  «aprobá la habilidad romano_y_sentimiento»  (lo maneja el creador)

Siempre devuelve ok=True: una vez que detecta() disparó, la respuesta es suya.
"""
import logging

from nucleo.habilidades import contrato
from nucleo.habilidades.planificador import (
    planificador as _plan_core,
    ejecutor as _plan_ejec,
    sintetizador as _plan_sint,
)
from nucleo.habilidades.creador import validador as _validador, escritor as _escritor
from . import detector, compositor

log = logging.getLogger("satella.habilidad.mezclador")

NOMBRE = "mezclador"
DESCRIPCION = "Combina varias habilidades para una tarea y la congela como una habilidad nueva reutilizable."
EJEMPLOS = [
    "mezclá: convertí 50 a romano y analizá el sentimiento de 'genial'",
    "congelá esto como romano_y_sentimiento",
    "combiná habilidades para validar un email y después generar un saludo",
]

# Estado por proceso: última composición lista para congelar.
_ultima = {"objetivo": None, "pasos": None}


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_peticion(texto, codigo_adjunto)


def manejar(texto: str, contexto: dict = None) -> dict:
    if detector.modo(texto) == "cristalizar":
        return _cristalizar(texto)
    return _componer(texto, contexto)


# ── Componer ─────────────────────────────────────────────────────────────────
def _componer(texto: str, contexto: dict = None) -> dict:
    objetivo = detector.extraer_objetivo(texto)
    pasos = _plan_core.planificar(objetivo)
    if not pasos:
        return contrato.resultado(NOMBRE, "componer", "no pude componer",
                                  "No pude armar la combinación (¿modelo disponible?).")

    log.info(f"[MEZCLA] {len(pasos)} paso(s) para: {objetivo[:60]}")
    resultados = _plan_ejec.ejecutar_plan(pasos, contexto)
    sintesis = _plan_sint.sintetizar(objetivo, resultados)

    _ultima["objetivo"] = objetivo
    _ultima["pasos"] = pasos

    plan_txt = "\n".join(f"{i}. {p}" for i, p in enumerate(pasos, 1))
    ejec_txt = "\n".join(f"{i}. [{r['skill']}] {r['cuerpo']}"
                         for i, r in enumerate(resultados, 1))
    sugerido = compositor.metadata(objetivo)["nombre"]
    cuerpo = (
        f"**Combinación ({len(pasos)} paso/s):**\n{plan_txt}\n\n"
        f"**Ejecución:**\n{ejec_txt}\n\n"
        f"**Resultado:**\n{sintesis}\n\n"
        f"Si querés que congele este proceso como una habilidad reutilizable, "
        f"decime: «congelá esto como {sugerido}» (o el nombre que prefieras)."
    )
    return contrato.resultado(NOMBRE, "componer",
                              f"composición ejecutada en {len(pasos)} paso(s)", cuerpo)


# ── Cristalizar ──────────────────────────────────────────────────────────────
def _cristalizar(texto: str) -> dict:
    if not _ultima["objetivo"]:
        return contrato.resultado(NOMBRE, "cristalizar", "nada para congelar",
                                  "No tengo una composición reciente. Primero hacé "
                                  "«mezclá: <lo que querés>» y después la congelo.")

    nombre_dado = detector.extraer_nombre(texto)
    meta = compositor.metadata(_ultima["objetivo"], nombre_dado)
    codigo = compositor.construir_skill(meta, _ultima["objetivo"], _ultima["pasos"])

    ok, problema = _validador.validar(codigo)
    if not ok:
        return contrato.resultado(NOMBRE, "cristalizar", "no pasó validación",
                                  f"Generé la habilidad compuesta pero no pasó la validación: {problema}")

    _escritor.estacionar(meta["nombre"], codigo)
    log.info(f"[MEZCLA] habilidad compuesta '{meta['nombre']}' estacionada en revisión")
    cuerpo = (
        f"Congelé la combinación como la habilidad **{meta['nombre']}** y pasó la "
        f"validación. Está EN REVISIÓN: no se activa hasta que la apruebes.\n\n"
        f"Dispara con: {', '.join(meta['triggers'])}.\n\n"
        f"Para activarla decime: «aprobá la habilidad {meta['nombre']}»."
    )
    return contrato.resultado(NOMBRE, "cristalizar",
                              f"habilidad {meta['nombre']} en revisión", cuerpo)