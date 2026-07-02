"""
nucleo/agentes/gerente.py — EL GERENTE DE AGENTES (el daemon).
─────────────────────────────────────────────────────────────────────────────
Esto hace realidad tu visión original: trabajadores que corren SOLOS en segundo
plano, sin que Satella esté abierta, vigilando tus proyectos y escalando lo que
necesita tu ojo.

El gerente:
  1. Mira el programador: ¿qué agente toca correr ahora? (vencidas)
  2. Despliega cada uno —DESATENDIDO— con la correa del gobernador puesta.
  3. Pasa el reporte por el supervisor (caza alucinaciones).
  4. Deja todo en la BANDEJA, y ESCALA lo que requiere tu atención.

LA REGLA DE ORO DE LA FASE 2 (efecto real):
  Un agente desatendido NUNCA ejecuta algo con efecto real por su cuenta. Si una
  acción necesita confirmación (la correa dice "confirmar") o el agente queda
  bloqueado, NO se hace: se ESCALA a la bandeja para que vos decidas. El daemon
  puede leer, analizar y construir/probar en sandbox solo; tocar el mundo real
  siempre pasa por tu OK. Por eso los agentes programados arrancan en nivel
  lectura: ven y avisan, no actúan sin permiso.
"""
import logging
import time
from datetime import datetime

log = logging.getLogger("satella.gerente")


def _escala(estado: str, dictamen: dict) -> bool:
    """¿Esta corrida requiere el ojo de Sebas?"""
    if estado in ("bloqueado", "pendiente_aprobacion", "listo_con_observaciones"):
        return True
    ver = (dictamen or {}).get("veredicto", "")
    if ver in ("observado", "rechazado"):
        return True
    return False


def correr_una(tarea: dict, ahora: datetime = None) -> dict:
    """Despliega UN agente programado, lo supervisa, lo deja en la bandeja.
    Devuelve un resumen de lo que pasó."""
    from nucleo.agentes import loop, supervisor, plantel, bandeja

    nombre = tarea.get("empleado", "agente")
    mision = tarea.get("mision", "")

    # Cargar la ficha del empleado (su dominio, su nivel). Si no existe, ad-hoc en lectura.
    ficha = plantel.obtener(nombre) or {}
    dominio = ficha.get("dominio", "")
    nivel = ficha.get("nivel_riesgo", "lectura")  # desatendido: arranca en lectura
    contexto = {"dominio": dominio} if dominio else {}
    mision_full = f"En el dominio {dominio}: {mision}" if dominio else mision

    log.info(f"Gerente: corriendo a {nombre} → {mision[:60]}")
    rep = loop.desplegar(mision_full, nombre=nombre, nivel_riesgo=nivel,
                         herramientas=ficha.get("herramientas") or None,
                         contexto=contexto, desatendido=True, avisar=None)

    # Supervisar el informe (caza alucinaciones).
    dictamen = {}
    try:
        if rep.get("sintesis"):
            dictamen = supervisor.revisar(rep)
    except Exception as e:
        log.error(f"Gerente: supervisor falló: {e}")

    estado = rep.get("estado", "?")
    veredicto = dictamen.get("veredicto", "")
    escalar = _escala(estado, dictamen)

    # Armar el cuerpo legible para la bandeja.
    cuerpo = _formatear_corrida(rep, dictamen)
    resumen = (rep.get("sintesis") or rep.get("estado") or "")[:300]

    bandeja.anotar(nombre, mision, estado, veredicto=veredicto,
                   escalado=escalar, resumen=resumen, cuerpo=cuerpo)

    # Registrar la corrida en el historial del empleado.
    try:
        if ficha:
            plantel.registrar_corrida(nombre, mision, estado, resumen)
    except Exception:
        pass

    return {"empleado": nombre, "estado": estado, "veredicto": veredicto,
            "escalado": escalar}


def tick(ahora: datetime = None) -> list:
    """Un latido del daemon: corre todo lo que venció. Devuelve los resúmenes."""
    from nucleo.agentes import programador
    ahora = ahora or datetime.now()
    pendientes = programador.vencidas(ahora)
    if not pendientes:
        return []
    resultados = []
    for tarea in pendientes:
        try:
            resultados.append(correr_una(tarea, ahora))
        except Exception as e:
            log.error(f"Gerente: error corriendo tarea #{tarea.get('id')}: {e}")
    return resultados


def correr(intervalo_seg: int = 60, max_latidos: int = None):
    """El loop del daemon. Late cada `intervalo_seg`. Bloqueante (corre como proceso
    aparte, independiente del servidor web). Ctrl+C para cortar."""
    log.info(f"Gerente: daemon en marcha (latido cada {intervalo_seg}s). Ctrl+C para parar.")
    latidos = 0
    try:
        while True:
            res = tick()
            if res:
                hechas = len(res)
                escaladas = len([r for r in res if r["escalado"]])
                log.info(f"Gerente: {hechas} agente(s) corrieron"
                         + (f" — {escaladas} escalado(s) a tu bandeja" if escaladas else ""))
            latidos += 1
            if max_latidos and latidos >= max_latidos:
                break
            time.sleep(intervalo_seg)
    except KeyboardInterrupt:
        log.info("Gerente: daemon detenido por el usuario.")


def _formatear_corrida(rep: dict, dictamen: dict) -> str:
    out = [f"Misión: {rep.get('mision', '')}",
           f"Estado: {rep.get('estado', '?')}"]
    sint = (rep.get("sintesis") or "").strip()
    if sint:
        out.append(f"Informe: {sint}")
    if dictamen:
        out.append(f"Supervisor: {dictamen.get('veredicto', '?')}")
        for s in dictamen.get("sin_respaldo", [])[:4]:
            out.append(f"  ⚠ sin respaldo: {s}")
    for o in rep.get("observaciones", [])[:4]:
        out.append(f"  • {o}")
    return "\n".join(out)