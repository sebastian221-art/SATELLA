"""
nucleo/habilidades/python/detector.py
Decide si un mensaje es tarea de código y de qué tipo.
Conservador: ante la duda, NO secuestra la conversación normal.
"""
import re

_KW_GENERAR = (
    "creá", "crea", "creame", "creáme", "hacé", "haceme", "hazme", "generá", "genera",
    "escribí", "escribime", "programá", "programa", "implementá", "implementa",
    "armá", "arma", "necesito un", "necesito una", "dame un", "dame una",
)
_KW_ANALIZAR = (
    "analizá", "analiza", "revisá", "revisa", "qué hace", "que hace", "explicá", "explica",
    "mejorá", "mejora", "optimizá", "optimiza", "refactorizá", "refactoriza",
)
_KW_DEBUG = (
    "error", "falla", "no funciona", "por qué falla", "porque no", "bug", "traceback",
    "exception", "no anda", "arreglá", "arregla", "corregí", "corrige", "no corre",
)
_KW_EJECUTAR = (
    "corré", "correlo", "ejecutá", "ejecuta", "ejecutalo", "probá esto", "qué da", "que da",
    "qué devuelve", "qué imprime", "que imprime",
)
_NOUN_CODIGO = ("código", "codigo", "función", "funcion", "script", "clase",
                "programa", "algoritmo", "método", "metodo", "snippet")


def _limpiar_envoltura(s: str) -> str:
    """Saca envolturas que rompen el parseo: <...>, «...», comillas, backticks sueltos."""
    s = s.strip()
    pares = [("<", ">"), ("«", "»"), ("“", "”"), ('"', '"'), ("'", "'"), ("`", "`")]
    cambiado = True
    while cambiado and len(s) >= 2:
        cambiado = False
        for a, b in pares:
            if s.startswith(a) and s.endswith(b):
                s = s[1:-1].strip()
                cambiado = True
    return s


def _normalizar(codigo: str) -> str:
    """Convierte \\n / \\t literales a saltos reales si no hay saltos reales, y limpia envolturas."""
    codigo = _limpiar_envoltura(codigo)
    if "\\n" in codigo and "\n" not in codigo:
        codigo = codigo.replace("\\n", "\n").replace("\\t", "\t")
    return codigo


def extraer_codigo(texto: str) -> str:
    """Saca el bloque de código si viene entre ``` , tras 'dos puntos', o si el texto ES código."""
    m = re.search(r"```(?:python|py)?\s*(.*?)```", texto, re.DOTALL)
    if m:
        return _normalizar(m.group(1).strip())
    # inline: "corré esto: <código>" → tomar lo de después del primer ':'
    if ":" in texto:
        despues = texto.split(":", 1)[1].strip()
        if despues and hay_codigo(_normalizar(despues)):
            return _normalizar(despues)
    if hay_codigo(_normalizar(texto)):
        return _normalizar(texto.strip())
    return ""


_SEÑALES_FUERTES = ("```", "def ", "class ", "import ", "print(", "lambda ", "return ")
_SEÑALES_DEBILES = ("for ", "while ", "= [", "elif ", "self.", "    ", "\t", "==", "():")


def hay_codigo(texto: str) -> bool:
    if any(s in texto for s in _SEÑALES_FUERTES):
        return True
    return sum(s in texto for s in _SEÑALES_DEBILES) >= 2


_VERBOS_DATOS = ("ordená", "ordena", "ordenar", "calculá", "calcula", "calcular",
                 "leé", "lee", "leer", "parseá", "parsea", "parsear", "convertí",
                 "convierte", "convertir", "filtrá", "filtra", "filtrar", "contá",
                 "cuenta", "contar", "sumá", "suma", "sumar", "recorré", "recorre",
                 "recorrer", "transformá", "transforma", "agrupá", "agrupa",
                 "validá", "valida", "validar", "extraé", "extrae", "extraer",
                 "invertí", "invierte", "invertir", "sacá", "saca", "sacar",
                 "quitá", "quita", "quitar", "eliminá", "elimina", "eliminar",
                 "remové", "remueve", "remover", "uní", "une", "unir", "combiná",
                 "combina", "combinar", "dividí", "divide", "dividir", "separá",
                 "separa", "separar", "deduplicá", "deduplica")
_SUST_DATOS = ("lista", "listas", "archivo", "archivos", "csv", "json", "datos",
               "diccionario", "dict", "array", "tabla", "registros", "usuarios",
               "string", "cadena", "matriz", "columna", "fila", "números", "numeros")


_REQUEST_MARKERS = ("necesito", "quiero", "dame", "hacé", "hace", "haceme", "podés",
                    "podrias", "podrías", "ayudame", "ayúdame", "como hago", "cómo hago",
                    "escribime", "armá", "arma", "resolvé", "resolve", "necesitaria",
                    "necesitaría", "me das", "tengo que", "hay que")


def es_tarea_codigo(texto: str, codigo_adjunto: str = "") -> bool:
    t = texto.lower()
    if codigo_adjunto or hay_codigo(texto):
        return True
    menciona = any(n in t for n in _NOUN_CODIGO)
    pide = any(k in t for k in _KW_GENERAR + _KW_ANALIZAR + _KW_DEBUG + _KW_EJECUTAR)
    if menciona and pide:
        return True
    # Intención IMPLÍCITA por palabras: verbo de datos + sustantivo de datos.
    if any(v in t for v in _VERBOS_DATOS) and any(s in t for s in _SUST_DATOS):
        return True
    # Caso ambiguo: hay un pedido pero no calzó arriba → que decida el modelo.
    if any(mk in t for mk in _REQUEST_MARKERS):
        try:
            from . import clasificador
            es, _ = clasificador.clasificar(texto)
            return es
        except Exception:
            return False
    return False


def detectar_modo(texto: str, codigo_adjunto: str = "") -> str:
    t = texto.lower()
    tiene = bool(codigo_adjunto) or hay_codigo(texto)
    if tiene and any(k in t for k in _KW_EJECUTAR):
        return "ejecutar"
    if tiene and any(k in t for k in _KW_DEBUG):
        return "debug"
    if tiene and any(k in t for k in _KW_ANALIZAR):
        return "analisis"
    if tiene and not any(k in t for k in _KW_GENERAR):
        return "analisis"
    return "generacion"

# ── Detección de lenguaje (multi-lenguaje) ───────────────────────────────────
_LENG = [
    ("typescript", ("typescript", " tsx", ".tsx", " ts ", "react con tipos")),
    ("javascript", ("javascript", " js ", ".js", "node", "nodejs", "react", "vue")),
    ("html",       ("html", "página web", "pagina web", "landing", "css")),
    ("json",       ("json", "un json")),
    ("python",     ("python", "py ", ".py")),
]


def detectar_lenguaje(texto: str) -> str:
    """Adivina el lenguaje pedido. Default: python."""
    t = " " + (texto or "").lower() + " "
    for leng, marcas in _LENG:
        if any(m in t for m in marcas):
            return leng
    return "python"