"""
nucleo/habilidades/analisis/detector.py
Detecta pedidos de ANÁLISIS de webs / APIs / sistemas / arquitecturas.
Específico a propósito: exige un verbo de análisis + (una URL o un sustantivo
de "cosa analizable"). Así no le roba a la habilidad de código ("analizá este
código") ni a la de sentimiento ("analizá el sentimiento").
"""
import re

_VERBOS = (
    "analiz", "analís", "estudia", "estudiá", "inspeccion", "revis",
    "examin", "cómo funciona", "como funciona", "qué hace", "que hace",
    "describí cómo", "describi como", "document", "desglos", "audit",
)
_NOUNS = (
    "web", "página", "pagina", "sitio", "url", " api", "endpoint", "sistema",
    "arquitectura", "login", "formulario", "html", "frontend", "back-end",
    "backend", "servicio", "landing", "dominio", " app ",
)
_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_HTML = re.compile(r"<!doctype html|<html|<head|<body|<div|<form|<script", re.IGNORECASE)

# Verbos de COPIA: si aparecen, el pedido es para la habilidad copia, no análisis.
_VERBOS_COPIA = ("copiá", "copia", "copialo", "copiar", "reproducí", "reproduce",
                 "reproducir", "recreá", "recrea", "replicá", "replica", "replicar",
                 "imitá", "imita", "imitar", "cloná", "clona", "clonar",
                 "reimplementá", "reimplementa", "equivalente de", "equivalente liviano")


def _t(texto):
    return " " + (texto or "").lower().strip() + " "


def hay_url(texto):
    m = _URL.search(texto or "")
    return m.group(0).rstrip(".,;)") if m else None


def hay_html(texto):
    """True si el mensaje trae HTML pegado (varios tags)."""
    return len(_HTML.findall(texto or "")) >= 3


def es_peticion(texto, codigo_adjunto=""):
    t = _t(texto)
    # Si hay intención de COPIAR, esto es para la habilidad copia, no análisis.
    if any(c in t for c in _VERBOS_COPIA):
        return False
    tiene_verbo = any(v in t for v in _VERBOS)
    tiene_noun = any(n in t for n in _NOUNS)
    if hay_url(texto) and tiene_verbo:
        return True
    if hay_html(texto) and tiene_verbo:
        return True
    if tiene_verbo and tiene_noun:
        return True
    # Paquete/librería: "analizá spacy", "analizá el paquete requests"
    if tiene_verbo and _es_paquete(texto):
        return True
    # Repo/proyecto local, archivo de código, o herramienta CLI
    if tiene_verbo and (ruta_local(texto) or comando_cli(texto)):
        return True
    return False


def objetivo(texto):
    """Qué se pidió analizar, en limpio (para el reporte)."""
    return (texto or "").strip()


def modo(texto):
    if hay_html(texto):
        return "html"
    if hay_url(texto):
        return "web"
    return "conceptual"


# ── Modificadores de alcance ─────────────────────────────────────────────────
# Secciones disponibles del análisis. "solo X" filtra; "sin X" excluye.
_SECCIONES = {
    "diseño": "diseno", "diseno": "diseno", "estética": "diseno", "estetica": "diseno", "ui": "diseno",
    "seguridad": "seguridad", "ciberseguridad": "seguridad", "vulnerabilidad": "seguridad",
    "performance": "performance", "rendimiento": "performance", "velocidad": "performance",
    "seo": "seo", "accesibilidad": "a11y", "a11y": "a11y",
    "privacidad": "privacidad", "red": "red", "network": "red",
    "tecnolog": "sources", "stack": "sources", "librer": "sources",
    "infra": "infra", "tools": "tools", "herramient": "tools",
}


def alcance(texto):
    """
    Devuelve (incluir, excluir): conjuntos de secciones.
    'analizá solo el diseño' → incluir={diseno}
    'analizá sin performance' → excluir={performance}
    'no analices los tools'  → excluir={tools}  (todas las técnicas)
    Vacío = análisis completo.
    """
    t = _t(texto)
    incluir, excluir = set(), set()
    # "solo / solamente / únicamente <sección>"
    if re.search(r"\bsol[oa]\b|solamente|únicamente|unicamente|nada m[aá]s que", t):
        for k, v in _SECCIONES.items():
            if k in t:
                incluir.add(v)
    # "sin / no analices / excepto <sección>"
    if re.search(r"\bsin\b|no analic|no analiz|excepto|menos\b", t):
        for k, v in _SECCIONES.items():
            if k in t:
                excluir.add(v)
    # "tools" excluido = todas las secciones técnicas
    if "tools" in excluir:
        excluir |= {"red", "sources", "seguridad", "performance", "infra"}
        excluir.discard("tools")
    return incluir, excluir


# ── Declaración de propiedad (desbloquea seguridad avanzada) ─────────────────
_PROPIO = (
    "es mi sitio", "es mi web", "es mi página", "es mi pagina", "es mío", "es mio",
    "mi propio", "mi navegador", "este es mi", "esta es mi", "lo autorizo",
    "lo autorizó", "tengo permiso", "soy el dueño", "soy dueño", "mi servidor",
    "auditá mi", "audita mi", "mi proyecto", "página mía", "pagina mia",
)


def es_objetivo_propio(texto):
    t = _t(texto)
    return any(p in t for p in _PROPIO)


# ── Detección de PAQUETE/LIBRERÍA (Ola 2) ────────────────────────────────────
_PKG_KW = ("paquete", "librería", "libreria", "módulo", "modulo", "library",
           "package", "pip install", "npm install", "dependencia", "framework")
# palabras españolas comunes que NO son nombres de paquete (anti falso positivo)
_STOP = {"esto", "eso", "esta", "este", "web", "página", "pagina", "sitio", "código",
         "codigo", "sistema", "url", "api", "login", "html", "el", "la", "lo", "un",
         "una", "mi", "tu", "su", "diseño", "diseno", "seguridad", "todo", "que"}
_PKG_TOKEN = re.compile(r"\b([a-z][a-z0-9]+(?:[-_.][a-z0-9]+)*)\b")


def nombre_paquete(texto):
    """Extrae el nombre de paquete. Tras una keyword, o el token identificador suelto."""
    t = (texto or "").lower()
    # tras keyword explícita
    for kw in _PKG_KW:
        m = re.search(re.escape(kw) + r"\s+([a-z0-9][\w\-.]+)", t)
        if m:
            return m.group(1)
    # token identificador suelto (sacando verbos y stopwords)
    candidatos = [tok for tok in _PKG_TOKEN.findall(t)
                  if tok not in _STOP and not any(v in tok for v in ("analiz", "estudi", "inspec", "examin", "revis"))
                  and 2 <= len(tok) <= 30]
    return candidatos[-1] if candidatos else None


def _menciona_paquete(texto):
    t = _t(texto)
    return any(kw in t for kw in _PKG_KW)


# palabras que pertenecen a OTRAS skills — si aparecen, no es paquete
_OTRAS_SKILLS = ("sentimiento", "sentir", "romano", "código", "codigo")


def _es_paquete(texto):
    """True si el pedido es sobre un paquete/librería, con guardas anti-colisión."""
    t = _t(texto)
    if any(o in t for o in _OTRAS_SKILLS):
        return False
    if _menciona_paquete(texto):
        return True
    # forma escueta: "analizá spacy" — mensaje corto, un identificador suelto, sin sustantivo web
    tiene_noun = any(n in t for n in _NOUNS)
    palabras = t.split()
    if not tiene_noun and len(palabras) <= 6 and nombre_paquete(texto):
        return True
    return False


def tipo(texto):
    """Router universal: html | repo | web | herramienta | codigo | paquete | conceptual."""
    import os
    t = _t(texto)
    if hay_html(texto):
        return "html"
    gh = repo_github(texto)
    if gh and any(k in t for k in _REPO_KW):
        return "repo"
    if hay_url(texto):
        return "web"
    if any(k in t for k in _TOOL_KW) and comando_cli(texto):
        return "herramienta"
    ruta = ruta_local(texto)
    if ruta:
        if os.path.isdir(ruta):
            return "repo"
        if os.path.isfile(ruta) and _CODE_EXT.search(ruta):
            return "codigo"
        return "repo"
    if _es_paquete(texto):
        return "paquete"
    return "conceptual"


# ── Repo / proyecto / código / herramienta ───────────────────────────────────
_PATH_WIN = re.compile(r"[A-Za-z]:\\[^\s\"'<>]+")
_CODE_EXT = re.compile(r"\.(py|js|ts|jsx|tsx|go|rs|rb|php|java|c|cpp|cs|html|css|sql|sh)\b", re.I)
_REPO_KW = ("repo", "repositorio", "proyecto")
_TOOL_KW = ("herramienta", "comando", " cli", "ejecutable", "binario")


def repo_github(texto):
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", texto or "")
    return (m.group(1), m.group(2).replace(".git", "")) if m else None


def ruta_local(texto):
    m = _PATH_WIN.search(texto or "")
    if m:
        return m.group(0).rstrip(' ".,;')
    m = re.search(r"(?:carpeta|proyecto|ruta|directorio)\s+([^\s\"']+[/\\][^\s\"']+)", texto or "", re.I)
    return m.group(1) if m else None


def comando_cli(texto):
    m = re.search(r"(?:herramienta|comando|ejecutable|binario|cli)\s+([a-zA-Z][\w.\-]*)", texto or "", re.I)
    return m.group(1) if m else None

# ── Auditoría de seguridad (modo hacker / análisis de vulnerabilidades) ──────
_SEG_MARKERS = (
    "vulnerab", "modo hacker", "pentest", "hackea", "hackear", "fragilidad",
    "frágil", "fragil", "fallas de seguridad", "huecos de seguridad", "agujero",
    "auditá la seguridad", "audita la seguridad", "auditar la seguridad",
    "auditoría de seguridad", "auditoria de seguridad", "qué tan seguro",
    "que tan seguro", "es seguro", "inseguro", "exploit", "vector de ataque",
    "superficie de ataque", "blindar", "endurec", "hardening", "análisis de seguridad",
    "analisis de seguridad", "buscá fallas", "busca fallas", "puntos de entrada",
)


def quiere_seguridad(texto):
    """True si el pedido es una auditoría de seguridad / análisis modo hacker."""
    return any(m in _t(texto) for m in _SEG_MARKERS)


_SIGNOS_FUERTES = ("```", "def ", "class ", "function ", "<?php", "import ")
_SIGNOS_DEBILES = ("const ", "let ", "var ", "=>", "select ", "public ",
                   "private ", "return ", "});", "console.log", "self.")


def hay_codigo_pegado(texto):
    """True si el mensaje trae código pegado: una señal fuerte, o dos débiles."""
    t = (texto or "").lower()
    if any(s in t for s in _SIGNOS_FUERTES):
        return True
    return sum(s in t for s in _SIGNOS_DEBILES) >= 2


def extraer_codigo_pegado(texto):
    """Saca el código pegado: bloque ```...```, lo de después de ':', o el texto."""
    m = re.search(r"```(?:[\w+]*)\n?(.*?)```", texto or "", re.DOTALL)
    if m:
        return m.group(1).strip()
    if ":" in (texto or "") and hay_codigo_pegado(texto.split(":", 1)[1]):
        return texto.split(":", 1)[1].strip()
    return (texto or "").strip()


def lenguaje_codigo(texto):
    """Adivina el lenguaje del código pegado para el reporte."""
    t = (texto or "").lower()
    if any(s in t for s in ("def ", "import ", "self.", "__init__", "print(")):
        return "python"
    if any(s in t for s in ("function ", "const ", "=>", "let ", "var ", "console.log")):
        return "javascript"
    if "<?php" in t:
        return "php"
    if any(s in t for s in ("<html", "<div", "<script")):
        return "html"
    if "select " in t or "insert into" in t:
        return "sql"
    return "código"