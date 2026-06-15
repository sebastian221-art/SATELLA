"""
nucleo/habilidades/navegador/detector.py
Detecta cuándo entrar al modo navegador y, MIENTRAS el modo está activo, reclama
todos los mensajes. Enruta cada mensaje a: navegar, inspección, observador (grabar/
guardar/cancelar), recetas (usar/listar, con variable), control del reproductor de
video, o instrucción para el agente.

El Gobernador tiene prioridad por encima (kill switch / modo seguro siguen llegando).
"""
import re
from . import motor

_ENTRAR = (
    "modo navegador", "entrá al navegador", "entra al navegador", "abrí el navegador",
    "abri el navegador", "abrí un navegador", "controlá el navegador", "controla el navegador",
    "navegador supremo", "tomá el navegador", "toma el navegador",
)
_SALIR = (
    "salí del modo navegador", "sali del modo navegador", "salí del navegador",
    "sali del navegador", "cerrá el navegador", "cerra el navegador",
    "apagá el navegador", "apaga el navegador", "terminá el modo navegador",
)
# tolerante a typos: "salí ... naveg..." (ej "salí del modo navegado")
_RE_SALIR = re.compile(r"\bsal(?:í|i|ir|ite)?\b.{0,20}naveg", re.I)


def _t(s):
    return (s or "").lower()


def _es_salir(t):
    return any(s in t for s in _SALIR) or bool(_RE_SALIR.search(t))


def detecta(texto, codigo_adjunto=""):
    t = _t(texto)
    if _es_salir(t):
        return True
    if any(e in t for e in _ENTRAR):
        return True
    if motor.activo():
        return True
    return False


_RE_URL = re.compile(r"(https?://[^\s]+|\b[\w.-]+\.(?:com|org|net|io|co|gov|edu|tv|me|app|dev|ai)\b[^\s]*)", re.I)
_IR = ("andá a", "anda a", "andate a", "ir a", "abrí ", "abri ", "entrá a", "entra a",
       "llevame a", "navegá a", "navega a", "ve a ", "vamos a", "andá al", "anda al")
_TAREA_VERBOS = ("ponme", "poné", "pon ", "buscá", "busca",
                 "escribí", "escribi", "clic", "apretá", "apreta", "presioná", "presiona",
                 "dale a", "seleccioná", "selecciona", "abrí el video", "entrá al video",
                 "encontrá", "encontra", "mandá", "manda", "enviá", "envia", "mensaje",
                 "login", "iniciá sesión", "inicia sesion", "comprá", "compra", "agregá",
                 "elegí", "elegi")


def _video_intent(t):
    """Control del reproductor de video HTML5. Devuelve dict o None."""
    m = re.search(r"minuto\s+(\d+)", t)
    if m:
        return {"accion": "minuto", "valor": int(m.group(1))}
    m = re.search(r"(?:adelant|avanz)\w*\s+(\d+)", t)
    if m:
        return {"accion": "adelantar", "valor": int(m.group(1))}
    m = re.search(r"(?:atras|retroced)\w*\s+(\d+)", t)
    if m:
        return {"accion": "atrasar", "valor": int(m.group(1))}
    m = re.search(r"volumen\s+(?:al?\s+)?(\d+)", t)
    if m:
        return {"accion": "volumen", "valor": int(m.group(1))}
    if any(k in t for k in ("subí el volumen", "subi el volumen", "más volumen", "mas volumen", "subile el volumen")):
        return {"accion": "volumen", "valor": 85}
    if any(k in t for k in ("bajá el volumen", "baja el volumen", "menos volumen", "bajale el volumen")):
        return {"accion": "volumen", "valor": 25}
    if any(k in t for k in ("silenciá", "silencia", "muteá", "mutea", "sin sonido")):
        return {"accion": "silenciar"}
    if any(k in t for k in ("activá el sonido", "activa el sonido", "con sonido", "quitá el silencio", "quita el silencio")):
        return {"accion": "activar_sonido"}
    m = re.search(r"velocidad\s+(?:a\s+)?([0-9]+(?:[.,][0-9]+)?)", t) or re.search(r"\b([0-9](?:[.,][0-9]+)?)\s*x\b", t)
    if m:
        return {"accion": "velocidad", "valor": float(m.group(1).replace(",", "."))}
    if any(k in t for k in ("pausá", "pausa", "pausalo", "pará el video", "para el video",
                            "detené el video", "detene el video", "frená el video", "frena el video")):
        return {"accion": "pause"}
    if any(k in t for k in ("dale play", "poné play", "pone play", "reproducí el video", "reproduce el video",
                            "play al video", "seguí el video", "reanudá", "reanuda", "reanudalo")):
        return {"accion": "play"}
    if any(k in t for k in ("pantalla completa", "pantalla compelta", "fullscreen", "maximizá el video")):
        return {"accion": "pantalla_completa"}
    return None


def intencion(texto):
    """
    Devuelve (accion, arg). acciones:
      entrar, salir, ir(url), elementos, screenshot, estado,
      observador_iniciar, observador_guardar(nombre), observador_cancelar,
      receta({nombre,variable}), recetas, video({accion,valor}), instruccion(texto)
    """
    t = _t(texto)

    # salir del modo navegador (cierra todo) — tolerante a typos
    if _es_salir(t):
        return ("salir", None)
    if any(e in t for e in _ENTRAR) and not motor.activo():
        m = _RE_URL.search(texto)
        return ("entrar", m.group(1) if m else None)

    # inspección
    if any(k in t for k in ("qué hay en la página", "que hay en la pagina", "qué elementos",
                            "que elementos", "qué se puede", "que se puede", "leé la página",
                            "lee la pagina")):
        return ("elementos", None)
    if any(k in t for k in ("captura", "screenshot", "pantallazo", "foto de la página")):
        return ("screenshot", None)
    if any(k in t for k in ("dónde estás", "donde estas", "en qué página", "en que pagina")):
        return ("estado", None)

    # ── Credenciales seguras (llavero) ──
    if any(k in t for k in ("qué logins", "que logins", "qué credenciales", "que credenciales",
                            "qué contraseñas", "que contrasenas", "logins guardados", "credenciales guardadas",
                            "logins tenés", "logins tenes")):
        return ("credenciales", None)
    if (("login" in t or "contraseñ" in t or "contrasen" in t or "credencial" in t or "clave" in t)
            and any(v in t for v in ("borrá", "borra", "olvidá", "olvida", "elimina", "eliminá", "quitá", "quita"))):
        m = re.search(r"(?:de|del|para|en)\s+([\w.-]+)", texto, re.I)
        return ("credencial_borrar", (m.group(1).strip() if m else None))
    # guardar: "guardá mi login/contraseña de X" — la clave la lee del NAVEGADOR, no del chat
    if (("login" in t or "contraseñ" in t or "contrasen" in t or "credencial" in t or "clave" in t or "usuario" in t)
            and any(v in t for v in ("guardá", "guarda", "guardar", "record", "memoriz", "acord", "anotá", "anota"))):
        m = re.search(r"(?:de|del|para|en)\s+([\w.-]+)", texto, re.I)
        return ("credencial_guardar", (m.group(1).strip() if m else None))
    # ── Memoria de navegación ──
    if any(k in t for k in ("qué aprendiste", "que aprendiste", "qué sabés navegar", "que sabes navegar",
                            "qué tenés en memoria", "que tenes en memoria", "qué procesos", "que procesos")):
        return ("memoria_lista", None)
    # ── Conocimiento del mundo web ──
    # enseñar: "recordá que en crunchyroll los episodios están abajo"
    m = re.search(r"(?:record[aá]|acord[aá]te|anot[aá]|ten[ée] en cuenta)\s+que\s+(?:en|para|de|del)\s+([\w.-]+)[,:\s]+(.+)$", texto, re.I)
    if m:
        return ("conocimiento_enseñar", {"dominio": m.group(1).strip(), "nota": m.group(2).strip()})
    # preguntar: "qué sabés de netflix" / "qué conocés del internet"
    if any(k in t for k in ("qué sabés de", "que sabes de", "qué conocés de", "que conoces de",
                            "qué sabés del", "que sabes del", "conocimiento de", "qué sabés sobre", "que sabes sobre")):
        m = re.search(r"(?:de|del|sobre)\s+([\w.-]+)", texto, re.I)
        return ("conocimiento_ver", (m.group(1).strip() if m else None))

    # ── Observador / recetas (Fase 4C) ──
    # 1) GUARDAR: "guardar + receta/grabación" (con o sin "la"), o frases de cierre con guardado
    _stop_guarda = ("terminá de observar", "termina de observar", "listo, guardá", "listo guarda",
                    "ya terminé de mostrarte", "ya termine de mostrarte")
    _guarda_verbo = ("guard", "salvá", "salva", "anotá", "anota")
    if any(s in t for s in _stop_guarda) or (("receta" in t or "grabaci" in t) and any(v in t for v in _guarda_verbo)):
        m = re.search(r"como\s+(.+)$", texto, re.I) or re.search(r"receta\s+(?:como\s+)?(.+)$", texto, re.I)
        return ("observador_guardar", (m.group(1).strip() if m else None))
    # 2) CANCELAR/SALIR del observador (sin guardar) — antes que "iniciar"
    if ("observador" in t or "grabaci" in t or "ese modo" in t or "este modo" in t) and \
            any(k in t for k in ("salí", "sali", "salir", "sal de", "sal del", "salite", "cancel",
                                 "descartá", "descarta", "dejá de", "deja de", "no grabes", "ya no")):
        return ("observador_cancelar", None)
    # 3) listar recetas
    if any(k in t for k in ("qué recetas", "que recetas", "listá las recetas", "lista las recetas",
                            "mostrame las recetas", "cuáles recetas", "cuales recetas", "qué sabés hacer")):
        return ("recetas", None)
    # 4) usar receta (con variable opcional): "hacé/usá/corré/repetí/reproducí (la) receta X [con/para/y pon ... Y]"
    m = re.search(r"(?:hac[eé]|us[aá]|corr[eé]|repet[ií]|rep\w*duc\w*|ejecut[aá])\s+(?:la\s+)?receta\s+(.+)$", texto, re.I)
    if m:
        resto = m.group(1).strip()
        var = None
        mp = re.search(r"\s+(?:con|para|y\s+pon[ée]?(?:\s+el|\s+la)?(?:\s+anime|\s+video|\s+serie|\s+capítulo|\s+pelicula|\s+película)?|y\s+busc[aá])\s+(.+)$", resto, re.I)
        if mp:
            var = mp.group(1).strip()
            resto = resto[:mp.start()].strip()
        return ("receta", {"nombre": resto, "variable": var})
    # 5) control del reproductor de video (después de receta, para no pisar "reproducí la receta")
    v = _video_intent(t)
    if v is not None:
        return ("video", v)
    # 6) empezar a observar
    if any(k in t for k in ("modo observador", "observá lo que hago", "observa lo que hago",
                            "analizá lo que hago", "analiza lo que hago", "mirá lo que hago",
                            "mira lo que hago", "aprendé de mí", "aprende de mi", "aprendé de mi",
                            "grabá lo que hago", "graba lo que hago", "fijate lo que hago",
                            "fijate cómo lo hago", "te muestro cómo", "te muestro como")):
        return ("observador_iniciar", None)

    tiene_tarea = any(v in t for v in _TAREA_VERBOS)
    m = _RE_URL.search(texto)
    if m and (any(k in t for k in _IR) or t.strip().startswith(("http", "www"))) and not tiene_tarea:
        return ("ir", m.group(1))
    return ("instruccion", texto)