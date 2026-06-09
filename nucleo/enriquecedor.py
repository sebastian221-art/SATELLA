"""
nucleo/enriquecedor.py — Capa lingüística de Echidna.
Combina NLTK WordNet + vocabulario propio para transformar
texto genérico en la voz precisa de Echidna.
Sin API. 0ms. Puro Python.
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
# Lema genérico → opciones en voz Echidna (rotativas, no siempre lo mismo)
VOCABULARIO = {
    # Verbos de percepción/cognición
    "creer":       ["sospechar", "intuir", "considerar"],
    "pensar":      ["intuir", "considerar", "razonar"],
    "ver":         ["observar", "percibir"],
    "notar":       ["percibir", "registrar"],          # "notar" → más preciso
    "parecer":     ["resultar", "volverse"],
    "entender":    ["comprender", "discernir"],
    "saber":       ["conocer", "tener claridad sobre"],
    # Adjetivos de valoración
    "interesante": ["fascinante"],                      # siempre este en Echidna
    "curioso":     ["fascinante", "peculiar"],
    "raro":        ["peculiar", "notable"],
    "bueno":       ["correcto", "acertado"],
    "malo":        ["incorrecto", "deficiente"],
    "importante":  ["relevante", "significativo"],
    "difícil":     ["complejo", "no trivial"],
    "fácil":       ["directo", "inmediato"],
    # Conectores / muletillas genéricas
    "básicamente": ["en términos precisos", "dicho con precisión"],
    "realmente":   ["genuinamente", "de hecho"],
    "simplemente": ["directamente", "sin rodeos"],
}

# ─── FRASES PROHIBIDAS — reemplazos directos ─────────────────────────────────
# Detectamos la frase completa y la sustituimos antes del vocabulario
_REEMPLAZOS_FRASES = [
    # Resúmenes
    (r"(?i)has identificado que", ""),
    (r"(?i)lo que describís sugiere", "lo que describís"),
    (r"(?i)tu frustración indica que", ""),
    (r"(?i)has señalado que", ""),
    (r"(?i)lo que observo es que", ""),
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
    # Exclamaciones al inicio de oración — Echidna es precisa, no entusiasta
    (r"^¡+", ""),               # ¡ al inicio del texto
    (r"\. ¡+", ". "),           # ¡ después de punto
    (r"! ¡+", ". "),            # !! doble exclamación
    (r"¡([A-ZÁÉÍÓÚ])", r"\1"), # ¡Palabra → Palabra (quita apertura)
    # Coach / poéticas
    (r"(?i)zona de resonancia", "zona de concentración"),
    (r"(?i)quietud nocturna", "silencio de la noche"),
    (r"(?i)potencia tu flujo", "te ayuda a concentrarte"),
    (r"(?i)núcleo de silencio", "silencio"),
    (r"(?i)ritual de inicio", "rutina de inicio"),
    # Corporativas
    (r"(?i)lo que encaja con tu", "lo que va con tu"),
    (r"(?i)resulta coherente con tu", "va con tu"),
    (r"(?i)armoniza con tu", "va con tu"),
    # Asistente
    (r"(?i)claro que sí", "sí"),
    (r"(?i)por supuesto", ""),
    (r"(?i)con gusto", ""),
    (r"(?i)espero haberte ayudado", ""),
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
    """Busca sinónimos en WordNet español para un lema dado."""
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
    """
    Sustituye palabras genéricas por vocabulario de Echidna.
    Usa spaCy para lematizar y respetar morfología.
    Fallback a búsqueda simple sin spaCy.
    """
    nlp = _get_nlp()

    if nlp is not None:
        doc = nlp(texto)
        resultado = list(texto)
        offset = 0

        for token in doc:
            lemma = token.lemma_.lower()
            if lemma in VOCABULARIO:
                opciones = VOCABULARIO[lemma]
                # Combinar con WordNet si está disponible
                extra = _wordnet_sinonimos(lemma)
                # Filtrar los WordNet que estén en nuestro vocabulario conocido
                opciones_filtradas = opciones  # priorizamos las nuestras
                reemplazo = random.choice(opciones_filtradas)

                # Solo sustituir si el token es largo (evitar "es", "va", etc.)
                if len(token.text) > 3:
                    inicio = token.idx + offset
                    fin    = inicio + len(token.text)
                    resultado[inicio:fin] = list(reemplazo)
                    offset += len(reemplazo) - len(token.text)

        return "".join(resultado)
    else:
        # Fallback sin spaCy — sustitución por palabras completas
        for lemma, opciones in VOCABULARIO.items():
            patron = r'\b' + re.escape(lemma) + r'\b'
            if re.search(patron, texto, re.IGNORECASE):
                reemplazo = random.choice(opciones)
                texto = re.sub(patron, reemplazo, texto, count=1, flags=re.IGNORECASE)
        return texto


def _limpiar_frases_prohibidas(texto: str) -> str:
    """Elimina o reemplaza frases que rompen la voz de Echidna."""
    for patron, reemplazo in _REEMPLAZOS_FRASES:
        texto = re.sub(patron, reemplazo, texto)
    # Limpiar espacios dobles que quedan después de eliminar frases
    texto = re.sub(r'  +', ' ', texto).strip()
    # Limpiar comas o puntos iniciales
    texto = re.sub(r'^[,\.\s]+', '', texto).strip()
    return texto


def enriquecer(texto: str, aplicar_vocabulario: bool = True) -> str:
    """
    Punto de entrada principal.
    Toma texto de Groq y lo transforma en voz Echidna.
    1. Elimina frases prohibidas
    2. Sustituye vocabulario genérico por registro Echidna
       (solo si el texto tiene más de 60 chars — evita romper respuestas cortas)
    """
    if not texto or len(texto) < 5:
        return texto

    # Paso 1: limpiar frases que rompen el personaje
    texto = _limpiar_frases_prohibidas(texto)

    # Paso 2: enriquecer vocabulario solo en respuestas largas
    # Respuestas cortas son frases completas — sustituir palabras las rompe
    if aplicar_vocabulario and len(texto) > 60:
        texto = _sustituir_vocabulario(texto)

    return texto.strip()


def instalar_nltk():
    """Descarga los recursos NLTK necesarios. Correr una vez."""
    try:
        import nltk
        nltk.download("wordnet")
        nltk.download("omw-1.4")
        print("✓ NLTK WordNet instalado")
    except Exception as e:
        print(f"Error instalando NLTK: {e}")


if __name__ == "__main__":
    instalar_nltk()
    # Test
    test = "Creo que eso es muy interesante. Me parece que tu enfoque es bueno."
    print("Original:", test)
    print("Enriquecido:", enriquecer(test))