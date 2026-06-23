"""
nucleo/habilidades/planificador/ejecutor.py
Ejecuta el plan paso a paso, con DOS capacidades:

  FLUJO DE DATOS: cada paso recibe los resultados de los pasos anteriores.
  RE-PLANIFICACIÓN ADAPTATIVA: si un paso FALLA, observa el fallo y replanifica
  los pasos restantes para recuperarse (otra estrategia), en vez de seguir ciego.

Rutea cada paso a la mejor habilidad (NUNCA al planificador — anti-recursión) o,
si ninguna lo reclama, lo resuelve con el modelo.
"""
import logging

from nucleo.habilidades.python import _llm

log = logging.getLogger("satella.habilidad.planificador")

_MAX_TOTAL = 10  # techo duro de pasos ejecutados (con replanificación incluida)


def _rutear(paso: str):
    from nucleo.habilidades import registro
    skills = [s for s in registro.habilidades()
              if getattr(s, "NOMBRE", "") != "planificador"]
    especificas = [s for s in skills if getattr(s, "NOMBRE", "") != "python"]
    generico = [s for s in skills if getattr(s, "NOMBRE", "") == "python"]
    for s in especificas + generico:
        try:
            if s.detecta(paso):
                return s
        except Exception as e:
            log.error(f"[PLAN] {getattr(s,'NOMBRE','?')} detecta() falló: {e}")
    return None


def _contexto_con_previos(contexto, previos: list):
    base = dict(contexto) if isinstance(contexto, dict) else {}
    if previos:
        base["pasos_previos"] = [{"paso": p["paso"], "cuerpo": p["cuerpo"]} for p in previos]
        base["resumen_previos"] = "\n".join(f"- {p['paso']} → {p['cuerpo']}" for p in previos)
    return base


def _resolver_con_modelo(paso: str, previos: list) -> str:
    if not _llm.disponible():
        return "(no había habilidad para este paso y el modelo no está disponible)"
    contexto = ""
    if previos:
        contexto = "Resultados previos:\n" + "\n".join(
            f"- {p['paso']} → {p['cuerpo']}" for p in previos
        ) + "\n\n"
    prompt = f"{contexto}Resolvé este paso de forma breve y concreta, en español: {paso}"
    return _llm.chat(prompt, max_tokens=500, temperature=0.4).strip()


def _ejecutar_paso(paso, contexto, previos):
    skill = _rutear(paso)
    if skill is not None:
        try:
            ctx = _contexto_con_previos(contexto, previos)
            res = skill.manejar(paso, ctx)
            return {"paso": paso, "skill": getattr(skill, "NOMBRE", "?"),
                    "cuerpo": res.get("cuerpo", ""), "ok": res.get("ok", True)}
        except Exception as e:
            log.error(f"[PLAN] {getattr(skill,'NOMBRE','?')} manejar() falló: {e}")
            return {"paso": paso, "skill": getattr(skill, "NOMBRE", "?"),
                    "cuerpo": f"(falló: {e})", "ok": False}
    cuerpo = _resolver_con_modelo(paso, previos)
    return {"paso": paso, "skill": "razonamiento", "cuerpo": cuerpo, "ok": True}


def ejecutar_plan(pasos: list, contexto: dict = None, objetivo: str = "",
                  replan_budget: int = 2) -> list:
    """
    Ejecuta el plan con re-planificación adaptativa. Devuelve
    [{paso, skill, cuerpo, ok, [replan]}, ...].
    """
    resultados = []
    pendientes = list(pasos or [])
    replanes = 0

    while pendientes and len(resultados) < _MAX_TOTAL:
        paso = pendientes.pop(0)
        res = _ejecutar_paso(paso, contexto, resultados)
        resultados.append(res)

        # Observar el fallo y replanificar lo que queda (si hay presupuesto).
        if not res["ok"] and replanes < replan_budget:
            try:
                from . import replanificador
                nuevos = replanificador.replanificar(objetivo, resultados, paso, pendientes)
            except Exception as e:
                log.error(f"[PLAN] replanificar falló: {e}")
                nuevos = []
            if nuevos:
                replanes += 1
                res["replan"] = True
                log.info(f"[PLAN] re-planifiqué tras fallar «{paso[:40]}»: {len(nuevos)} paso(s) nuevos")
                # Los pasos nuevos reemplazan lo que quedaba, respetando el techo.
                cupo = max(0, _MAX_TOTAL - len(resultados))
                pendientes = nuevos[:cupo]

    return resultados