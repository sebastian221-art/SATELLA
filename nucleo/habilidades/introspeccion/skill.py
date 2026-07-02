"""
nucleo/habilidades/introspeccion/skill.py — INTROSPECCIÓN.
─────────────────────────────────────────────────────────────────────────────
La herramienta con la que Satella (y sus agentes) se LEEN A SÍ MISMOS. Nació de
un hueco que el agente Laura detectó sola: podía escribir en la memoria pero no
consultarla, así que sus informes decían "infiero" en vez de "confirmo".

Tres cosas, todas de SOLO LECTURA (sin efecto en el mundo):
  - consultar la memoria Coral: "¿qué sé de ERP-PSI?" → trae conceptos y relaciones
  - listar las habilidades activas: "¿qué herramientas tengo?"
  - ver el estado real: tamaño de la memoria, habilidades, salud general

Para un agente, esto convierte "probablemente exista una tabla X" en "en mi memoria
tengo ERP-PSI conectado con facturación, MySQL, PM2…". Confirma, no adivina.
"""
import logging

from nucleo.habilidades import contrato

log = logging.getLogger("satella.habilidad.introspeccion")

NOMBRE = "introspeccion"
DESCRIPCION = ("Lee la memoria de Satella (Coral) y su estado interno: consultá qué sabe "
               "de un tema, listá las habilidades activas, o pedí su estado general. "
               "Solo lectura — sirve para CONFIRMAR datos reales en vez de inferir.")
EJEMPLOS = [
    "qué sabés de ERP-PSI",
    "consultá tu memoria sobre Satella",
    "qué habilidades tenés activas",
    "mostrame tu estado interno",
]

_T_SKILLS = ("qué habilidades", "que habilidades", "tus habilidades", "tus skills",
             "qué herramientas", "que herramientas", "listá las habilidades",
             "lista las habilidades", "listá tus", "qué skills", "que skills")
_T_ESTADO = ("tu estado interno", "estado del sistema", "estado interno", "cómo estás por dentro",
             "tu salud", "salud del sistema", "estado general", "tu estado general")
_T_MEMORIA = ("qué sé de", "que se de", "qué sabés de", "que sabes de", "qué sabes de",
              "consultá tu memoria", "consulta tu memoria", "revisá la memoria",
              "revisa la memoria", "buscá en tu memoria", "busca en tu memoria",
              "en tu memoria", "en coral", "tu memoria sobre", "memoria coral",
              "qué tenés sobre", "que tenes sobre", "qué recordás de", "que recordas de")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    return (any(k in t for k in _T_SKILLS)
            or any(k in t for k in _T_ESTADO)
            or any(k in t for k in _T_MEMORIA))


def manejar(texto: str, contexto: dict = None) -> dict:
    t = (texto or "").lower()
    if any(k in t for k in _T_SKILLS):
        return _listar_habilidades()
    if any(k in t for k in _T_ESTADO):
        return _estado_interno()
    # por defecto: consulta a la memoria (lo que más usan los agentes).
    return _consultar_memoria(texto)


# ── Consultar la memoria Coral ───────────────────────────────────────────────
def _limpiar_consulta(texto: str) -> str:
    """Saca las muletillas de introspección para quedarse con el TEMA a buscar."""
    t = (texto or "").strip()
    bajas = t.lower()
    for frase in ("qué sé de", "que se de", "qué sabés de", "que sabes de", "qué sabes de",
                  "consultá tu memoria sobre", "consulta tu memoria sobre",
                  "consultá tu memoria", "consulta tu memoria",
                  "revisá la memoria sobre", "revisa la memoria sobre",
                  "revisá la memoria", "revisa la memoria",
                  "buscá en tu memoria", "busca en tu memoria",
                  "qué tenés sobre", "que tenes sobre", "qué recordás de", "que recordas de",
                  "tu memoria sobre", "en tu memoria", "en coral", "memoria coral"):
        idx = bajas.find(frase)
        if idx != -1:
            return t[idx + len(frase):].strip(" :,.¿?")
    return t.strip(" :,.¿?")


def _consultar_memoria(texto: str) -> dict:
    tema = _limpiar_consulta(texto)
    try:
        from nucleo import coral
    except Exception:
        return contrato.resultado(NOMBRE, "memoria", "no tengo memoria disponible",
                                  "No pude acceder a Coral.", ok=True)
    if not tema:
        st = coral.stats()
        return contrato.resultado(
            NOMBRE, "memoria", "memoria sin tema",
            f"Mi memoria tiene {st['conceptos']} conceptos y {st['relaciones']} relaciones. "
            f"Preguntame por un tema concreto, ej: «¿qué sé de ERP-PSI?».", ok=True)

    try:
        recuerdo = coral.recordar(tema)
    except Exception as e:
        return contrato.resultado(NOMBRE, "memoria", "error consultando memoria",
                                  f"No pude consultar la memoria: {e}", ok=True)

    if not recuerdo.get("semillas"):
        return contrato.resultado(
            NOMBRE, "memoria", f"sin memoria de «{tema}»",
            f"No tengo nada conectado a «{tema}» en mi memoria todavía.", ok=True)

    cuerpo = coral.como_texto(recuerdo)
    resumen = f"memoria sobre «{tema}»: {len(recuerdo['semillas'])} concepto(s)"
    return contrato.resultado(NOMBRE, "memoria", resumen, cuerpo or "(sin detalle)", ok=True)


# ── Listar habilidades ───────────────────────────────────────────────────────
def _listar_habilidades() -> dict:
    try:
        from nucleo.habilidades import registro
        mods = registro.habilidades()
    except Exception as e:
        return contrato.resultado(NOMBRE, "habilidades", "no pude listar",
                                  f"No pude listar las habilidades: {e}", ok=True)
    lineas = []
    for m in mods:
        nombre = getattr(m, "NOMBRE", "?")
        desc = (getattr(m, "DESCRIPCION", "") or "").strip()
        lineas.append(f"- {nombre}: {desc[:90]}" if desc else f"- {nombre}")
    cuerpo = f"Tengo {len(mods)} habilidades activas:\n" + "\n".join(lineas)
    return contrato.resultado(NOMBRE, "habilidades",
                              f"{len(mods)} habilidades activas", cuerpo, ok=True)


# ── Estado interno ───────────────────────────────────────────────────────────
def _estado_interno() -> dict:
    partes = []
    try:
        from nucleo import coral
        st = coral.stats()
        partes.append(f"Memoria (Coral): {st['conceptos']} conceptos, {st['relaciones']} relaciones")
    except Exception:
        partes.append("Memoria (Coral): no disponible")
    try:
        from nucleo.habilidades import registro
        partes.append(f"Habilidades activas: {len(registro.habilidades())}")
    except Exception:
        pass
    try:
        from nucleo import telemetria
        r = telemetria.resumen()
        if isinstance(r, dict):
            tot = r.get("total") or r.get("eventos") or r.get("invocaciones")
            if tot:
                partes.append(f"Trabajos registrados en telemetría: {tot}")
    except Exception:
        pass
    cuerpo = "Estado interno de Satella:\n- " + "\n- ".join(partes)
    return contrato.resultado(NOMBRE, "estado", "estado interno", cuerpo, ok=True)