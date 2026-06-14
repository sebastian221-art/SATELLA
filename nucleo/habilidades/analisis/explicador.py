"""
nucleo/habilidades/analisis/explicador.py
Razona como ingeniero senior SOBRE los hechos, separando Confirmado (está en los
hechos) de Inferido (típico, no confirmado). Respeta el ALCANCE: si el usuario
pidió "solo diseño", el explicador razona SOLO sobre diseño y no se va al backend.
Reusa el cliente Groq de la habilidad de código.
"""
from nucleo.habilidades.python import _llm
from nucleo.habilidades import _generacion_segura

_SYSTEM = (
    "Sos un ingeniero senior haciendo ingeniería inversa DESCRIPTIVA. Regla de oro: "
    "distinguir lo que SE OBSERVA de lo que se INFIERE, en dos bloques:\n"
    "**Confirmado** — solo lo que está literalmente en los hechos.\n"
    "**Inferido (típico, no confirmado)** — hipótesis, cada una con 'Probablemente' o 'Es típico que'. "
    "NUNCA inventes nombres concretos de endpoints, librerías o proveedores que no estén en los hechos; "
    "si no los viste, hablá en general ('un gateway de pagos'). "
    "Español rioplatense (voseo), preciso, sin relleno."
)

_ETIQUETAS = {
    "diseno": "diseño (colores, tipografías, componentes, layout)",
    "seguridad": "seguridad (headers, cookies, CVE, exposición)",
    "performance": "performance/rendimiento",
    "seo": "SEO y estructura", "a11y": "accesibilidad",
    "privacidad": "privacidad y tracking", "red": "red y recursos",
    "sources": "stack y librerías", "infra": "infraestructura/TLS",
}


def _restriccion(incluir, excluir):
    if incluir:
        temas = ", ".join(_ETIQUETAS.get(s, s) for s in sorted(incluir))
        return (f"\n\nALCANCE ESTRICTO: el usuario pidió analizar ÚNICAMENTE {temas}. "
                "Razoná SOLO sobre eso. No menciones backend, streaming, autenticación ni "
                "ninguna otra área fuera de ese alcance, ni en Confirmado ni en Inferido.")
    if excluir:
        temas = ", ".join(_ETIQUETAS.get(s, s) for s in sorted(excluir))
        return f"\n\nALCANCE: NO hables de {temas} (el usuario los excluyó)."
    return ""


def explicar(objetivo, hechos_texto, modo="web", incluir=None, excluir=None):
    if not _llm.disponible():
        return ""
    restriccion = _restriccion(incluir or set(), excluir or set())
    if modo == "conceptual":
        prompt = (
            f"El usuario pidió: «{objetivo}».\n"
            "No observaste nada concreto, así que TODO es Inferido: explicá en general cómo funciona "
            "esa clase de sistema, marcando que es lo típico." + restriccion)
    else:
        prompt = (
            f"Pedido: «{objetivo}».\n\nHECHOS OBSERVADOS:\n{hechos_texto}\n\n"
            "Explicá en los dos bloques (Confirmado / Inferido). No agregues nombres de productos "
            "ni rutas que no estén arriba." + restriccion)
    return _generacion_segura.completar_texto(prompt, system=_SYSTEM, max_tokens=1800)