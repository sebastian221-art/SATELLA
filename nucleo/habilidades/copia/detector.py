"""
nucleo/habilidades/copia/detector.py
Detecta pedidos de COPIA/REIMPLEMENTACIÓN y resuelve el objetivo: qué copiar
(web, paquete, repo, código pegado, o una descripción) y si es objetivo propio.
Reusa el detector del analizador para no duplicar lógica.
"""
import re
from nucleo.habilidades.analisis import detector as adet

_VERBOS = (
    "copiá", "copia", "copiame", "copialo", "copiar",
    "reproducí", "reproduce", "reproducí", "reproducir",
    "recreá", "recrea", "recrear", "replicá", "replica", "replicar",
    "imitá", "imita", "imitar", "cloná", "clona", "clonar",
    "reimplementá", "reimplementa", "reimplementar",
    "hacé una versión", "hace una version", "hacé un equivalente",
    "equivalente de", "versión de", "version de", "imitación de",
)


def _t(texto):
    return " " + (texto or "").lower().strip() + " "


def detecta(texto, codigo_adjunto=""):
    t = _t(texto)
    return any(v in t for v in _VERBOS)


def es_propio(texto):
    return adet.es_objetivo_propio(texto)


def mejorar(texto):
    """¿Pidió mejorar, no solo copiar?"""
    t = _t(texto)
    return any(k in t for k in ("mejorá", "mejora", "mejor", "superá", "supera", "más eficiente", "mas eficiente"))


_CODE_HINT = re.compile(r"(def |class |import |from |function |const |let |var |public |private |#include|=>|console\.log|return )")


def objetivo(texto, codigo_adjunto=""):
    """
    Devuelve (tipo, referencia):
      web/paquete/repo/codigo/descripcion
    """
    if codigo_adjunto and codigo_adjunto.strip():
        return "codigo", codigo_adjunto
    # bloque de código entre fences ```
    m = re.search(r"```(?:\w+)?\s*([\s\S]+?)```", texto or "")
    if m and m.group(1).strip():
        return "codigo", m.group(1).strip()
    url = adet.hay_url(texto)
    gh = adet.repo_github(texto)
    ruta = adet.ruta_local(texto)
    if gh:
        return "repo", f"{gh[0]}/{gh[1]}"
    if ruta:
        return "repo", ruta
    if url:
        return "web", url
    if adet.hay_html(texto):
        return "codigo", texto
    # código pegado suelto (sin fences): varias líneas con pinta de código
    if texto and len(texto.splitlines()) >= 5 and len(_CODE_HINT.findall(texto)) >= 2:
        return "codigo", texto
    if adet._es_paquete(texto):
        return "paquete", adet.nombre_paquete(texto)
    return "descripcion", (texto or "").strip()