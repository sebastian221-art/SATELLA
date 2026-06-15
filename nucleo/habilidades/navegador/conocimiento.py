"""
nucleo/habilidades/navegador/conocimiento.py — CONOCIMIENTO DEL MUNDO WEB.

Lo que un humano SABE del internet y Satella no traía: cómo se comportan los
buscadores, los reproductores, los logins, los banners, los paywalls, el scroll
infinito, etc. Esto se inyecta al cerebro en CADA paso para que razone con
contexto real, no a ciegas.

Tiene dos capas:
  • GENERAL: principios que valen para casi cualquier sitio (curados acá).
  • POR DOMINIO: lo específico de cada sitio. Viene pre-cargado para los que ya
    conocemos y CRECE SOLO: Satella anota lo que descubre, y el usuario le puede
    enseñar ("recordá que en X ..."). Se guarda en datos/navegador/conocimiento.json.
"""
import json
import re
from pathlib import Path

_ARCHIVO = Path("datos/navegador/conocimiento.json")

# ── Capa GENERAL (saber web que siempre aplica) ──────────────────────────────
_GENERAL = [
    "Los banners de cookies/consentimiento tapan los clics: aceptalos o cerralos primero.",
    "En sitios de video (streaming), el botón de Reproducir/Ver ahora suele estar OCULTO "
    "y solo aparece al pasar el mouse por encima de la tarjeta (hover).",
    "Para buscar algo: clic en la barra de búsqueda (suele tener una lupa), escribir el "
    "término y apretar Enter. El primer resultado suele ser el correcto.",
    "Login: llenar email/usuario, llenar contraseña, y recién al final clic en el botón de "
    "enviar (Iniciar sesión/Acceder/Entrar). Eso último es lo único 'sensible'.",
    "Las listas largas (episodios, resultados) cargan más al bajar (scroll infinito), pero "
    "si scrolleás dos veces y no aparece, mejor usar clic-por-texto con el nombre exacto.",
    "Un mismo texto puede estar en varios elementos (título, imagen, link): el que sirve para "
    "navegar es el link/botón, no el texto suelto.",
    "Si un clic no cambió nada, ese elemento no era el correcto: probá otro, no repitas.",
]

# ── Capa POR DOMINIO pre-cargada (lo que ya aprendimos a los golpes) ──────────
_SEMILLA = {
    "crunchyroll.com": [
        "Pasar el mouse (hover) sobre la tarjeta de una serie revela el botón de reproducir.",
        "La lista de episodios carga dinámicamente y puede tener un selector de temporada; "
        "para elegir un episodio puntual, usá clic-por-texto con su nombre/número.",
        "Tiene buscador arriba; escribí el nombre del anime y apretá Enter.",
    ],
    "netflix.com": [
        "Necesita Google Chrome real (con Widevine/DRM); el error M7701-1003 es por DRM faltante.",
        "Pasar el mouse sobre un título revela los controles (play, +, info).",
        "El contenido está en filas horizontales; el buscador es el ícono de lupa arriba.",
    ],
    "youtube.com": [
        "La barra de búsqueda está arriba; el primer video suele ser el que se busca.",
        "Los videos son links con /watch?v=; clic en el título del video lo abre y reproduce.",
    ],
    "github.com": [
        "Un repositorio muestra el árbol de archivos; el README está debajo de la lista.",
        "Para ver un archivo, clic en su nombre en la lista; para los repos del usuario, "
        "la pestaña 'Repositories' del perfil.",
    ],
}


def _dom(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return (m.group(1).replace("www.", "").lower() if m else "")


def _leer():
    try:
        return json.loads(_ARCHIVO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _escribir(d):
    _ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    _ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def de_dominio(dom):
    """Notas para un dominio: pre-cargadas + aprendidas, fusionando también claves
    parciales (ej 'crunchyroll' y 'crunchyroll.com' se unifican), sin duplicar."""
    dom = (dom or "").replace("www.", "").lower()
    if not dom:
        return []
    notas = []
    fuentes = {**_SEMILLA}
    for d, ns in _leer().items():
        fuentes.setdefault(d, [])
        for n in ns:
            if n not in fuentes[d]:
                fuentes[d].append(n)
    for d, ns in fuentes.items():
        if d == dom or d in dom or dom in d:
            for n in ns:
                if n not in notas:
                    notas.append(n)
    return notas


def anotar(dom, nota):
    """Agrega una observación sobre un dominio (la escribe Satella o el usuario)."""
    dom = (dom or "").replace("www.", "").lower()
    nota = (nota or "").strip()
    if not dom or not nota:
        return {"ok": False}
    if nota in _SEMILLA.get(dom, []):
        return {"ok": True, "ya_sabia": True}
    d = _leer()
    d.setdefault(dom, [])
    if nota in d[dom]:
        return {"ok": True, "ya_sabia": True}
    d[dom].append(nota)
    d[dom] = d[dom][-20:]            # tope por dominio
    _escribir(d)
    return {"ok": True, "dominio": dom}


def para_prompt(url):
    """Bloque de conocimiento para inyectar al cerebro este paso (general + dominio)."""
    bloque = ["LO QUE SABÉS DEL INTERNET (usalo para decidir):"]
    bloque += [f"- {p}" for p in _GENERAL]
    notas = de_dominio(_dom(url))
    if notas:
        bloque.append(f"SOBRE ESTE SITIO ({_dom(url)}) ya sabés:")
        bloque += [f"- {n}" for n in notas]
    return "\n".join(bloque) + "\n"


def listar():
    """Todo el conocimiento por dominio (semilla + aprendido)."""
    fusion = {}
    for d, ns in _SEMILLA.items():
        fusion[d] = list(ns)
    for d, ns in _leer().items():
        fusion.setdefault(d, [])
        for n in ns:
            if n not in fusion[d]:
                fusion[d].append(n)
    return fusion