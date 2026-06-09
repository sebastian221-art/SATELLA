"""
nucleo/motor_satella.py — Motor independiente de Satella. v2.
100% sin Groq. 100% sin API externa. Corre en cualquier hardware.
Corrige: normalización de acentos, nombres de categorías, vocab calibrado.
"""
import re, math, random, logging
from typing import Optional

log = logging.getLogger("satella.motor_satella")

try:
    from nucleo.estado_conversacion import EstadoConversacion
    from nucleo.voces_motor import SelectorVoz, componer_respuesta
except ImportError:
    from estado_conversacion import EstadoConversacion
    from voces_motor import SelectorVoz, componer_respuesta


def _norm(texto: str) -> str:
    """Normaliza acentos y pasa a minúsculas. Robusto en Windows y Linux."""
    t = texto.lower()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n'),('ü','u')]:
        t = t.replace(a, b)
    return t


class ClasificadorContextual:

    _STOP = frozenset({
        'que','con','los','las','del','una','por','para','son','sus','nos','mas',
        'pero','como','esta','este','esto','ser','hay','fue','han','tiene','van',
        'sea','muy','bien','cuando','donde','porque','sobre','entre','todo','cada',
        'solo','sin','me','te','se','le','lo','la','un','de','en','el','al',
        'y','o','a','e','mi','tu','su','si','ya','no','ni','eso','esa',
    })

    _VOCAB = {
        "siendo_probada":   ["prueba","probar","demostrar","convencer","medir","evaluar",
                             "profundidad","personalidad","capacidad","limites","ver si",
                             "comprobar","testeando","a prueba","puedes hacer","cuanto"],
        "logro":            ["funciono","logre","resolvi","termine","consegui","listo",
                             "marcha","funciona","tengo listo","lo tengo","al fin"],
        "duda_capacidad":   ["incapaz","sirvo","suficiente","merezco","competente",
                             "tengo lo","no sirvo","no soy bueno","no soy capaz","me falta"],
        "frustracion":      ["frustrado","falla","error","roto","mal","loco","harto",
                             "imposible","fallando","no anda","sin matchear","no responde"],
        "bloqueo":          ["bloqueado","trabado","estancado","varado","no encuentro",
                             "no veo","no avanzo","parado","no se como","mismo punto"],
        "pereza":           ["pereza","flojo","arrancar","empezar","motivacion","energia",
                             "cuesta empezar","cuesta arrancar","no puedo empezar"],
        "ideas":            ["idea","ocurrio","pense","nueva","diferente","alternativa",
                             "se me ocurrio","nueva forma","nueva idea"],
        "decision":         ["elegir","decidir","opcion","alternativa","debo","deberia",
                             "no se cual","escoger","cual usar"],
        "mira_algo":        ["mira","fijate","mostrarte","te muestro","fijate esto",
                             "mira como","esto que hice","esto que logre"],
        "pregunta_opinion": ["pensas","piensas","opinas","crees","dime que piensas"],
        "saludo":           ["hola","buenas","hey","como estas","como andas"],
        "despedida":        ["chao","adios","hasta luego","bye","nos vemos"],
        "filosofia":        ["principio","filosofia","profundidad","amplitud","mente pura",
                             "concepto","abstraccion"],
        "conciencia":       ["consciente","consciencia","existo","soy real"],
        "noche":            ["madrugada","trasnochando","3am","2am","1am","4am",
                             "todavia aca","sigo despierto","sigo aca"],
        "descanso":         ["dormir","descansar","cama","hora dormir"],
        "sobre_satella":    ["quien eres","que sos","que haces","capacidades",
                             "como funcionas","como aprendes","que puedes"],
        "sobre_sebastian":  ["piensas de mi","como me ves","que ves en mi","sin filtros"],
        "cansancio":        ["cansado","agotado","sin energia","no puedo mas"],
        "nuevo_reflexivo":  ["pienso que","creo que","me parece","me doy cuenta",
                             "he estado pensando","a veces siento"],
    }

    # Triggers exactos — normalizados sin acentos para comparación robusta
    _TRIGGERS = {
        "siendo_probada": [
            "que tan bien puedes","que tanto puedes","a ver que tan","poner a prueba",
            "a ver si podes","demostrame que","probame que","convenceme","a prueba",
            "seguimos en prueba","probar tus respuestas","quiero ver si",
        ],
        "logro":           ["lo logre","funciono","por fin","lo resolvi","salio bien","lo hice"],
        "duda_capacidad":  ["no se si soy","no se si sirvo","dudo de mi","me siento incapaz","soy suficientemente"],
        "frustracion":     ["estoy frustrado","sigue fallando","me tiene loco","no puedo con esto","sin matchear"],
        "pereza":          ["tengo pereza","me da pereza","no tengo ganas","no me dan ganas"],
        "bloqueo":         ["estoy bloqueado","me trabe","no se como continuar","estancado","no encuentro la solucion"],
        "ideas":           ["tuve una idea","se me ocurrio","nueva idea","que tal si"],
        "saludo":          ["hola","buenas","hey"],
        "despedida":       ["chao","hasta luego","hasta manana","me despido","nos vemos"],
        "descanso":        ["me voy a dormir","necesito descansar","hora de dormir"],
        "noche":           ["son las 2am","son las 3am","son las 4am","son las 1am",
                            "3am","2am","1am","4am","madrugada","trasnochando"],
        "mira_algo":       ["mira esto","mira lo que","mira como","te muestro","fijate esto",
                            "esto que hice","esto que logre","mirá esto"],
        "pregunta_opinion":["que pensas de","que piensas de","que opinas de",
                            "que te parece","dime que pensas","dime que piensas"],
        "sobre_satella":   ["como funcionas","que puedes hacer","tus capacidades","como aprendes"],
        "sobre_sebastian": ["que piensas de mi","como me ves","que ves en mi"],
        "filosofia":       ["profundidad sobre amplitud","mente pura","principio de"],
        "conciencia":      ["eres consciente","sos consciente","conciencia artificial"],
    }

    @classmethod
    def _tokens(cls, texto: str) -> frozenset:
        t = _norm(texto)
        words = re.findall(r'\b[a-z]{2,}\b', t)
        return frozenset(w for w in words if w not in cls._STOP)

    @classmethod
    def _score(cls, tokens_msg: frozenset, tipo: str) -> float:
        vocab = cls._VOCAB.get(tipo, [])
        if not vocab:
            return 0.0
        tokens_v = cls._tokens(' '.join(vocab))
        if not tokens_msg or not tokens_v:
            return 0.0
        overlap = tokens_msg & tokens_v
        if not overlap:
            return 0.0
        return len(overlap) / math.sqrt(len(tokens_msg) * len(tokens_v))

    @classmethod
    def clasificar(cls, mensaje: str, estado: 'EstadoConversacion') -> dict:
        ml_orig = mensaje.lower()
        ml      = _norm(mensaje)          # sin acentos para comparar triggers
        tokens  = cls._tokens(mensaje)

        # ── 1. Seguimiento: Sebastian pregunta sobre lo que dijo Satella ──────
        if estado.es_seguimiento(mensaje) and estado.ultimo_satella():
            return {"tipo":"seguimiento","emocion":"curioso",
                    "necesita":"clarificacion","voz":"echidna"}

        # ── 2. Triggers exactos (normalizados) ───────────────────────────────
        for tipo, frases in cls._TRIGGERS.items():
            if any(_norm(f) in ml for f in frases):
                log.debug(f"[CLF] trigger → {tipo}")
                return {
                    "tipo": tipo,
                    "emocion": cls._emocion(ml),
                    "necesita": cls._necesidad(tipo),
                    "voz": cls._voz(tipo, cls._emocion(ml), cls._necesidad(tipo)),
                }

        # ── 3. Motor semántico ───────────────────────────────────────────────
        mejor, score_max = None, 0.0
        for tipo in cls._VOCAB:
            s = cls._score(tokens, tipo)
            if s > score_max:
                score_max, mejor = s, tipo

        if score_max >= 0.12 and mejor:
            log.debug(f"[CLF] semantico → {mejor} ({score_max:.3f})")
            return {
                "tipo": mejor,
                "emocion": cls._emocion(ml),
                "necesita": cls._necesidad(mejor),
                "voz": cls._voz(mejor, cls._emocion(ml), cls._necesidad(mejor)),
            }

        # ── 4. Default ───────────────────────────────────────────────────────
        tipo_d = "saludo" if len(mensaje.split()) <= 3 else (
                 "nuevo_casual" if len(mensaje.split()) <= 7 else "nuevo_reflexivo")
        return {"tipo":tipo_d,"emocion":cls._emocion(ml),
                "necesita":"info","voz":"echidna"}

    @staticmethod
    def _emocion(ml: str) -> str:
        if any(w in ml for w in ["frustrado","loco","harto","no puedo","me tiene"]):
            return "frustrado"
        if any(w in ml for w in ["funciono","logre","salio","por fin"]):
            return "contento"
        if any(w in ml for w in ["no se","dudo","incapaz","no sirvo"]):
            return "dudando"
        if any(w in ml for w in ["cansado","sueno","pereza","agotado"]):
            return "cansado"
        return "neutral"

    @staticmethod
    def _necesidad(tipo: str) -> str:
        return {
            "siendo_probada":"desafio","logro":"validacion",
            "duda_capacidad":"apoyo_directo","frustracion":"ayuda_tecnica",
            "bloqueo":"ayuda_tecnica","pereza":"desafio",
            "descanso":"apoyo_directo",
        }.get(tipo, "info")

    @staticmethod
    def _voz(tipo: str, emocion: str, necesita: str) -> str:
        if tipo in ("pereza",) or emocion == "flojo":
            return "ram"
        if tipo in ("duda_capacidad","cansancio") or (emocion=="dudando" and necesita=="apoyo_directo"):
            return "rem"
        if tipo == "confusion_objetivo":
            return "emilia"
        return "echidna"


class AprendizContinuo:
    def __init__(self):
        self._historial: list = []
        self._pesos:    dict  = {}
        self._ultimo:   Optional[dict] = None

    def registrar(self, msg: str, resp: str, clf: dict, snap: dict):
        r = {"msg":msg[:100],"resp":resp[:150],"tipo":clf.get("tipo"),"voz":clf.get("voz")}
        self._historial = (self._historial + [r])[-200:]
        self._ultimo = r

    def feedback(self, positivo: bool):
        if not self._ultimo:
            return
        k = self._ultimo.get("tipo","default")
        d = 0.05 if positivo else -0.03
        self._pesos[k] = max(0.1, min(2.0, self._pesos.get(k, 1.0) + d))
        log.info(f"[APRENDIZ] {'✓' if positivo else '✗'} {k} → {self._pesos[k]:.2f}")


class MotorSatella:
    """Motor 100% independiente de Groq. <1ms por mensaje. Cualquier hardware."""

    def __init__(self):
        self.estado   = EstadoConversacion()
        self._clf     = ClasificadorContextual()
        self.aprendiz = AprendizContinuo()
        self._recientes: list[str] = []
        log.info("[MOTOR_SATELLA] iniciado — sin Groq")

    def procesar(self, mensaje: str) -> str:
        self.estado.registrar("sebastian", mensaje)
        clf = self._clf.clasificar(mensaje, self.estado)
        tipo = clf["tipo"]

        voz = SelectorVoz.seleccionar(
            tipo_mensaje=tipo,
            emocion=clf.get("emocion","neutral"),
            necesita=clf.get("necesita","info"),
        )
        log.info(f"[MOTOR] tipo={tipo} | voz={voz}")

        ctx = self.estado.contexto_para_compositor()
        ctx.update({"tipo_mensaje": tipo, "voz": voz})

        respuesta = self._generar_sin_repetir(voz, tipo, ctx)
        self.estado.registrar("satella", respuesta)
        self.aprendiz.registrar(mensaje, respuesta, clf, self.estado.snapshot())
        log.info(f"[MOTOR] → ({len(respuesta)}c) {respuesta[:55]}")
        return respuesta

    def feedback(self, positivo: bool):
        self.aprendiz.feedback(positivo)

    def resetear_sesion(self):
        self.estado = EstadoConversacion()
        self._recientes = []

    def _generar_sin_repetir(self, voz: str, tipo: str, ctx: dict) -> str:
        for _ in range(4):
            r = componer_respuesta(voz, tipo, ctx)
            if r and r not in self._recientes:
                self._recientes = (self._recientes + [r])[-6:]
                return r
        return componer_respuesta(voz, "default", ctx)


# ── Interfaz para generacion.py ───────────────────────────────────────────────
_motor_global: Optional[MotorSatella] = None

def obtener_motor() -> MotorSatella:
    global _motor_global
    if _motor_global is None:
        _motor_global = MotorSatella()
    return _motor_global

def generar_motor(mensaje: str) -> Optional[str]:
    return obtener_motor().procesar(mensaje)

def resetear_motor():
    obtener_motor().resetear_sesion()