"""
nucleo/enriquecedor.py — Capa lingüística de Echidna.
Fix crítico: las exclamaciones ¡ de Echidna (¡Jajaja!, ¡Ahah!) ahora sobreviven.
Solo se eliminan exclamaciones específicas de asistente genérico.
"""
import re
import random
import logging
from typing import Optional

log = logging.getLogger("satella.enriquecedor")

# ─── NLTK — descarga silenciosa si no está ────────────────────────────────────
_wordnet_ok = False
try:
    import nltk
    from nltk.corpus import wordnet as wn
    try:
        wn.synsets("fascinante", lang="spa")
        _wordnet_ok = True
    except Exception:
        nltk.download("wordnet",  quiet=True)
        nltk.download("omw-1.4", quiet=True)
        try:
            wn.synsets("fascinante", lang="spa")
            _wordnet_ok = True
        except Exception:
            _wordnet_ok = False
except ImportError:
    _wordnet_ok = False

# ─── VOCABULARIO ECHIDNA ──────────────────────────────────────────────────────
VOCABULARIO = {
    "creer":       ["sospechar", "intuir", "considerar"],
    "pensar":      ["intuir", "considerar", "razonar"],
    "ver":         ["observar", "percibir"],
    "notar":       ["percibir", "registrar"],
    "parecer":     ["resultar", "volverse"],
    "entender":    ["comprender", "discernir"],
    "saber":       ["conocer", "tener claridad sobre"],
    "interesante": ["fascinante"],
    "curioso":     ["fascinante", "peculiar"],
    "raro":        ["peculiar", "notable"],
    "bueno":       ["correcto", "acertado"],
    "malo":        ["incorrecto", "deficiente"],
    "importante":  ["relevante", "significativo"],
    "difícil":     ["complejo", "no trivial"],
    "fácil":       ["directo", "inmediato"],
    "básicamente": ["en términos precisos", "dicho con precisión"],
    "realmente":   ["genuinamente", "de hecho"],
    "simplemente": ["directamente", "sin rodeos"],
}

# ─── FRASES PROHIBIDAS — reemplazos directos ─────────────────────────────────
# IMPORTANTE: las ¡ de Echidna (¡Jajaja!, ¡Ahah!, ¡Fascinante!) NO se tocan.
# Solo se eliminan las exclamaciones específicas de asistente genérico.
_REEMPLAZOS_FRASES = [
    # Resúmenes — frases de asistente que repiten lo que dijo Sebastian
    (r"(?i)has identificado que", ""),
    (r"(?i)lo que describís sugiere", "lo que describís"),
    (r"(?i)tu frustración indica que", ""),
    (r"(?i)has señalado que", ""),
    (r"(?i)lo que observo es que", ""),
    (r"(?i)lo que señalás es que", ""),
    (r"(?i)la pausa que mencionaste sugiere", ""),

    # Exclamaciones específicas de asistente — SOLO estas, no toda ¡
    (r"(?i)^¡[Cc]laro[!,\s]", ""),
    (r"(?i)^¡[Pp]or supuesto[!,\s]", ""),
    (r"(?i)^¡[Ee]ntendido[!,\s]", ""),
    (r"(?i)^¡[Pp]erfecto[!,\s]", ""),
    (r"(?i)^¡[Gg]enial[!,\s]", ""),
    (r"(?i)^¡[Ee]xcelente[!,\s]", ""),
    (r"(?i)^¡[Ss]uper[!,\s]", ""),

    # Me alegra — frase de asistente
    (r"(?i)me alegra (que|poder|haber|conocer|tener)[^.!?]*[.!?]?", ""),
    (r"(?i)me alegra[^.!?]*[.!?]", ""),

    # Stage directions / acotaciones teatrales
    (r"\([Ss]ilencio[^)]*\)", ""),
    (r"\([Pp]ausa[^)]*\)", ""),
    (r"\([Rr]íe[^)]*\)", ""),
    (r"\([Ss]e detiene[^)]*\)", ""),
    (r"\([Pp]iensa[^)]*\)", ""),

    # Describe al personaje desde afuera
    (r"(?i)como echidna se supone[^.!?]*[.!?]?", ""),
    (r"(?i)como se supone que debo", "como debo"),

    # Coach / poéticas que no suenan a Echidna
    (r"(?i)zona de resonancia", "zona de concentración"),
    (r"(?i)quietud nocturna", "silencio de la noche"),
    (r"(?i)potencia tu flujo", "te ayuda a concentrarte"),
    (r"(?i)núcleo de silencio", "silencio"),
    (r"(?i)ritual de inicio", "rutina de inicio"),
    (r"(?i)motivación intrínseca", "lo que te mueve"),

    # Corporativas
    (r"(?i)lo que encaja con tu", "lo que va con tu"),
    (r"(?i)resulta coherente con tu", "va con tu"),
    (r"(?i)armoniza con tu", "va con tu"),

    # Asistente
    (r"(?i)claro que sí", "sí"),
    (r"(?i)por supuesto", ""),
    (r"(?i)con gusto", ""),
    (r"(?i)espero haberte ayudado", ""),
    (r"(?i)si necesitas algo más", ""),

    # Tercera persona sobre Sebastian
    (r"\bsu proyecto\b", "tu proyecto"),
    (r"\bsu arquitectura\b", "tu arquitectura"),
    (r"\bsu enfoque\b", "tu enfoque"),
    (r"\bsu manera\b", "tu manera"),
]

# ─── spaCy opcional ───────────────────────────────────────────────────────────
_nlp = None
def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        try:    _nlp = spacy.load("es_core_news_sm")
        except: _nlp = spacy.blank("es")
    except:
        _nlp = None
    return _nlp


def _wordnet_sinonimos(lemma: str) -> list:
    if not _wordnet_ok:
        return []
    try:
        synsets = wn.synsets(lemma, lang="spa")
        sinonimos = []
        for s in synsets[:3]:
            for l in s.lemmas("spa"):
                nombre = l.name().replace("_", " ")
                if nombre != lemma and nombre not in sinonimos:
                    sinonimos.append(nombre)
        return sinonimos[:5]
    except Exception:
        return []


def _sustituir_vocabulario(texto: str) -> str:
    nlp = _get_nlp()

    if nlp is not None:
        doc = nlp(texto)
        resultado = list(texto)
        offset = 0

        for token in doc:
            lemma = token.lemma_.lower()
            if lemma in VOCABULARIO:
                opciones = VOCABULARIO[lemma]
                reemplazo = random.choice(opciones)
                if len(token.text) > 3:
                    inicio = token.idx + offset
                    fin    = inicio + len(token.text)
                    resultado[inicio:fin] = list(reemplazo)
                    offset += len(reemplazo) - len(token.text)

        return "".join(resultado)
    else:
        for lemma, opciones in VOCABULARIO.items():
            patron = r'\b' + re.escape(lemma) + r'\b'
            if re.search(patron, texto, re.IGNORECASE):
                reemplazo = random.choice(opciones)
                texto = re.sub(patron, reemplazo, texto, count=1, flags=re.IGNORECASE)
        return texto


def _limpiar_frases_prohibidas(texto: str) -> str:
    for patron, reemplazo in _REEMPLAZOS_FRASES:
        texto = re.sub(patron, reemplazo, texto)
    texto = re.sub(r'  +', ' ', texto).strip()
    texto = re.sub(r'^[,\.\s]+', '', texto).strip()
    return texto


def enriquecer(texto: str, aplicar_vocabulario: bool = True) -> str:
    """
    Transforma texto de Groq en voz Echidna.
    1. Elimina frases prohibidas (¡Claro!, ¡Por supuesto!, resúmenes, stage directions)
    2. Sustituye vocabulario genérico por registro Echidna (solo si > 60 chars)
    
    NOTA: ¡Jajaja!, ¡Ahah!, ¡Fascinante! y otras ¡ de Echidna NO se tocan.
    """
    if not texto or len(texto) < 5:
        return texto

    texto = _limpiar_frases_prohibidas(texto)

    if aplicar_vocabulario and len(texto) > 60:
        texto = _sustituir_vocabulario(texto)

    return texto.strip()


def instalar_nltk():
    try:
        import nltk
        nltk.download("wordnet")
        nltk.download("omw-1.4")
        print("✓ NLTK WordNet instalado")
    except Exception as e:
        print(f"Error instalando NLTK: {e}")


if __name__ == "__main__":
    instalar_nltk()
    tests = [
        "¡Jajaja, qué inmediato es que te quejes! ¿Qué esperabas exactamente?",
        "¡Ahah! No es que me gusten los arrebatos.",
        "¡Claro que sí! Me alegra que lo notes.",
        "¡Por supuesto! Con gusto te ayudo con eso.",
        "Me alegra que hayas identificado el problema. Lo que describís sugiere un patrón.",
    ]
    print("=== TEST ENRIQUECEDOR ===")
    for t in tests:
        resultado = enriquecer(t)
        changed = " [CAMBIÓ]" if resultado != t else " [SIN CAMBIO]"
        print(f"ORIG:  {t}")
        print(f"RESUL: {resultado}{changed}")
        print()