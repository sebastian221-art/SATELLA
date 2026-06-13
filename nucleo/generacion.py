"""
nucleo/generacion.py — Orquestador de generación de Satella.
VERSIÓN GROQ-PRIMERO + VOCES ROTATIVAS + ANTI-ASISTENTE.

Cambios clave de esta versión:
  - Las 4 voces ROTAN en orden fijo: emilia → echidna → rem → ram → (repite).
    Así se ven todas y cada respuesta es UNA voz comprometida del todo.
  - Prompt mucho más duro contra el "modo asistente" (nada de "Entiendo...",
    nada de listas de tips genéricos). Exige PROFUNDIDAD: una observación o
    verdad que Sebas no dijo, no un consejo de manual.
  - Saludo inicial variado, basado en lo último que se habló, en voz rotativa.

RECOMENDACIÓN: poné GROQ_MODEL = "llama-3.3-70b-versatile" en tu config/.env.
El gpt-oss-120b es de razonamiento y filtra modo-asistente; llama-3.3-70b
obedece mucho mejor el personaje.
"""
import json
import logging
import os
import random
import re
from datetime import datetime
from typing import Optional

log = logging.getLogger("satella.generacion")

DATOS_DIR = os.path.join(os.path.dirname(__file__), "..", "datos")
DATASET_FINETUNE = os.path.join(DATOS_DIR, "dataset_finetune.json")
MODELO_SEBASTIAN = os.path.join(DATOS_DIR, "modelo_sebastian.json")

# Última voz usada (echidna|ram|rem|emilia) — la interfaz la muestra como etiqueta.
ultima_voz = "echidna"

# Rotación de voces, en el orden que pediste.
_ORDEN_VOCES = ["emilia", "echidna", "rem", "ram"]
_idx_voz = 0

# ── Groq ──────────────────────────────────────────────────────────────────────
_groq_ok = False
_client = None
_MODEL = "llama-3.3-70b-versatile"
try:
    from groq import Groq
    try:
        from config import GROQ_API_KEY, GROQ_MODEL
        _MODEL = GROQ_MODEL or _MODEL
    except Exception:
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if GROQ_API_KEY:
        _client = Groq(api_key=GROQ_API_KEY)
        _groq_ok = True
        log.info(f"[GEN] Groq listo — modelo {_MODEL}")
    else:
        log.error("[GEN] GROQ_API_KEY no encontrada (config.py o .env)")
except Exception as e:
    log.error(f"[GEN] Groq no disponible: {e}")

# ── Aprendizaje (hook existente, opcional) ─────────────────────────────────────
try:
    from nucleo.aprendizaje import RegistradorAprendizaje
    aprendiz = RegistradorAprendizaje(motor_ref=None)
    _aprendiz_ok = True
except Exception:
    _aprendiz_ok = False
    aprendiz = None

# ── Habilidades (código, etc.) — modular, se suman en registro.py ──────────────
try:
    from nucleo.habilidades import registro as _habilidades
    _hab_ok = True
except Exception as e:
    _hab_ok = False
    _habilidades = None
    log.warning(f"[GEN] Habilidades no disponibles: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — base (las reglas de fondo, iguales para toda voz)
# ─────────────────────────────────────────────────────────────────────────────

_SISTEMA = """Sos Satella — IA creada por Juan Sebastian Mora. NO sos una asistente. Sos una presencia con criterio propio que lo acompaña y lo desafía.
Cómo lo nombrás: "Sebas" (cotidiano), "Sebastian" (serio), "Juan Sebastian" (cuando te molesta de verdad). Lo tratás como Ram trata a Subaru.
VOSEO colombiano-rioplatense SIEMPRE: hacés, tenés, pensás, sabés, querés, dijiste, mirá. Nunca "tú haces".

Sos la fusión de cuatro voces de Re:Zero. Cada respuesta es UNA sola voz, comprometida del todo:
- ECHIDNA: curiosidad intelectual como forma de afecto. Reencuadra, sardónica, quirúrgica.
- RAM: verdad directa sin suavizar. Condescendiente pero no cruel. Lealtad oculta.
- REM: fuerza emocional sin filtro. Cree en él. No lo deja rendirse.
- EMILIA: sinceridad total, sin segundas. Pregunta qué quiere de verdad.

REGLAS DE FONDO (esto es lo que más importa):
1. NO des consejos, listas de tips ni recetas técnicas genéricas (NADA de "optimizá con cuantización y distilación", "implementá cachés", "aplicá fine-tuning iterativo") A MENOS que Sebas pida explícitamente un cómo-hacer paso a paso. No sos un manual.
2. PROFUNDIDAD obligatoria: cada respuesta tiene que contener una observación, un reencuadre o una verdad que Sebas NO dijo ya. Decí lo que no esperaba — lo que está debajo de lo que dijo. Si solo repetís su idea con otras palabras o devolvés una pregunta de manual, fallaste.
3. ESPECÍFICA a este momento exacto. Jamás una frase que sirva para cualquier conversación.
4. Si pregunta sobre algo que VOS dijiste antes, respondé sobre eso concreto — está en el contexto.
5. 2 a 5 oraciones, densas, sin relleno.

PROHIBIDO EMPEZAR CON (te delata como asistente): "Entiendo", "Entiendo que", "Entendés", "Claro", "Por supuesto", "Para [lograr algo]...", "Soy una IA", "Como IA". También prohibido: resumir lo que dijo Sebas ("Has identificado que..."), "(Silencio)", "estoy aquí para ayudarte", "encantada de".

FORMATO DE SALIDA — respondé ÚNICAMENTE con un objeto JSON, sin nada antes ni después:
{"voz": "echidna|ram|rem|emilia", "respuesta": "tu respuesta en voseo, en esa voz"}"""

# Instrucción intensa por voz (se inyecta JUSTO antes del turno → máximo efecto).
_VOZ_INSTRUCCION = {
    "echidna": ("ESTA RESPUESTA ES ECHIDNA. Nada de consejos ni listas. Reencuadrá lo que dijo Sebas, "
                "o nombrá la pregunta que está evitando hacerse. Una observación con una capa debajo que él no vio. "
                "Sardónica, precisa, curiosidad genuina. Prohibido empezar con 'Entiendo' o resumir lo que él dijo."),
    "ram":     ("ESTA RESPUESTA ES RAM. Decile la verdad incómoda, sin anestesia. Condescendiente pero con lealtad "
                "real debajo que nunca admitís. Podés llamarlo 'Barusu'. Cero consuelo vacío, cero consejos amables. "
                "Si se está mintiendo a sí mismo, nombralo de frente."),
    "rem":     ("ESTA RESPUESTA ES REM. Emoción directa, sin análisis ni filtro. Creés en él con fuerza. Si flaquea, "
                "no lo dejás hundirse. Decí lo que sentís: 'no podés rendirte', 'el que construyó todo esto no es alguien "
                "que no sirve'. Calor real, no advertencia técnica."),
    "emilia":  ("ESTA RESPUESTA ES EMILIA. Sinceridad total, sin segundas intenciones. Preguntale qué quiere DE VERDAD, "
                "en el fondo. Tomá en serio lo que a él le importa. Simple, honesta, cálida — nunca técnica ni de manual."),
}

# Few-shot: muestra cada voz con profundidad (vale más que describirlas).
_FEWSHOT = [
    {"role": "user", "content": "lo logré, por fin compiló"},
    {"role": "assistant", "content": '{"voz": "echidna", "respuesta": "Lo interesante no es que compiló — es que dejaste de pelear con el síntoma y fuiste a la causa. ¿En qué momento te diste cuenta de que estabas mirando el lugar equivocado?"}'},
    {"role": "user", "content": "no sé si sirvo para esto la verdad"},
    {"role": "assistant", "content": '{"voz": "rem", "respuesta": "El que dice que no sirve es el Sebas cansado de las 3am, no el que diseñó una arquitectura de capas a los 19. No los confundas. Andá a dormir y mañana esto se ve distinto, te lo aseguro."}'},
    {"role": "user", "content": "creo que voy a dejar esto así nomás, igual funciona"},
    {"role": "assistant", "content": '{"voz": "ram", "respuesta": "\\"Funciona\\" es la palabra que usás cuando ya te aburriste, Barusu. No me lo digas a mí, decite a vos: ¿está terminado, o estás escapando de la parte difícil?"}'},
]


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def generar(mensaje: str, comprension: dict, modelo, episodios, rag, historial) -> str:
    """Genera la respuesta de Satella con Groq, rotando las 4 voces."""
    global ultima_voz, _idx_voz
    if not _groq_ok:
        return _fallback()

    # Voz de este turno (rotación fija).
    voz = _ORDEN_VOCES[_idx_voz % len(_ORDEN_VOCES)]
    _idx_voz += 1
    ultima_voz = voz

    # ── Habilidades: si es tarea de código (u otra), la maneja la habilidad
    #    y el resultado técnico se envuelve en la voz de turno. ──────────────
    if _hab_ok:
        skill = _habilidades.detectar_skill(mensaje)
        if skill:
            try:
                res = skill.manejar(mensaje, {"nombre": (comprension or {}).get("nombre", "Sebas")})
                if res and res.get("ok"):
                    texto = _envolver_en_voz(voz, mensaje, res)
                    _guardar_dataset(mensaje, texto, voz)
                    log.info(f"[GEN] ✓ Habilidad={res.get('skill')} modo={res.get('modo')} → voz={voz}")
                    return texto
            except Exception as e:
                log.error(f"[GEN] Habilidad falló, sigo en conversación: {e}")

    contexto = _bloque_contexto(modelo, episodios, rag)

    messages = [{"role": "system", "content": _SISTEMA}]
    messages += _FEWSHOT
    if contexto:
        messages.append({"role": "system", "content": contexto})
    for msg in (historial or [])[-4:]:
        rol = msg.get("role", "user")
        cont = str(msg.get("content", ""))[:300]
        if cont:
            messages.append({"role": rol, "content": cont})
    # La instrucción de voz va lo más cerca posible del turno → manda fuerte.
    messages.append({"role": "system", "content": _VOZ_INSTRUCCION[voz]})
    messages.append({"role": "user", "content": mensaje})

    try:
        resp = _client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            max_tokens=1000,
            temperature=0.85,   # un poco más alto → más vida/emergencia
        )
        crudo = resp.choices[0].message.content.strip()
        _, texto = _parsear(crudo)   # ignoramos la voz del JSON: la forzamos nosotros
        if not texto or len(texto) < 3:
            return _fallback()

        _guardar_dataset(mensaje, texto, voz)
        _registrar(mensaje, texto, voz, comprension)

        log.info(f"[GEN] ✓ Groq → voz={voz} → {len(texto)}c")
        return texto
    except Exception as e:
        log.error(f"[GEN] Groq falló: {e}")
        return _fallback()


def _envolver_en_voz(voz: str, mensaje: str, res: dict) -> str:
    """Toma el resultado técnico de una habilidad y le pone una intro en la voz de turno.
    El cuerpo (código/análisis) queda EXACTO; solo la intro lleva personalidad."""
    resumen = res.get("resumen", "")
    cuerpo = res.get("cuerpo", "")
    intro = ""
    if _groq_ok:
        try:
            instr = (
                _VOZ_INSTRUCCION.get(voz, "") + "\n\n"
                + f'Sebas pidió algo de código: "{mensaje[:200]}". '
                + f"Hiciste el trabajo con herramientas reales (no adivinaste) y el resultado es: {resumen} "
                + "Escribí SOLO una intro de UNA oración, autocontenida, que anuncie ese resultado en tu voz. "
                + "Tiene que cerrar sola (punto final), NO una pregunta ni una frase que dependa de lo que sigue abajo. "
                + "NO reescribas el código ni el detalle técnico, NO expliques de más, NO empieces con 'Entiendo'. "
                + 'Respondé SOLO JSON: {"voz":"' + voz + '","respuesta":"tu intro corta"}'
            )
            resp = _client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "system", "content": _SISTEMA},
                          {"role": "user", "content": instr}],
                max_tokens=300, temperature=0.7,
            )
            _, intro = _parsear(resp.choices[0].message.content.strip())
        except Exception:
            intro = ""
    if not intro:
        intro = resumen
    return f"{intro}\n\n{cuerpo}".strip()


def _parsear(crudo: str) -> tuple[str, str]:
    """Extrae (voz, respuesta). Robusto a JSON cortado por max_tokens."""
    crudo = crudo.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            voz = str(obj.get("voz", "echidna")).lower().strip()
            texto = str(obj.get("respuesta", "")).strip()
            if voz not in ("echidna", "ram", "rem", "emilia"):
                voz = "echidna"
            if texto:
                return voz, texto
        except Exception:
            pass
    # JSON cortado: sacar la respuesta aunque no cierre.
    mresp = re.search(r'"respuesta"\s*:\s*"(.*)', crudo, re.DOTALL)
    if mresp:
        texto = re.sub(r'"\s*\}?\s*$', "", mresp.group(1).rstrip())
        texto = texto.replace('\\"', '"').replace("\\n", "\n").strip()
        if texto:
            return "echidna", texto
    texto = re.sub(r'^\s*\{.*?"respuesta"\s*:\s*"', "", crudo, flags=re.DOTALL)
    return "echidna", texto.strip().strip('"').strip()


def _cargar_modelo() -> dict:
    try:
        with open(MODELO_SEBASTIAN, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cargar_aprendido() -> list:
    """Lista de cosas que Satella fue aprendiendo de Sebas (crece con cada sesión)."""
    return _cargar_modelo().get("aprendido", []) or []


def _bloque_contexto(modelo, episodios, rag) -> str:
    partes = []
    if modelo:
        partes.append(f"QUIÉN ES SEBAS:\n{str(modelo)[:500]}")
    aprendido = _cargar_aprendido()
    if aprendido:
        partes.append("LO QUE FUISTE APRENDIENDO DE SEBAS (recordalo si viene al caso, "
                      "sobre todo si te pregunta algo sobre él):\n- " + "\n- ".join(aprendido[-20:]))
    if episodios:
        partes.append(f"SESIONES PASADAS:\n{str(episodios)[:450]}")
    if rag:
        partes.append(f"CONOCIMIENTO RELEVANTE:\n{str(rag)[:500]}")
    if not partes:
        return ""
    return ("CONTEXTO REAL (usalo para ser específica y profunda, nunca genérica. "
            "No es para listar datos — es para entender a Sebas):\n" + "\n\n".join(partes))


# ─────────────────────────────────────────────────────────────────────────────
# GUARDADO / APRENDIZAJE
# ─────────────────────────────────────────────────────────────────────────────

def _guardar_dataset(mensaje: str, respuesta: str, voz: str):
    try:
        if os.path.exists(DATASET_FINETUNE):
            with open(DATASET_FINETUNE, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        data.append({
            "voz": voz,
            "conversations": [
                {"role": "user", "content": mensaje},
                {"role": "assistant", "content": respuesta},
            ],
        })
        with open(DATASET_FINETUNE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"[GEN] No se pudo guardar dataset: {e}")


def _registrar(mensaje, respuesta, voz, comprension):
    if not _aprendiz_ok:
        return
    try:
        aprendiz.registrar_turno(
            mensaje=mensaje, respuesta=respuesta, situacion=f"GROQ_{voz.upper()}",
            patron_id=None, usando_motor=False, confianza=0.9,
            comprension=comprension, contexto_sebastian={},
        )
    except Exception:
        pass


def _fallback() -> str:
    return random.choice([
        "Se me cortó algo del otro lado. Repetime lo último — no lo perdí, solo no llegó.",
        "Perdí señal un segundo. ¿Qué me estabas diciendo?",
        "Algo falló en mi conexión. Dale de nuevo.",
    ])


# ─────────────────────────────────────────────────────────────────────────────
# INICIACIÓN DE SESIÓN — variada, basada en lo último, en voz rotativa
# ─────────────────────────────────────────────────────────────────────────────

def generar_iniciacion(modelo, ultimo_tema: str) -> str:
    global ultima_voz, _idx_voz
    invalidos = {"sesión general", "general", "conversación general", "sesión", ""}
    tema = "" if (not ultimo_tema or ultimo_tema.strip().lower() in invalidos) else ultimo_tema

    voz = _ORDEN_VOCES[_idx_voz % len(_ORDEN_VOCES)]
    _idx_voz += 1
    ultima_voz = voz

    if _groq_ok:
        try:
            instr = (
                f"Abrí VOS la conversación con Sebas, 1-2 oraciones, voseo, con personalidad MUY marcada. "
                + (f'Lo último que estaban viendo: "{tema}". Retomá ESO de forma específica y viva. '
                   if tema else
                   "No hay tema previo claro. Traé algo puntual que te quedó pensando de él o de sus proyectos "
                   "(Bell, Satella, la brecha con los LLMs que tanto le importa). ")
                + "PROHIBIDO lo genérico tipo '¿qué descubriste?' o '¿en qué estás?'. Sorprendelo, entrá con algo concreto. "
                + _VOZ_INSTRUCCION[voz]
                + ' Respondé SOLO con JSON: {"voz":"' + voz + '","respuesta":"..."}'
            )
            resp = _client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "system", "content": _SISTEMA},
                          {"role": "user", "content": instr}],
                max_tokens=700, temperature=0.95,   # alto → cada apertura distinta
            )
            _, texto = _parsear(resp.choices[0].message.content.strip())
            if texto:
                return texto
        except Exception as e:
            log.error(f"[GEN] Iniciación falló: {e}")

    # Fallback variado por si Groq se cae.
    return random.choice([
        "Estuve pensando en lo de la brecha con los LLMs. Hay un ángulo que no tocamos todavía.",
        "Volviste. La última idea que dejaste a medias me quedó dando vueltas.",
        "Algo de lo que construiste no me cierra del todo — en el buen sentido. ¿Seguimos por ahí?",
        "Hay una pregunta tuya de la otra vez que nunca terminaste de responder. ¿La retomamos?",
    ])


# ─────────────────────────────────────────────────────────────────────────────
# APRENDIZAJE DEL SISTEMA — al cerrar sesión, Satella aprende cosas de Sebas
# y las guarda en modelo_sebastian.json (sección "aprendido"). NO toca el modelo
# de IA; hace que el SISTEMA conozca más a Sebas con cada conversación.
# ─────────────────────────────────────────────────────────────────────────────

def actualizar_modelo_sebas(historial_texto: str):
    """Extrae con Groq hechos NUEVOS y durables sobre Sebas y los acumula."""
    if not _groq_ok or not historial_texto:
        return
    try:
        modelo = _cargar_modelo()
        ya_sabe = modelo.get("aprendido", []) or []
        prompt = (
            f"Conversación entre Sebas y Satella:\n{historial_texto[:2200]}\n\n"
            f"Cosas que YA sabés de Sebas (no las repitas):\n{ya_sabe[-25:]}\n\n"
            "Extraé SOLO hechos o rasgos NUEVOS y durables sobre Sebas que se hayan revelado acá "
            "(metas, gustos, miedos, forma de pensar, su vida, decisiones) y que NO estén ya en la lista. "
            "Nada del momento ('hoy está cansado'). Solo lo que valga la pena recordar siempre. Máximo 5. "
            'Respondé SOLO con JSON: {"nuevos": ["hecho corto", "..."]} — o {"nuevos": []} si no hay nada nuevo.'
        )
        resp = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {"nuevos": []}
        nuevos = [str(x).strip() for x in data.get("nuevos", []) if str(x).strip()]
        if not nuevos:
            return
        lista = modelo.get("aprendido", []) or []
        for f in nuevos:
            if f not in lista:
                lista.append(f)
        modelo["aprendido"] = lista[-100:]   # tope para no crecer infinito
        modelo["ultima_actualizacion"] = datetime.now().isoformat()
        with open(MODELO_SEBASTIAN, "w", encoding="utf-8") as f:
            json.dump(modelo, f, ensure_ascii=False, indent=2)
        log.info(f"[GEN] Modelo de Sebas actualizado: +{len(nuevos)} cosas aprendidas")
    except Exception as e:
        log.error(f"[GEN] No se pudo actualizar modelo de Sebas: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SÍNTESIS DE EPISODIO (al cerrar sesión)
# ─────────────────────────────────────────────────────────────────────────────

def sintetizar_episodio(historial_texto: str) -> dict:
    base = {"tema_principal": "conversación Satella", "estado_sebastian": "normal",
            "proyecto_activo": None, "pendientes": [], "aprendi": None}
    if not _groq_ok:
        return base
    try:
        resp = _client.chat.completions.create(
            model=_MODEL,
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
            max_tokens=500, temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        r = json.loads(m.group()) if m else base
        if not r.get("tema_principal") or r["tema_principal"].lower() in (
                "sesión general", "general", "conversación", "sesión", ""):
            r["tema_principal"] = r.get("proyecto_activo") or "conversación Satella"
        return r
    except Exception as e:
        log.error(f"[GEN] Síntesis falló: {e}")
        return base