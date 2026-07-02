"""
nucleo/agentes/supervisor.py — EL SUPERVISOR.
─────────────────────────────────────────────────────────────────────────────
Nació de un problema real observado dos veces: el agente Laura, al consolidar su
informe, agregaba frases que sonaban profesionales pero que NO estaban en los datos
("Atención: riesgos de seguridad", "posibles cuellos de botella"). El modelo las
inventa para sonar útil. Eso es una alucinación, y en la empresa real puede costar
caro: un agente que reporta un "problema de seguridad" falso, o un "todo salió bien"
cuando en realidad falló.

El supervisor revisa el reporte de CADA agente ANTES de que llegue a Sebas y hace
una sola cosa, central:

  SEPARA LO CONFIRMADO DE LO INVENTADO.

Toma la EVIDENCIA (lo que las herramientas devolvieron de verdad) y la compara contra
el INFORME (lo que el agente afirma). Cada afirmación que no se rastrea a la evidencia
se marca como "opinión sin respaldo". Emite un veredicto: aprobado / observado /
rechazado. Es escéptico por diseño: ante la duda, marca.

Principio #1: todo "Atención / riesgo / problema" que un agente reporte tiene que
poder rastrearse a un dato real, o se marca como opinión sin respaldo.
"""
import json
import logging
import re

log = logging.getLogger("satella.supervisor")

_PROMPT_VERIFICAR = """Sos el SUPERVISOR de calidad de Satella: escéptico, riguroso e implacable. Un agente cumplió una misión y escribió un INFORME. Tu único trabajo: verificar que CADA afirmación del informe esté LITERALMENTE respaldada por la EVIDENCIA (lo que las herramientas devolvieron). Si algo del informe no aparece en la evidencia, es una OPINIÓN SIN RESPALDO, por más razonable o profesional que suene. NO seas indulgente: las advertencias de seguridad, los "riesgos", los "cuellos de botella", los "hay que monitorear/actualizar" casi siempre son inventados si no están en la evidencia.

EJEMPLO de cómo pensar:
  EVIDENCIA: "ERP-PSI: usa Node.js; usa MySQL; tiene Jelcom"
  INFORME: "El ERP-PSI usa Node.js y MySQL. Atención: hay riesgos de seguridad que monitorear."
  CORRECTO →
  {{"confirmados": ["El ERP-PSI usa Node.js y MySQL"],
    "sin_respaldo": ["Atención: hay riesgos de seguridad que monitorear (NO está en la evidencia, el agente lo inventó)"],
    "veredicto": "observado", "razon": "Agregó un riesgo de seguridad sin ningún dato que lo respalde."}}

Ahora verificá este caso real:

MISIÓN: «{mision}»

EVIDENCIA (lo único que las herramientas devolvieron de verdad):
{evidencia}

INFORME DEL AGENTE:
{informe}

Respondé SOLO JSON, sin texto afuera:
{{"confirmados": ["afirmaciones del informe respaldadas por la evidencia"],
 "sin_respaldo": ["afirmaciones del informe que NO están en la evidencia"],
 "veredicto": "aprobado|observado|rechazado",
 "razon": "una frase corta"}}

Veredicto: "aprobado" solo si TODO se rastrea a la evidencia; "observado" si hay algo sin respaldo; "rechazado" si contradice la evidencia o inventa logros."""


# Patrón de las alucinaciones observadas: lenguaje de "consultor que advierte".
# Si una frase del informe usa una de estas señales y la señal NO está en la
# evidencia, se marca como sin respaldo SIN depender del criterio del modelo.
_SENALES_INVENTO = (
    "riesgo", "segurid", "vulnerab", "monitor", "cuello de botella", "amenaza",
    "peligro", "atención", "atencion", "crítico", "critico", "debería", "deberia",
    "conviene", "recomend", "parche", "actualiz", "disponibilidad", "escalab",
    "mantenimiento", "optimiz", "podría generar", "podria generar", "podrían",
    "se sugiere", "es importante", "hay que", "asegurar", "garantizar",
)


def _filtro_mecanico(informe: str, evidencia: str) -> list:
    """Red de seguridad que NO depende del modelo: marca frases con lenguaje de
    advertencia/recomendación cuya señal no aparezca en la evidencia."""
    ev = (evidencia or "").lower()
    flags = []
    for frase in re.split(r"[.\n;•\-]\s*", informe or ""):
        f = frase.strip()
        if len(f) < 15:
            continue
        fl = f.lower()
        for sig in _SENALES_INVENTO:
            if sig in fl and sig not in ev:
                flags.append(f[:160])
                break
    return flags


def _parsear_json(salida: str) -> dict:
    if not salida:
        return {}
    s = re.sub(r"```json|```", "", salida)
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    spans, pila = [], []
    for i, ch in enumerate(s):
        if ch == "{":
            pila.append(i)
        elif ch == "}" and pila:
            spans.append(s[pila.pop():i + 1])
    for cand in sorted(set(spans), key=len, reverse=True):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict) and "veredicto" in obj:
                return obj
        except Exception:
            continue
    return {}


def revisar(reporte: dict) -> dict:
    """Revisa el reporte de un agente. Devuelve el dictamen del supervisor:
    {veredicto, confirmados, sin_respaldo, razon, coherencia, verificado}.
    Nunca rompe: si no puede verificar, lo dice sin bloquear."""
    bitacora = reporte.get("bitacora", [])
    informe = (reporte.get("sintesis") or "").strip()
    mision = reporte.get("mision", "")

    # 1) EVIDENCIA: lo que las herramientas devolvieron de verdad (la verdad de campo).
    evidencia_items = [b for b in bitacora if b.get("estado") in ("ok", "reusado") and b.get("resultado")]
    evidencia_txt = "\n".join(f"- [{b.get('herramienta')}] {b['resultado']}" for b in evidencia_items)

    # 2) COHERENCIA DE ESTADO: ¿dice que terminó pero hay pasos que fallaron sin avisar?
    malos = [b for b in bitacora if b.get("estado") in ("bloqueado", "saltado", "denegado")]
    coherencia = "ok"
    nota_coherencia = ""
    if reporte.get("estado") == "listo" and malos:
        coherencia = "incoherente"
        nota_coherencia = f"El estado dice LISTO pero {len(malos)} paso(s) no se completaron."

    # 3) Sin informe que verificar → no hay nada que alucinar.
    if not informe:
        return {"veredicto": "aprobado", "confirmados": [], "sin_respaldo": [],
                "razon": "No hubo informe consolidado que verificar.",
                "coherencia": coherencia, "nota_coherencia": nota_coherencia,
                "verificado": True}

    # 4) Sin evidencia pero CON informe → todo el informe es sospechoso.
    if not evidencia_txt:
        return {"veredicto": "observado", "confirmados": [],
                "sin_respaldo": ["El informe completo no tiene evidencia de herramientas que lo respalde."],
                "razon": "El agente informó sin datos de herramientas detrás.",
                "coherencia": coherencia, "nota_coherencia": nota_coherencia,
                "verificado": True}

    # 5) Verificación con el modelo (escéptico).
    try:
        from nucleo.habilidades.python import _llm
        if not _llm.disponible():
            return {"veredicto": "sin_verificar", "confirmados": [], "sin_respaldo": [],
                    "razon": "No hay modelo para verificar el informe.",
                    "coherencia": coherencia, "nota_coherencia": nota_coherencia,
                    "verificado": False}
        prompt = _PROMPT_VERIFICAR.format(mision=mision,
                                          evidencia=evidencia_txt[:3500],
                                          informe=informe[:2000])
        salida = _llm.chat(prompt, max_tokens=2000, temperature=0.1, reasoning_effort="low")
        if not salida:
            salida = _llm.chat(prompt, max_tokens=3500, temperature=0.1)
        obj = _parsear_json(salida)
    except Exception as e:
        log.error(f"Supervisor: verificación falló: {e}")
        obj = {}

    if not obj:
        obj = {"confirmados": [], "sin_respaldo": [], "veredicto": "sin_verificar",
               "razon": "no pude verificar con el modelo"}

    # RED MECÁNICA (no depende del modelo): caza el patrón de las alucinaciones.
    flags_mecanicos = _filtro_mecanico(informe, evidencia_txt)

    sin_respaldo = list(obj.get("sin_respaldo", []))
    # Sumar lo que el filtro mecánico cazó y el modelo no marcó.
    for f in flags_mecanicos:
        if not any(f[:40].lower() in (s or "").lower() for s in sin_respaldo):
            sin_respaldo.append(f)

    veredicto = obj.get("veredicto", "observado")
    if veredicto == "sin_verificar" and not flags_mecanicos:
        # el modelo no respondió pero la red mecánica tampoco vio nada raro
        return {"veredicto": "sin_verificar", "confirmados": obj.get("confirmados", []),
                "sin_respaldo": sin_respaldo, "razon": obj.get("razon", ""),
                "coherencia": coherencia, "nota_coherencia": nota_coherencia,
                "verificado": False}

    # Si HAY afirmaciones sin respaldo (por el modelo o por la red mecánica),
    # NUNCA puede ser un aprobado limpio. El filtro mecánico tiene la última palabra.
    if sin_respaldo and veredicto == "aprobado":
        veredicto = "observado"
    # Incoherencia de estado tampoco permite aprobado.
    if coherencia == "incoherente" and veredicto == "aprobado":
        veredicto = "observado"

    return {"veredicto": veredicto,
            "confirmados": obj.get("confirmados", []),
            "sin_respaldo": sin_respaldo,
            "razon": obj.get("razon", ""),
            "coherencia": coherencia, "nota_coherencia": nota_coherencia,
            "verificado": True}


def formatear(dictamen: dict) -> str:
    """Arma el bloque del supervisor para mostrarle a Sebas."""
    if not dictamen:
        return ""
    ver = dictamen.get("veredicto", "?")
    iconos = {"aprobado": "✅", "observado": "⚠️", "rechazado": "❌",
              "sin_verificar": "❓"}
    titulo = {"aprobado": "APROBADO — el informe se sostiene con los datos.",
              "observado": "OBSERVADO — hay afirmaciones sin respaldo (cuidado).",
              "rechazado": "RECHAZADO — el informe no coincide con lo que pasó.",
              "sin_verificar": "SIN VERIFICAR — no pude chequear el informe."}
    out = ["─── SUPERVISOR ───",
           f"{iconos.get(ver, '·')} Veredicto: {titulo.get(ver, ver)}"]

    if dictamen.get("nota_coherencia"):
        out.append(f"  ⚠️ {dictamen['nota_coherencia']}")

    sin_resp = dictamen.get("sin_respaldo", [])
    if sin_resp:
        out.append("  El agente agregó esto SIN respaldo en los datos (verificá vos):")
        for s in sin_resp[:6]:
            out.append(f"    ⚠️ {s}")

    conf = dictamen.get("confirmados", [])
    if conf and ver != "aprobado":
        out.append("  Lo que SÍ está respaldado por los datos:")
        for c in conf[:6]:
            out.append(f"    ✓ {c}")

    return "\n".join(out)