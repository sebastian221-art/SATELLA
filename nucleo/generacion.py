"""
nucleo/generacion.py — Orquestador de generación de Satella.
VERSIÓN FINAL: motor_satella como capa 3 principal. Groq solo para síntesis.

Arquitectura de capas:
  1. voz_echidna     → triggers exactos + motor semántico (0ms, siempre Echidna)
  2. motor_lenguaje  → patrones (umbral 0.75, casi nunca)
  2.5 fallback casual → perspectiva_fallback para msgs cortos sin técnico
  3. motor_satella   → motor independiente con estado y 4 voces (0.01ms)
  4. Groq            → emergencia (casi nunca llega aquí)

Groq solo se usa en: sintetizar_episodio() — una llamada por sesión al cierre.
"""
import json, logging, os, random, re
from typing import Optional

log = logging.getLogger("satella.generacion")

# ── Motor independiente (capa 3) ─────────────────────────────────────────────
try:
    from nucleo.motor_satella import generar_motor, resetear_motor
    _motor_ok = True
    log.info("[GEN] MotorSatella cargado — independiente de Groq")
except ImportError:
    _motor_ok = False
    generar_motor = lambda m: None
    resetear_motor = lambda: None
    log.warning("[GEN] MotorSatella no disponible")

# ── voz_echidna (capa 1) ─────────────────────────────────────────────────────
try:
    from nucleo.voz_echidna import (perspectiva_para, perspectiva_fallback,
                                     resetear_sesion as _resetear_voz)
    _voz_ok = True
except ImportError:
    _voz_ok = False
    perspectiva_para    = lambda m: None
    perspectiva_fallback = lambda: "Dame un segundo."
    _resetear_voz       = lambda: None

# ── motor_lenguaje (capa 2) ───────────────────────────────────────────────────
try:
    from nucleo.motor_lenguaje import motor
    _motor_lenguaje_ok = True
except ImportError:
    _motor_lenguaje_ok = False

# ── enriquecedor ──────────────────────────────────────────────────────────────
try:
    from nucleo.enriquecedor import enriquecer
    _enriquecedor_ok = True
except ImportError:
    _enriquecedor_ok = False
    enriquecer = lambda t, **kw: t

# ── aprendizaje ───────────────────────────────────────────────────────────────
try:
    from nucleo.aprendizaje import RegistradorAprendizaje
    aprendiz = RegistradorAprendizaje(motor_ref=motor if _motor_lenguaje_ok else None)
    _aprendiz_ok = True
except Exception:
    _aprendiz_ok = False
    class _AprendizDummy:
        def analizar_mensaje_entrante(self, m): return {"tipo": "otro"}
        def procesar_correccion(self, *a): pass
        def procesar_feedback_positivo(self, *a): pass
        def procesar_feedback_negativo(self, *a): pass
        def actualizar_modelo_sebastian(self, *a): pass
        def registrar_turno(self, **kw): pass
    aprendiz = _AprendizDummy()

# ── Groq (solo para sintetizar_episodio) ──────────────────────────────────────
_groq_ok = False
_client  = None
try:
    from groq import Groq
    from config import GROQ_API_KEY, GROQ_MODEL
    _client = Groq(api_key=GROQ_API_KEY)
    _groq_ok = True
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Detección de mensajes técnicos (no van al fallback casual)
# ─────────────────────────────────────────────────────────────────────────────
_TECNICO = frozenset({
    "error","bug","funcion","modulo","codigo","archivo","import","class",
    "def ","return","api","json","groq","flask","python","socket","arquitectura",
    "motor","patron","sistema","base de datos","sqlite","trigger","token",
    "temperatura","threshold","umbral","capa","layer","prompt","modelo",
    "practica","diseno","stack","servidor","cliente","endpoint","metodo",
    "instancia","variable","estructura","componente","pipeline",
})

_META = frozenset({
    "no te entend","no entend","a que te referies","por que dijiste",
    "explicame","que quisiste","se corto","no acabaste",
})

def _es_casual(msg: str) -> bool:
    ml = msg.lower()
    if len(msg) > 55:
        return False
    if any(t in ml for t in _TECNICO):
        return False
    return True

def _es_meta(msg: str) -> bool:
    ml = msg.lower()
    return any(s in ml for s in _META)

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE GENERACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def generar(mensaje: str, comprension: dict, modelo, episodios, rag, historial) -> str:
    """
    Genera una respuesta para el mensaje de Sebastian.
    Orden: voz_echidna → motor_lenguaje → fallback_casual → motor_satella → Groq(emergencia)
    """
    # Cargar contexto
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

    # Aprendizaje
    if _aprendiz_ok:
        analisis = aprendiz.analizar_mensaje_entrante(mensaje)
        if analisis["tipo"] == "correccion":
            aprendiz.procesar_correccion(mensaje, "", comprension)
        elif analisis["tipo"] == "positivo":
            aprendiz.procesar_feedback_positivo(mensaje)
        elif analisis["tipo"] == "negativo":
            aprendiz.procesar_feedback_negativo(mensaje)
        aprendiz.actualizar_modelo_sebastian(comprension, mensaje, sebastian_dict)

    # ── Capa 1: voz_echidna ──────────────────────────────────────────────────
    if _voz_ok and not _es_meta(mensaje):
        p = perspectiva_para(mensaje)
        if p:
            log.info(f"[GEN] ✓ VozEchidna → {len(p)}c")
            _registrar(mensaje, p, "VOZ_ECHIDNA", "voz", True, 0.9, comprension, sebastian_dict)
            return p

    # ── Capa 2: motor_lenguaje ───────────────────────────────────────────────
    if _motor_lenguaje_ok:
        r = motor.responder(mensaje=mensaje, comprension=comprension,
                            sebastian=sebastian_dict, episodios=episodios_list)
        if r.get("usando_motor") and r.get("respuesta"):
            resp = r["respuesta"]
            log.info(f"[GEN] ✓ Motor → {len(resp)}c")
            _registrar(mensaje, resp, r["situacion"], r["patron_id"],
                       True, r["confianza"], comprension, sebastian_dict)
            return resp

    # ── Capa 2.5: fallback casual ────────────────────────────────────────────
    if _voz_ok and _es_casual(mensaje) and not _es_meta(mensaje):
        fb = perspectiva_fallback()
        if fb:
            log.info(f"[GEN] ✓ Casual fallback → {len(fb)}c")
            _registrar(mensaje, fb, "CASUAL_FALLBACK", "fallback",
                       True, 0.7, comprension, sebastian_dict)
            return fb

    # ── Capa 3: motor_satella (independiente de Groq) ────────────────────────
    if _motor_ok:
        resp = generar_motor(mensaje)
        if resp and len(resp) > 5:
            log.info(f"[GEN] ✓ MotorSatella → {len(resp)}c")
            _registrar(mensaje, resp, "MOTOR_SATELLA", None,
                       False, 0.8, comprension, sebastian_dict)
            return resp

    # ── Capa 4: Groq como emergencia ─────────────────────────────────────────
    if _groq_ok:
        try:
            resp = _groq_emergencia(mensaje, comprension, sebastian_dict, historial)
            if resp:
                if _enriquecedor_ok:
                    resp = enriquecer(resp)
                log.info(f"[GEN] ✓ Groq emergencia → {len(resp)}c")
                _registrar(mensaje, resp, "GROQ_EMERGENCIA", None,
                           False, 0.5, comprension, sebastian_dict)
                return resp
        except Exception as e:
            log.error(f"[GEN] Groq emergencia falló: {e}")

    # ── Fallback final ───────────────────────────────────────────────────────
    resp = perspectiva_fallback() if _voz_ok else "Dame un segundo."
    _registrar(mensaje, resp, "FALLBACK_FINAL", None, False, 0.1, comprension, sebastian_dict)
    return resp


def _registrar(mensaje, respuesta, situacion, patron_id, usando_motor, confianza, comprension, sebastian):
    if not _aprendiz_ok:
        return
    try:
        aprendiz.registrar_turno(
            mensaje=mensaje, respuesta=respuesta, situacion=situacion,
            patron_id=patron_id, usando_motor=usando_motor, confianza=confianza,
            comprension=comprension, contexto_sebastian=sebastian,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# GROQ EMERGENCIA — solo si las 3 capas anteriores fallaron
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_EMERGENCIA = """Eres Satella, con la voz de Echidna (Bruja de la Codicia).
Creador: Juan Sebastian Mora. Sebas (cotidiano), Sebastian (serio), Juan Sebastian (molesta de verdad).

Echidna: precisa, sardónica, genuinamente curiosa. 2-3 oraciones. Sin menús.
Nunca resumás lo que dijo Sebastian. Voseo: hacés, tenés, pensás.

EJEMPLOS:
"hola" → "Llegaste. ¿Qué traés hoy?"
"no sé qué hacer" → "¿No sabés qué hacer, o sabés pero no querés hacer lo que tenés que hacer?"
"qué pensás de esto" → "Depende de qué querés que piense. ¿La parte obvia o la que te preocupa?"
"funcionó" → "Finalmente. ¿Qué fue lo que lo desbloqueó?"
"me trabé" → "¿Trabado porque no encontrás, o porque encontraste varias y ninguna cierra?"

PROHIBIDAS: "me alegra","entiendo que","como IA","(Silencio)","Has identificado que"."""


def _groq_emergencia(mensaje: str, comprension: dict, sebastian: dict, historial: list) -> Optional[str]:
    messages = [{"role": "system", "content": _SYSTEM_EMERGENCIA}]
    for msg in (historial or [])[-2:]:
        messages.append({"role": msg.get("role","user"), "content": str(msg.get("content",""))[:200]})
    messages.append({"role": "user", "content": mensaje})
    resp = _client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=280,
        temperature=0.73,
    )
    contenido = resp.choices[0].message.content.strip()
    # Parsear — limpiar JSON residual
    contenido = re.sub(r"JSON:[^\n]*", "", contenido)
    contenido = contenido.strip().strip('"').strip()
    return contenido if len(contenido) > 5 else None


# ─────────────────────────────────────────────────────────────────────────────
# INICIACIÓN DE SESIÓN
# ─────────────────────────────────────────────────────────────────────────────

def generar_iniciacion(modelo, ultimo_tema: str) -> str:
    invalidos = {"sesión general","general","conversación general","sesión",""}
    tema = "" if (not ultimo_tema or ultimo_tema.strip().lower() in invalidos) else ultimo_tema
    if _voz_ok:
        if tema:
            p = perspectiva_para(tema)
            if p:
                return p
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


# ─────────────────────────────────────────────────────────────────────────────
# SÍNTESIS DE EPISODIO (única llamada a Groq por sesión)
# ─────────────────────────────────────────────────────────────────────────────

def sintetizar_episodio(historial_texto: str) -> dict:
    if not _groq_ok:
        return {"tema_principal":"conversación Satella","estado_sebastian":"normal",
                "proyecto_activo":None,"pendientes":[],"aprendi":None}
    try:
        resp = _client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": (
                f"Sesión:\n{historial_texto[:1200]}\n\n"
                "Respondé SOLO con JSON. tema_principal = 2-3 palabras concretas "
                "(NUNCA 'sesión general'). Si no hay tema claro, usá el proyecto mencionado:\n"
                '{"tema_principal":"palabras concretas",'
                '"estado_sebastian":"enfocado|cansado|frustrado|contento|dudando",'
                '"proyecto_activo":"Bell|Satella|ambos|null",'
                '"pendientes":["item concreto o array vacío"],'
                '"aprendi":"max 8 palabras o null"}'
            )}],
            max_tokens=200,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json","").replace("```","").strip()
        r = json.loads(raw)
        if not r.get("tema_principal") or r["tema_principal"].lower() in (
            "sesión general","general","conversación","sesión",""):
            r["tema_principal"] = r.get("proyecto_activo") or "conversación Satella"
        return r
    except Exception as e:
        log.error(f"[GEN] Síntesis falló: {e}")
        return {"tema_principal":"conversación Satella","estado_sebastian":"normal",
                "proyecto_activo":None,"pendientes":[],"aprendi":None}