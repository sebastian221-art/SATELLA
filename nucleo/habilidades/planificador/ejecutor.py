"""
nucleo/habilidades/planificador/ejecutor.py
Ejecuta el plan: rutea cada paso a la mejor habilidad (NUNCA al planificador
mismo — guarda anti-recursión) y, si ninguna lo reclama, lo resuelve con el
modelo. Devuelve un resultado por paso.
"""
import logging

from nucleo.habilidades.python import _llm

log = logging.getLogger("satella.habilidad.planificador")


def _rutear(paso: str):
    """
    Habilidad que reclame el paso, o None. En DOS pasadas:
      1) habilidades específicas (todo menos planificador y python)
      2) python como fallback (es el genérico de código)
    Así un paso como "convertí 50 a romano" va a 'romano', no a 'python',
    aunque python también lo reclame. (anti-recursión: nunca el planificador)
    """
    from nucleo.habilidades import registro
    skills = [s for s in registro.habilidades()
              if getattr(s, "NOMBRE", "") != "planificador"]
    especificas = [s for s in skills if getattr(s, "NOMBRE", "") != "python"]
    generico = [s for s in skills if getattr(s, "NOMBRE", "") == "python"]
    for s in especificas + generico:  # específicas primero, python al final
        try:
            if s.detecta(paso):
                return s
        except Exception as e:
            log.error(f"[PLAN] {getattr(s,'NOMBRE','?')} detecta() falló: {e}")
    return None


def _resolver_con_modelo(paso: str, previos: list) -> str:
    """Resuelve un paso que ninguna habilidad reclamó, con el modelo."""
    if not _llm.disponible():
        return "(no había habilidad para este paso y el modelo no está disponible)"
    contexto = ""
    if previos:
        contexto = "Resultados previos:\n" + "\n".join(
            f"- {p['paso']} → {p['cuerpo']}" for p in previos
        ) + "\n\n"
    prompt = (f"{contexto}Resolvé este paso de forma breve y concreta, en español: {paso}")
    return _llm.chat(prompt, max_tokens=500, temperature=0.4).strip()


def ejecutar_plan(pasos: list, contexto: dict = None) -> list:
    """Ejecuta cada paso en orden. Devuelve [{paso, skill, cuerpo, ok}, ...]."""
    resultados = []
    for paso in pasos:
        skill = _rutear(paso)
        if skill is not None:
            try:
                res = skill.manejar(paso, contexto)
                resultados.append({
                    "paso": paso,
                    "skill": getattr(skill, "NOMBRE", "?"),
                    "cuerpo": res.get("cuerpo", ""),
                    "ok": res.get("ok", True),
                })
            except Exception as e:
                log.error(f"[PLAN] {getattr(skill,'NOMBRE','?')} manejar() falló: {e}")
                resultados.append({"paso": paso, "skill": getattr(skill, "NOMBRE", "?"),
                                   "cuerpo": f"(falló: {e})", "ok": False})
        else:
            cuerpo = _resolver_con_modelo(paso, resultados)
            resultados.append({"paso": paso, "skill": "razonamiento", "cuerpo": cuerpo, "ok": True})
    return resultados