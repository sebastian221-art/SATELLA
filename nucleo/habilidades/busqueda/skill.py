"""
nucleo/habilidades/busqueda/skill.py — BÚSQUEDA EN VIVO.

Le pasa la consulta a Claude Code con sus herramientas de búsqueda web reales
(WebSearch + WebFetch): busca en internet, lee las fuentes, confirma, y responde
lo ACTUAL con criterio y citando de dónde lo sacó — tal como buscaría una persona.

Sin Claude Code no hay búsqueda real (Groq no tiene internet); en ese caso lo dice
honestamente en vez de inventar.
"""
import logging

from nucleo.habilidades import contrato
from . import detector

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None

log = logging.getLogger("satella.habilidad.busqueda")

NOMBRE = "busqueda"
DESCRIPCION = "Busca en internet información actual, lee las fuentes y responde lo último con citas."
EJEMPLOS = [
    "buscá las últimas noticias de inteligencia artificial",
    "qué es lo último de la Champions",
    "averiguá el precio actual del dólar en Colombia",
    "buscá en internet qué modelos nuevos sacó Anthropic",
]


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_busqueda(texto, codigo_adjunto)


def _prompt(consulta: str) -> str:
    return (
        "Sos el módulo de investigación de Satella. Buscá en internet información "
        f"ACTUAL y confiable para responder: «{consulta}».\n\n"
        "Hacé lo siguiente:\n"
        "1. Buscá en la web con WebSearch.\n"
        "2. Abrí las fuentes más confiables y recientes con WebFetch para confirmar.\n"
        "3. Respondé en español rioplatense (voseo), conciso y directo, sin relleno.\n"
        "4. Citá las fuentes (nombre del sitio) de donde sacaste cada dato clave.\n"
        "5. Si las fuentes se contradicen o no hay info confiable, decilo honestamente; "
        "no inventes ni rellenes.\n"
        "6. Si la info es muy reciente o cambiante, aclaralo (ej «al día de hoy…»)."
    )


def manejar(texto: str, contexto: dict = None) -> dict:
    consulta = detector.limpiar_consulta(texto)

    if claude_cli is None or not claude_cli.disponible():
        return contrato.resultado(
            NOMBRE, "busqueda", "no puedo buscar ahora",
            "Para buscar en internet de verdad necesito Claude Code (es el que tiene "
            "acceso a la web). No lo encuentro disponible, así que no te voy a inventar "
            "una respuesta. Revisá que Claude Code esté instalado y logueado.",
            ok=True,
        )

    log.info(f"[BUSCA] consulta: {consulta[:70]}")
    r = claude_cli.preguntar(
        _prompt(consulta),
        allowed_tools="WebSearch,WebFetch",
        max_turns=15, timeout=240,
        etiqueta="Búsqueda en internet",
        fases=["buscando en la web", "leyendo las fuentes", "confirmando los datos",
               "armando la respuesta"],
    )

    if not r.get("ok"):
        return contrato.resultado(
            NOMBRE, "busqueda", "la búsqueda falló",
            "Intenté buscar pero la búsqueda no se completó "
            f"({r.get('razon', 'motivo desconocido')}). Probá de nuevo o reformulá.",
            ok=True,
        )

    cuerpo = r.get("texto", "").strip() or "No encontré información clara sobre eso."
    costo = r.get("costo")
    nota = f"\n\n_(búsqueda en vivo vía Claude Code{f' · ${costo:.4f}' if costo else ''})_"
    return contrato.resultado(NOMBRE, "busqueda",
                              f"busqué en internet: {consulta[:50]}", cuerpo + nota, ok=True)