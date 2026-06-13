"""
nucleo/habilidades/creador/skill.py — Creador de habilidades.

Genera habilidades nuevas a partir de una descripción, las valida en aislamiento
y las deja EN REVISIÓN. El sistema NO activa código que se escribió a sí mismo
hasta que vos lo aprobás explícitamente.

IMPORTANTE: el creador SIEMPRE devuelve ok=True una vez que detecta() disparó,
porque la respuesta (aunque sea "no encontré ese nombre") es SUYA y tenés que
verla. Si devolviera ok=False, generacion.py la descartaría y caería a la
conversación, que inventaría una respuesta. Ese era el bug.

Modos:
  crear   → "creame una habilidad que ..."
  aprobar → "aprobá la habilidad <nombre>"  (tolerante: matchea por aproximación)
  listar  → "qué habilidades tenés" / "mostrá las pendientes"
"""
import logging

from nucleo.habilidades import contrato
from . import detector, generador, validador, escritor

log = logging.getLogger("satella.habilidad.creador")

NOMBRE = "creador"
DESCRIPCION = "Crea habilidades nuevas para Satella a partir de una descripción."
EJEMPLOS = [
    "creame una habilidad que valide emails",
    "aprobá la habilidad validador_email",
    "qué habilidades tenés en revisión",
]


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    return detector.es_peticion(texto, codigo_adjunto)


def manejar(texto: str, contexto: dict = None) -> dict:
    m = detector.modo(texto)
    if m == "aprobar":
        return _aprobar(texto)
    if m == "listar":
        return _listar()
    return _crear(texto)


# ── Crear ───────────────────────────────────────────────────────────────────
def _crear(texto: str) -> dict:
    spec = detector.extraer_spec(texto)
    if not spec:
        return contrato.resultado(NOMBRE, "crear", "sin descripción",
                                  "Decime qué tiene que hacer la habilidad.")

    gen = generador.generar(spec)
    if not gen.get("ok"):
        return contrato.resultado(NOMBRE, "crear", "no se pudo generar",
                                  "No pude generar la habilidad (¿modelo de código disponible?).")

    codigo, nombre = gen["codigo"], gen["nombre"]

    ok, problema = validador.validar(codigo)
    if not ok:  # un intento de corrección
        nuevo = generador.refinar(spec, codigo, problema)
        ok2, problema2 = validador.validar(nuevo)
        if ok2:
            codigo, ok = nuevo, True
        else:
            problema = problema2

    if not ok:
        return contrato.resultado(NOMBRE, "crear", "no pasó validación",
                                  f"Generé la habilidad pero no pasó la validación: {problema}")

    escritor.estacionar(nombre, codigo)
    log.info(f"[CREADOR] habilidad '{nombre}' estacionada en revisión")
    cuerpo = (
        f"Creé la habilidad **{nombre}** y pasó la validación (sintaxis + smoke test aislado). "
        f"Está EN REVISIÓN: no se activa hasta que la apruebes.\n\n"
        f"```python\n{codigo}\n```\n\n"
        f"Para activarla decime: «aprobá la habilidad {nombre}»."
    )
    return contrato.resultado(NOMBRE, "crear", f"habilidad {nombre} en revisión", cuerpo)


# ── Aprobar (tolerante al nombre) ────────────────────────────────────────────
def _resolver(pedido: str, pendientes: list):
    """Encuentra qué habilidad en revisión quiso decir el usuario."""
    if not pendientes:
        return None
    p = (pedido or "").lower()
    # 1) match exacto
    for nombre in pendientes:
        if nombre.lower() == p:
            return nombre
    # 2) coincidencia parcial en cualquier dirección (numeros_romanos ↔ romano)
    if p:
        for nombre in pendientes:
            n = nombre.lower()
            if n in p or p in n:
                return nombre
    # 3) si hay una sola en revisión, es esa
    if len(pendientes) == 1:
        return pendientes[0]
    return None


def _aprobar(texto: str) -> dict:
    pedido = detector.extraer_nombre_aprobar(texto)
    pendientes = escritor.listar_pendientes()

    if not pendientes:
        return contrato.resultado(NOMBRE, "aprobar", "nada en revisión",
                                  "No hay ninguna habilidad en revisión para aprobar.")

    nombre = _resolver(pedido, pendientes)
    if not nombre:
        return contrato.resultado(NOMBRE, "aprobar", "no encontré esa habilidad",
                                  f"No encontré una habilidad parecida a «{pedido}». "
                                  f"En revisión tengo: {', '.join(pendientes)}. ¿Cuál aprobás?")

    ok, info = escritor.aprobar(nombre)
    if not ok:
        return contrato.resultado(NOMBRE, "aprobar", "no se aprobó", info)

    try:
        from nucleo.habilidades import registro
        registro.recargar()
    except Exception as e:
        log.error(f"[CREADOR] recargar registro falló: {e}")

    log.info(f"[CREADOR] habilidad '{nombre}' activada")
    return contrato.resultado(NOMBRE, "aprobar", f"habilidad {nombre} activada",
                              f"Listo, activé la habilidad **{nombre}**. Ya podés usarla.")


# ── Listar ───────────────────────────────────────────────────────────────────
def _listar() -> dict:
    pendientes = escritor.listar_pendientes()
    try:
        from nucleo.habilidades import registro
        activas = [getattr(s, "NOMBRE", "?") for s in registro.habilidades()]
    except Exception:
        activas = []
    cuerpo = "Habilidades activas: " + (", ".join(activas) or "ninguna") + "."
    if pendientes:
        cuerpo += "\nEn revisión (sin aprobar): " + ", ".join(pendientes) + "."
    return contrato.resultado(NOMBRE, "listar", "estado de habilidades", cuerpo)