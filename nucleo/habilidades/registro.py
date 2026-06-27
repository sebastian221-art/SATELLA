"""
nucleo/habilidades/registro.py
─────────────────────────────────────────────────────────────────────────────
Registro de habilidades con AUTODESCUBRIMIENTO.

Escanea las carpetas de nucleo/habilidades/, importa cada skill.py, lo valida
contra el contrato (contrato.validar) y, si pasa, lo activa. Las carpetas que
empiezan con "_" (ej: _pendientes) o "." se ignoran — ahí viven las habilidades
que el creador dejó EN REVISIÓN, que no entran hasta que las aprobás.

Sumar una habilidad nueva ya no requiere tocar este archivo: alcanza con que
exista la carpeta con un skill.py válido. recargar() las relee en caliente.
"""
import importlib
import logging
import os
import time

from nucleo.habilidades import contrato

log = logging.getLogger("satella.habilidades")

_PAQUETE = "nucleo.habilidades"
# Orden de prioridad: las más específicas / meta primero. El resto va después.
# 'agente_cc' (Claude Code) va ANTES que 'agente_codigo': cuando decís explícito
# "agente cc" / "claude code", lo toma el agente nuevo (Claude Code). Como su
# detecta() solo dispara con esos triggers explícitos, NO le roba las misiones
# normales al viejo: un "agente, en X: ..." sin "cc" sigue yendo a 'agente_codigo'.
# 'agente_codigo' va ANTES que 'copia', 'analisis' y 'python': una MISIÓN sobre
# un proyecto (o un "cloná …") la toma el agente, no el analizador ni la skill
# de código suelta. Un snippet suelto ("escribime una función") sigue yendo a 'python'.
_PRIORIDAD = ["gobernador", "navegador", "creador", "mezclador", "planificador",
              "agente_cc", "agente_codigo", "copia", "analisis", "sistema", "agenda",
              "telemetria", "busqueda", "python"]

_SKILLS = []


def _carpetas_habilidades():
    import nucleo.habilidades as paquete
    base = os.path.dirname(paquete.__file__)
    for nombre in sorted(os.listdir(base)):
        ruta = os.path.join(base, nombre)
        if not os.path.isdir(ruta):
            continue
        if nombre.startswith("_") or nombre.startswith("."):
            continue
        if not os.path.exists(os.path.join(ruta, "skill.py")):
            continue
        yield nombre


def _descubrir():
    skills = []
    for nombre in _carpetas_habilidades():
        try:
            mod = importlib.import_module(f"{_PAQUETE}.{nombre}.skill")
        except Exception as e:
            log.error(f"[HAB] no pude importar '{nombre}': {e}")
            continue
        ok, problemas = contrato.validar(mod)
        if not ok:
            log.error(f"[HAB] '{nombre}' no cumple el contrato: {problemas}")
            continue
        skills.append(mod)

    def clave(m):
        n = getattr(m, "NOMBRE", "")
        if n in _PRIORIDAD:
            return _PRIORIDAD.index(n)
        # Las habilidades compuestas (creadas por el mezclador) van DESPUÉS de las
        # meta pero ANTES que las atómicas: cuando reclaman un pedido multi-parte,
        # le ganan a una habilidad atómica que solo cubriría una parte.
        if getattr(m, "COMPUESTA", False):
            return len(_PRIORIDAD)
        return len(_PRIORIDAD) + 1

    skills.sort(key=clave)
    return skills


def recargar():
    """Relee todas las habilidades (útil tras aprobar una nueva)."""
    global _SKILLS
    importlib.invalidate_caches()
    _SKILLS = _descubrir()
    nombres = [getattr(s, "NOMBRE", "?") for s in _SKILLS]
    log.info(f"[HAB] {len(_SKILLS)} habilidades activas: {nombres}")
    return _SKILLS


def habilidades() -> list:
    return list(_SKILLS)


def detectar_skill(texto: str, codigo_adjunto: str = ""):
    """Devuelve la primera habilidad que reclame el mensaje, o None."""
    for s in _SKILLS:
        try:
            if s.detecta(texto, codigo_adjunto):
                return s
        except Exception as e:
            log.error(f"[HAB] {getattr(s, 'NOMBRE', '?')} detecta() falló: {e}")
    return None


def ejecutar(skill, texto: str, contexto: dict = None):
    """
    ÚNICO PUNTO DE EJECUCIÓN de una habilidad. Invoca manejar() midiendo el tiempo
    y dejando el evento en el cuaderno (telemetría), sin que la skill se entere.

    Tanto generacion.py como el ejecutor del planificador pasan por acá: así TODA
    invocación de habilidad queda registrada en un solo lugar, sin tocar el contrato.

    El costo se lee del resultado SOLO si la skill lo expone (clave opcional 'costo');
    las skills que no la traen no se ven afectadas — el costo queda en None.

    Propaga la excepción si manejar() falla (para no cambiar el comportamiento previo:
    generacion.py la atrapa y cae a conversación). El evento de fallo se registra
    igual en el finally, ANTES de propagar.
    """
    nombre = getattr(skill, "NOMBRE", "?")
    t0 = time.perf_counter()
    res = None
    error = None
    try:
        res = skill.manejar(texto, contexto)
        return res
    except Exception as e:
        error = str(e)
        raise
    finally:
        ms = int((time.perf_counter() - t0) * 1000)
        ok = bool(res and isinstance(res, dict) and res.get("ok"))
        modo = (res.get("modo") if isinstance(res, dict) else None) or "?"
        costo = res.get("costo") if isinstance(res, dict) else None
        try:
            from nucleo import telemetria
            telemetria.registrar(nombre, modo, ms, ok, costo=costo, error=error)
        except Exception:
            pass


# Descubrimiento inicial al importar el módulo.
recargar()