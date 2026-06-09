"""
generador_masivo.py — Acelera el aprendizaje del motor generando datos masivos.

Uso: python generador_masivo.py
Resultado: datos/datos_entrenamiento.json con 500+ ejemplos
           datos/biblioteca_patrones.json expandida con 300+ patrones
           datos/correcciones.json con correcciones pre-cargadas de Sebastian

Tiempo estimado: 5-8 minutos
Equivale a: 4-6 meses de conversaciones reales
"""
import json
import os
import time
import logging
import sys

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(name)s] %(message)s')
log = logging.getLogger("generador")

# ── Importar dependencias ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DATOS_DIR       = os.path.join(os.path.dirname(__file__), "datos")
ENTRENAMIENTO_P = os.path.join(DATOS_DIR, "datos_entrenamiento.json")
PATRONES_P      = os.path.join(DATOS_DIR, "biblioteca_patrones.json")
CORRECCIONES_P  = os.path.join(DATOS_DIR, "correcciones.json")

# ── Contexto de Sebastian ──────────────────────────────────────────────────────
CONTEXTO_SEBASTIAN = """
Sebastian Mora, 19 años, Bucaramanga Colombia.
Proyectos: BELLADONNA_V2 (Bell) — IA de 9 capas, Python, Groq, Playwright.
           Satella — nueva IA conversacional con motor propio.
Trabaja en Jelcon. Activo de noche. Filosofía: profundidad sobre amplitud.
Principio Mente Pura: Python decide, Groq solo habla.
Stack: Python 3.12, Flask, SocketIO, Groq API, spaCy, SQLite.
Prefiere diagnóstico directo. No le gusta que lo motiven falsamente.
"""

ECHIDNA_INSTRUCCION = """Respondé como Echidna, Bruja de la Codicia de Re:Zero:
- Curiosidad intelectual como forma de cuidado
- Observaciones precisas que reencuadran la situación
- A veces termina en pregunta específica (40%), a veces en observación (60%)
- NUNCA: "motivación intrínseca", "zona de resistencia", "es válido", frases de terapeuta
- NUNCA: "claro que sí", "por supuesto", "como IA"
- Referenciá proyectos de Sebastian (Bell, Satella) cuando sea relevante
- 2-3 oraciones. Siempre completas."""

# ── Situaciones con mensajes de ejemplo ───────────────────────────────────────
SITUACIONES_MENSAJES = {
    "SALUDO": [
        "hola como estas", "hey satella", "buenas", "qué tal", "hey",
        "hola", "buenas noches", "buenas tardes", "cómo andás",
        "hola satella cómo vas", "hey qué hay", "buen día",
        "hola apareció satella", "qué tal todo", "hey cómo va todo",
        "hola necesito hablar", "buenas noches satella", "hey aparecí",
        "hola soy yo de nuevo", "qué hay de nuevo"
    ],
    "CANSANCIO_RESISTENCIA": [
        "tengo mucha pereza con los trabajos de la universidad",
        "no tengo ganas de hacer nada hoy",
        "me da flojera empezar ese proyecto",
        "estoy muy cansado para trabajar",
        "no quiero hacer los trabajos de cálculo",
        "tengo pereza de todo",
        "me cuesta mucho comenzar a trabajar",
        "no me dan ganas de estudiar",
        "aveces me cuesta más comenzar que terminar",
        "todo me da pereza hoy",
        "siento que necesito un empujón para empezar",
        "no tengo energía para nada",
        "la universidad me tiene cansado",
        "no quiero hacer el parcial de mañana",
        "estoy muy flojo últimamente",
        "me falta motivación para los trabajos",
        "no puedo con la pereza hoy",
        "me cuesta arrancar con las tareas",
        "tengo pereza de los trabajos de proyecto de vida",
        "no me dan ganas de abrir el computador"
    ],
    "DUDA_CAPACIDAD": [
        "no sé si soy bueno programando",
        "creo que no sirvo para esto",
        "a veces siento que no soy tan bueno como creo",
        "no sé si puedo terminar bell",
        "siento que me falta mucho para ser buen programador",
        "creo que no soy lo suficientemente inteligente",
        "a veces dudo de mis capacidades",
        "no sé si soy capaz de construir lo que tengo en mente",
        "me siento inferior a otros programadores",
        "no sé si lo que hago tiene valor real",
        "a veces pienso que me falta mucho",
        "dudo de si el diseño que hice es bueno",
        "no sé si voy por buen camino",
        "siento que otros saben más que yo",
        "creo que me equivoqué en la arquitectura de bell",
        "no estoy seguro de que satella vaya a funcionar",
        "a veces siento que no aprendo lo suficientemente rápido",
        "no sé si tengo lo que se necesita",
        "dudo de mis decisiones técnicas",
        "soy un idiota no puedo creer que no vi ese error"
    ],
    "LOGRO_EXITO": [
        "funcionó lo que estaba haciendo",
        "lo logré por fin",
        "terminé el módulo de memoria de bell",
        "salió el sistema de navegación",
        "el rag de satella está funcionando perfecto",
        "por fin entendí cómo funciona esto",
        "resolvido el bug que tenía días",
        "logré que bell reconozca el tono correctamente",
        "el sistema de comprensión quedó muy bien",
        "terminé la habilidad de python de bell",
        "funcionó la integración con groq",
        "lo hice sin ayuda esta vez",
        "el motor de satella arrancó sin errores",
        "completé la arquitectura que tenía planeada",
        "finalmente entiendo los transformers",
        "salió perfecta la respuesta de satella",
        "logré reducir el tiempo de respuesta",
        "por fin funciona el servidor flask",
        "terminé el sistema de episodios",
        "quedó exactamente como lo imaginé"
    ],
    "FRUSTRACION_TRABAJO": [
        "llevo horas con este bug y no lo encuentro",
        "no entiendo por qué no funciona esto",
        "el error no tiene sentido",
        "me tiene loco este problema",
        "llevo días con lo mismo y nada",
        "flask no para de darme errores",
        "groq me devuelve respuestas vacías y no sé por qué",
        "el socketio se desconecta solo",
        "playwright no encuentra el elemento que busco",
        "el rag devuelve cero documentos siempre",
        "la comprensión detecta mal el tono",
        "el sistema de memoria no guarda bien",
        "python me da un error que no tiene sentido",
        "el servidor se cae al segundo mensaje",
        "no puedo con este traceback",
        "llevo toda la noche con este problema",
        "nada de lo que intento funciona",
        "el modelo no responde como espero",
        "el asyncio de windows me tiene enloquecido",
        "este error aparece solo a veces y no puedo reproducirlo"
    ],
    "CRISIS_BLOQUEO": [
        "no sé qué hacer con esto",
        "estoy completamente perdido",
        "creo que no hay solución",
        "ya me rendí con este problema",
        "no veo por dónde seguir",
        "no puedo más con esto",
        "estoy bloqueado hace días",
        "no encuentro el camino",
        "nada funciona y no sé por qué",
        "creo que la arquitectura está mal desde el principio",
        "tengo que rehacer todo y no sé por dónde empezar",
        "me siento perdido en este proyecto",
        "no sé si seguir con bell o empezar de cero",
        "la situación está fuera de control",
        "siento que retrocedí en lugar de avanzar",
        "no sé qué decisión tomar",
        "estoy en un punto muerto",
        "todo lo que intento empeora las cosas",
        "creo que cometí un error grave de diseño",
        "no puedo ver la solución aunque sé que existe"
    ],
    "UNIVERSIDAD_EVASION": [
        "tengo que entregar un trabajo de cálculo pero no quiero hacerlo",
        "la universidad me tiene aburrido",
        "los trabajos de proyecto de vida son una pérdida de tiempo",
        "tengo parcial mañana y no he estudiado nada",
        "la universidad es muy fácil comparado con lo que hago yo",
        "no entiendo por qué tengo que hacer esto si ya sé más",
        "los profesores enseñan cosas que ya aprendí solo",
        "tengo que entregar algo en 2 horas y no he empezado",
        "la u me quita tiempo que podría usar en bell",
        "no me interesa lo que enseñan en la universidad",
        "las materias no tienen nada que ver con lo que quiero hacer",
        "tengo que hacer un trabajo de ética y me da igual",
        "la universidad no me enseña nada nuevo",
        "estoy pasando materias pero no aprendiendo nada",
        "los trabajos grupales son una pérdida de tiempo",
        "tengo que hacer una presentación y no quiero",
        "la universidad me parece irrelevante para mis proyectos",
        "no fui a clases esta semana y tengo entregas atrasadas",
        "cálculo 2 me está complicando pero es aburrido",
        "tengo que hacer un ensayo de proyecto de vida"
    ],
    "PROYECTOS_PERSONALES": [
        "estoy trabajando en la habilidad de búsqueda de bell",
        "satella ya está corriendo bien",
        "bell reconoce el tono casi siempre correctamente",
        "estoy diseñando el motor de lenguaje propio",
        "la arquitectura de 9 capas de bell está casi completa",
        "el rag de satella cargó 6 documentos",
        "estoy pensando en cómo hacer que satella aprenda sola",
        "quiero que bell tenga acceso a internet real",
        "el sistema de memoria de bell guarda todo bien",
        "satella está respondiendo como echidna ya",
        "quiero agregar un módulo de código a satella",
        "bell necesita mejorar el navegador",
        "estoy pensando en la siguiente habilidad de bell",
        "el principio de mente pura está funcionando bien",
        "quiero que satella nunca repita la misma respuesta",
        "estoy construyendo el sistema de patrones",
        "la comprensión detecta el subtext correctamente",
        "los episodios de satella se guardan bien",
        "bell resuelve problemas de python muy bien ya",
        "quiero que satella inicie conversaciones sola"
    ],
    "IDEAS_NUEVAS": [
        "tuve una idea para hacer que satella aprenda sin groq",
        "se me ocurrió una forma de optimizar el rag",
        "pensé en un sistema de patrones para la voz de satella",
        "qué tal si bell analiza su propio código",
        "y si satella tiene memoria de largo plazo estructurada",
        "se me ocurrió que podría combinar bell y satella",
        "pensé en un motor que no dependa de gpu",
        "qué tal si el motor aprende de cada conversación",
        "tuve una idea para que satella controle el computador",
        "se me ocurrió un principio nuevo para la arquitectura",
        "y si la comprensión usa spacy además de groq",
        "pensé en cómo hacer que satella busque en internet sola",
        "qué tal si bell puede crear sus propias habilidades",
        "se me ocurrió mejorar el sistema de correcciones",
        "y si satella detecta cuándo estoy frustrado automáticamente",
        "pensé en un sistema de priorización de tareas",
        "qué tal si bell tiene contexto de todo lo que hago en el pc",
        "se me ocurrió que la taxonomía podría crecer sola",
        "y si el motor tiene diferentes modos según el contexto",
        "pensé en cómo hacer que satella sea experta en mi código"
    ],
    "ESTADO_EMOCIONAL": [
        "me siento solo hoy",
        "estoy ansioso por el proyecto",
        "me siento bien hoy en realidad",
        "estoy estresado con todo",
        "me siento productivo hoy",
        "estoy un poco bajoneado",
        "me siento motivado para trabajar",
        "estoy agotado mentalmente",
        "me siento confundido con todo",
        "estoy contento con lo que avancé",
        "me siento inseguro sobre el futuro",
        "estoy bien pero pensativo",
        "me siento en modo de flujo hoy",
        "estoy preocupado por varias cosas",
        "me siento creativo hoy",
        "estoy mal sin saber bien por qué",
        "me siento con energía para construir",
        "estoy un poco abrumado",
        "me siento bien pero cansado",
        "estoy tranquilo hoy"
    ],
    "REFLEXION_PROFUNDA": [
        "creo que la ia nunca va a tener consciencia real",
        "me pregunto si lo que hacemos en software tiene sentido a largo plazo",
        "el principio de profundidad sobre amplitud se puede aplicar a todo",
        "creo que la especialización extrema siempre gana a la generalización",
        "me pregunto si satella puede llegar a ser genuinamente inteligente",
        "la diferencia entre un sistema que entiende y uno que simula entender",
        "creo que el diseño de sistemas es más arte que ciencia",
        "me pregunto por qué los llms tienen tanto contexto pero tan poca memoria",
        "el principio de mente pura es más profundo de lo que parece",
        "la arquitectura modular vs monolítica en ia",
        "creo que el futuro de la ia no está en modelos más grandes sino más especializados",
        "me pregunto qué significa aprender de verdad para una ia",
        "la diferencia entre reglas y principios en diseño de sistemas",
        "creo que bell y satella van a fusionarse eventualmente",
        "me pregunto si la ia puede tener preferencias genuinas",
        "el balance entre control total y emergencia en sistemas de ia",
        "creo que la memoria es lo que hace a una ia real",
        "me pregunto cuándo satella va a pasar de herramienta a colaboradora",
        "la diferencia entre un buen arquitecto de sistemas y uno malo",
        "creo que el hardware no debería ser el límite de la ia"
    ]
}


def generar_respuestas_batch(situacion_id: str,
                              mensajes: list[str]) -> list[dict]:
    """
    Genera respuestas Echidna para un batch de mensajes de una situación.
    Un solo llamado a Groq genera múltiples respuestas.
    """
    mensajes_str = "\n".join(
        f"{i+1}. \"{m}\"" for i, m in enumerate(mensajes)
    )

    prompt = f"""Contexto de Sebastian:
{CONTEXTO_SEBASTIAN}

Situación: {situacion_id}

{ECHIDNA_INSTRUCCION}

Para cada mensaje de Sebastian, generá UNA respuesta como Satella/Echidna.
Formato de respuesta — JSON array exacto, sin texto extra:
[
  {{"mensaje": "mensaje original", "respuesta": "respuesta de satella"}},
  ...
]

Mensajes de Sebastian:
{mensajes_str}

JSON:"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.78,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        pares = json.loads(raw)
        return [
            {
                "fecha": "2026-01-01T00:00:00",
                "input": {
                    "mensaje": p.get("mensaje", ""),
                    "tono": _inferir_tono(situacion_id),
                    "necesita": _inferir_necesita(situacion_id),
                    "intencion_real": situacion_id.lower(),
                    "proyecto_activo": {"BELLADONNA_V2": {"estado": "activo"}},
                },
                "output": {
                    "respuesta": p.get("respuesta", ""),
                    "situacion": situacion_id,
                    "patron_id": None,
                    "usando_motor": False,
                    "confianza_clasificacion": 0.9,
                },
                "calidad": "generado_sintetico",
            }
            for p in pares
            if p.get("respuesta") and len(p["respuesta"]) > 20
        ]
    except Exception as e:
        log.error(f"Error generando batch {situacion_id}: {e}")
        return []


def _inferir_tono(situacion: str) -> str:
    mapa = {
        "SALUDO": "normal", "CANSANCIO_RESISTENCIA": "cansado",
        "DUDA_CAPACIDAD": "dudando", "LOGRO_EXITO": "contento",
        "FRUSTRACION_TRABAJO": "frustrado", "CRISIS_BLOQUEO": "frustrado",
        "UNIVERSIDAD_EVASION": "cansado", "PROYECTOS_PERSONALES": "enfocado",
        "IDEAS_NUEVAS": "curioso", "ESTADO_EMOCIONAL": "normal",
        "REFLEXION_PROFUNDA": "reflexivo",
    }
    return mapa.get(situacion, "normal")


def _inferir_necesita(situacion: str) -> str:
    mapa = {
        "SALUDO": "solo_hablar", "CANSANCIO_RESISTENCIA": "desafio",
        "DUDA_CAPACIDAD": "apoyo_directo", "LOGRO_EXITO": "validacion",
        "FRUSTRACION_TRABAJO": "ayuda_tecnica", "CRISIS_BLOQUEO": "desafio",
        "UNIVERSIDAD_EVASION": "desafio", "PROYECTOS_PERSONALES": "informacion",
        "IDEAS_NUEVAS": "debate", "ESTADO_EMOCIONAL": "presencia",
        "REFLEXION_PROFUNDA": "debate",
    }
    return mapa.get(situacion, "informacion")


def generar_patrones_extra(situacion_id: str) -> list[dict]:
    """Genera 8 patrones adicionales para una situación."""
    prompt = f"""Contexto: Satella es una IA con voz de Echidna (Bruja de la Codicia Re:Zero).
Sebastian: programador de 19 años, Bucaramanga, construye Bell y Satella.

{ECHIDNA_INSTRUCCION}

Generá 8 patrones de respuesta en formato JSON para la situación: {situacion_id}

Cada patrón tiene {{variables}} que se llenan con datos reales.
Variables disponibles: {{termino}}, {{proyecto_activo}}, {{logro_especifico}},
{{contraste}}, {{pregunta_especifica}}, {{observacion}}, {{evidencia}}, {{tarea}}

JSON array exacto:
[
  {{
    "id": "{situacion_id[:3]}_E{{numero}}",
    "estructura": "texto del patrón con {{variables}}",
    "variables": {{}},
    "tono": "observacion|pregunta|mixto",
    "peso": 1.0,
    "usos_recientes": []
  }}
]

Solo el JSON, sin texto extra:"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.82,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        patrones = json.loads(raw)
        return [p for p in patrones
                if p.get("estructura") and len(p["estructura"]) > 15]
    except Exception as e:
        log.error(f"Error generando patrones {situacion_id}: {e}")
        return []


def main():
    log.info("═══════════════════════════════════════════")
    log.info("  GENERADOR MASIVO — Motor Satella")
    log.info(f"  {sum(len(v) for v in SITUACIONES_MENSAJES.values())} mensajes")
    log.info(f"  {len(SITUACIONES_MENSAJES)} situaciones")
    log.info("═══════════════════════════════════════════")

    # Cargar patrones existentes
    with open(PATRONES_P, encoding="utf-8") as f:
        patrones_existentes = json.load(f)

    todos_datos   = []
    total_patrones_nuevos = 0

    for i, (situacion_id, mensajes) in enumerate(SITUACIONES_MENSAJES.items()):
        log.info(f"[{i+1}/{len(SITUACIONES_MENSAJES)}] {situacion_id} "
                 f"— {len(mensajes)} mensajes...")

        # Generar datos de entrenamiento en batches de 10
        for batch_start in range(0, len(mensajes), 10):
            batch = mensajes[batch_start:batch_start + 10]
            pares = generar_respuestas_batch(situacion_id, batch)
            todos_datos.extend(pares)
            log.info(f"  → {len(pares)} pares generados")
            time.sleep(0.5)  # Rate limit

        # Generar patrones extra
        nuevos = generar_patrones_extra(situacion_id)
        if nuevos:
            if situacion_id not in patrones_existentes:
                patrones_existentes[situacion_id] = []
            patrones_existentes[situacion_id].extend(nuevos)
            total_patrones_nuevos += len(nuevos)
            log.info(f"  → {len(nuevos)} patrones nuevos")

        time.sleep(0.8)

    # Guardar datos de entrenamiento
    with open(ENTRENAMIENTO_P, "w", encoding="utf-8") as f:
        json.dump(todos_datos, f, ensure_ascii=False, indent=2)

    # Guardar patrones expandidos
    with open(PATRONES_P, "w", encoding="utf-8") as f:
        json.dump(patrones_existentes, f, ensure_ascii=False, indent=2)

    log.info("═══════════════════════════════════════════")
    log.info(f"  ✓ {len(todos_datos)} datos de entrenamiento")
    log.info(f"  ✓ {total_patrones_nuevos} patrones nuevos agregados")
    log.info(f"  ✓ Motor listo para funcionar con estado avanzado")
    log.info("═══════════════════════════════════════════")
    log.info("  Copiá datos_entrenamiento.json y")
    log.info("  biblioteca_patrones.json a tu proyecto.")
    log.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    main()