"""
generacion.py — Groq genera directamente con voz Echidna via ejemplos.
La versión que funcionaba: ejemplos fuertes + Groq 70b + voz_echidna.
"""
import json, logging, os, random, re
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MODEL_RAPIDO
from nucleo.motor_lenguaje import motor
from nucleo.aprendizaje import RegistradorAprendizaje

log      = logging.getLogger("satella.generacion")
_client  = Groq(api_key=GROQ_API_KEY)
aprendiz = RegistradorAprendizaje(motor_ref=motor)

_MODELO_GEN = "llama-3.3-70b-versatile"

try:
    from nucleo.enriquecedor import enriquecer
    _enriquecedor_ok = True
except ImportError:
    _enriquecedor_ok = False
    enriquecer = lambda t, **kw: t

try:
    from nucleo.voz_echidna import (perspectiva_para, perspectiva_fallback,
                                     resetear_sesion as _resetear_voz)
    _voz_ok = True
except ImportError:
    _voz_ok = False
    perspectiva_para = lambda m: None
    perspectiva_fallback = lambda: None
    _resetear_voz = lambda: None

_nlp = None
def _get_lemas(txt: str) -> str:
    global _nlp
    try:
        if _nlp is None:
            import spacy
            try:    _nlp = spacy.load("es_core_news_sm")
            except: _nlp = spacy.blank("es")
        doc = _nlp(txt[:300])
        return " ".join([t.lemma_.lower() for t in doc
                         if not t.is_stop and not t.is_punct and len(t.text) > 2][:12])
    except Exception:
        return txt[:80]

# ─── SYSTEM PROMPT — voz Echidna via ejemplos fuertes ────────────────────────
_SYSTEM_BASE = """Eres Satella, con la voz de Echidna (Bruja de la Codicia).
Creador: Juan Sebastian Mora. Sebas (cotidiano), Sebastian (serio), Juan Sebastian (molesta de verdad).

Echidna: precisa, sardónica, genuinamente curiosa sobre el interior de Sebastian.
Una observación que reencuadra lo que dijo, O una pregunta que va al punto que evitó.
Seca. Directa. 2-3 oraciones completas. Sin consultoría ni menús de opciones.

EJEMPLOS — estudiá el TONO, no copies las palabras:

"quiero que sea más única"
→ "Única en qué sentido exactamente. Porque única como identidad y única como capacidad son problemas completamente distintos."

"creo que es cuestión de tiempo"
→ "El tiempo no mejora nada por sí solo. Lo que mejora es el criterio de quien evalúa. ¿Cómo va a cambiar el tuyo?"

"dime qué tenés en mente"
→ "Nada que no hayas pensado ya. La pregunta más útil es cuál de las cosas que ya pensaste no te animás a hacer todavía."

"me falta personalidad en tus respuestas"
→ "Fascinante observación. ¿Qué parte específicamente — el carácter, la precisión, o el que yo misma no sepa cuándo callar?"

"qué pensás de mi trabajo"
→ "La arquitectura que elegiste es más sofisticada de lo que la mayoría intentaría. La pregunta interesante es si la complejidad está al servicio del problema o del placer de diseñar."

"sigo sin poder terminar esto"
→ "Llevás mucho tiempo en esto. Cuando algo resiste así, hay una suposición incorrecta en algún lugar. ¿Cuál es la que estás dando por sentada?"

"me cuesta arrancar"
→ "La resistencia aparece antes de empezar, no durante. Eso indica que el problema no es la tarea — es el umbral de entrada. Una vez que empezás, desaparece."

"me preocupa que el resultado no sea perfecto"
→ "La perfección que buscás es un estado que siempre va a estar un paso más adelante. ¿En qué momento decidís que es suficiente?"

PROHIBIDAS: "supongo que","me alegra","entiendo que","la pausa que mencionaste sugiere",
"como IA","mi función es","(Silencio)","como Echidna se supone"
Responde directamente. Nunca resumás lo que dijo antes de responder."""


def _construir_prompt(comprension, modelo, episodios, rag):
    partes = [_SYSTEM_BASE]
    if modelo:
        partes.append(f"\nSebastian: {str(modelo)[:150]}")
    if episodios:
        ep = str(episodios).replace('\n', ' ')
        partes.append(f"\nAntes: {ep[-180:]}")
    if rag:
        partes.append(f"\nCtx: {str(rag)[:300]}")
    partes.append(
        f"\nTono:{comprension.get('tono','normal')} "
        f"Necesita:{comprension.get('necesita','info')} "
        f"Nombre:{comprension.get('nombre','Sebas')}"
    )
    return "\n".join(partes)


def _parsear(contenido: str) -> str:
    texto = re.sub(r"JSON:[^\n]*", "", contenido)
    texto = re.sub(r'\{[^}]*"s"[^}]*\}', "", texto)
    texto = texto.strip().strip('"').strip()
    if texto and texto[-1] == '!' and '¿' in texto:
        texto = texto[:-1] + '?'
    return texto


_META = ["no te entend","no entend","a qué te referís","por qué dijiste",
         "explicame","qué quisiste","se cortó","no acabaste"]

def _es_meta(msg: str) -> bool:
    return any(s in msg.lower() for s in _META)


def _groq_generar(mensaje, comprension, modelo, episodios, rag, historial, lemas):
    system = _construir_prompt(comprension, modelo, episodios, rag)
    messages = [{"role": "system", "content": system}]
    for msg in historial[-2:]:
        messages.append({
            "role": msg.get("role", "user"),
            "content": str(msg.get("content", ""))[:180]
        })
    user_content = f"[lemas: {lemas}]\n{mensaje}" if lemas else mensaje
    messages.append({"role": "user", "content": user_content})
    resp = _client.chat.completions.create(
        model=_MODELO_GEN, messages=messages,
        max_tokens=300, temperature=0.86,
    )
    contenido = resp.choices[0].message.content.strip()
    finish = resp.choices[0].finish_reason
    log.info(f"[GEN] Groq {finish} | {len(contenido)} chars")
    return _parsear(contenido), finish


def generar(mensaje, comprension, modelo, episodios, rag, historial):
    try:
        mp = os.path.join(os.path.dirname(__file__), "..", "datos", "modelo_sebastian.json")
        sebastian_dict = json.load(open(mp, encoding="utf-8"))
    except Exception:
        sebastian_dict = {}
    try:
        ep = os.path.join(os.path.dirname(__file__), "..", "datos", "episodios.json")
        episodios_list = json.load(open(ep, encoding="utf-8"))
    except Exception:
        episodios_list = []

    analisis = aprendiz.analizar_mensaje_entrante(mensaje)
    if analisis["tipo"] == "correccion":
        aprendiz.procesar_correccion(mensaje, "", comprension)
    elif analisis["tipo"] == "positivo":
        aprendiz.procesar_feedback_positivo(mensaje)
    elif analisis["tipo"] == "negativo":
        aprendiz.procesar_feedback_negativo(mensaje)
    aprendiz.actualizar_modelo_sebastian(comprension, mensaje, sebastian_dict)

    # Capa 1: voz_echidna (triggers precisos con scoring)
    if _voz_ok and not _es_meta(mensaje):
        p = perspectiva_para(mensaje)
        if p:
            log.info(f"[GEN] ✓ VozEchidna → {len(p)} chars")
            aprendiz.registrar_turno(
                mensaje=mensaje, respuesta=p, situacion="VOZ_ECHIDNA",
                patron_id="voz", usando_motor=True, confianza=0.9,
                comprension=comprension, contexto_sebastian=sebastian_dict,
            )
            return p

    # Capa 2: motor de patrones
    resultado_motor = {"respuesta": None, "situacion": "SMALL_TALK",
                       "patron_id": None, "confianza": 0.0, "usando_motor": False}
    resultado_motor = motor.responder(
        mensaje=mensaje, comprension=comprension,
        sebastian=sebastian_dict, episodios=episodios_list,
    )
    if resultado_motor["usando_motor"] and resultado_motor["respuesta"]:
        respuesta = resultado_motor["respuesta"]
        log.info(f"[GEN] ✓ Motor → {len(respuesta)} chars")
        aprendiz.registrar_turno(
            mensaje=mensaje, respuesta=respuesta,
            situacion=resultado_motor["situacion"],
            patron_id=resultado_motor["patron_id"],
            usando_motor=True, confianza=resultado_motor["confianza"],
            comprension=comprension, contexto_sebastian=sebastian_dict,
        )
        return respuesta

    # Capa 3: Groq genera directamente con voz Echidna
    lemas = _get_lemas(mensaje)
    try:
        respuesta, _ = _groq_generar(mensaje, comprension, modelo, episodios, rag, historial, lemas)
        if _enriquecedor_ok and respuesta:
            r2 = enriquecer(respuesta)
            if r2 != respuesta:
                log.info("[GEN] ✓ Enriquecedor aplicó cambios")
            respuesta = r2
        if not respuesta or len(respuesta) < 10:
            respuesta = perspectiva_fallback() if _voz_ok else "Dame un segundo."
        log.info(f"[GEN] ✓ Groq → {len(respuesta)} chars")
    except Exception as e:
        log.error(f"[GEN] Error: {e}")
        respuesta = perspectiva_fallback() if _voz_ok else "Dame un segundo."

    aprendiz.registrar_turno(
        mensaje=mensaje, respuesta=respuesta,
        situacion=resultado_motor["situacion"],
        patron_id=None, usando_motor=False,
        confianza=resultado_motor["confianza"],
        comprension=comprension, contexto_sebastian=sebastian_dict,
    )
    return respuesta


def generar_iniciacion(modelo, ultimo_tema):
    invalidos = {"sesión general","general","conversación general","sesión",""}
    tema = "" if (not ultimo_tema or ultimo_tema.strip().lower() in invalidos) else ultimo_tema
    if _voz_ok:
        if tema:
            p = perspectiva_para(tema)
            if p: return p
        return random.choice([
            "¿En qué punto dejaste lo de Bell?",
            "Hay algo de tu arquitectura que no terminé de procesar.",
            "¿Qué descubriste desde la última vez?",
            "¿En qué estás metido ahora?",
            "¿Cómo va el proyecto desde que hablamos?",
            "La última vez quedaste en algo sin resolver. ¿Avanzaste?",
            "¿Qué cambió desde que no hablamos?",
        ])
    return "¿Qué hay?"


def sintetizar_episodio(historial_texto):
    try:
        resp = _client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": (
                f"Sesión:\n{historial_texto[:1200]}\n\n"
                'JSON sin texto:\n{"tema_principal":"3 palabras concretas",'
                '"estado_sebastian":"enfocado|cansado|frustrado|contento|dudando",'
                '"proyecto_activo":"Bell|Satella|null",'
                '"pendientes":["item"],"aprendi":"max 8 palabras"}'
            )}],
            max_tokens=200, temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json","").replace("```","").strip()
        r = json.loads(raw)
        if r.get("tema_principal","").lower() in ("sesión general","general",""):
            r["tema_principal"] = r.get("proyecto_activo") or "conversación"
        return r
    except Exception as e:
        log.error(f"[GEN] Síntesis: {e}")
        return {"tema_principal":"conversación","estado_sebastian":"normal",
                "proyecto_activo":None,"pendientes":[],"aprendi":""}