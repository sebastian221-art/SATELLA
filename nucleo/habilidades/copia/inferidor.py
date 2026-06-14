"""
nucleo/habilidades/copia/inferidor.py
Extrae el CONTRATO FUNCIONAL del objetivo: qué hace (no cómo está implementado).
Entradas → salidas, comportamientos clave, y qué partes son "pesadas" (candidatas
a equivalente liviano). Es el "test de cómo funciona / inferir qué hace".
"""
from nucleo.habilidades.python import _llm
from nucleo.habilidades import _generacion_segura

_SYSTEM = (
    "Sos un ingeniero senior que hace ingeniería inversa FUNCIONAL. Tu trabajo es "
    "destilar QUÉ HACE algo, no cómo está implementado. Ignorás detalles de "
    "implementación específicos del sistema original. Respondés en español (voseo), "
    "estructurado y conciso."
)


def inferir(objetivo, contexto, es_codigo=False):
    """contexto: hechos del analizador, el código pegado, o la descripción del usuario."""
    if not _llm.disponible():
        return ""
    que = "el siguiente CÓDIGO" if es_codigo else "la siguiente información observada"
    prompt = (
        f"Pedido del usuario: «{objetivo}».\n\n"
        f"A partir de {que}:\n{contexto[:6000]}\n\n"
        "Extraé el CONTRATO FUNCIONAL en este formato:\n"
        "1. QUÉ HACE (una frase).\n"
        "2. ENTRADAS (qué recibe).\n"
        "3. SALIDAS (qué produce).\n"
        "4. COMPORTAMIENTOS CLAVE (lista breve de lo esencial que debe replicarse).\n"
        "5. PARTES PESADAS (qué del original es costoso: modelos, GPU, servicios externos, "
        "datos grandes — candidatos a sustituir por un equivalente liviano). Si no hay, decí 'ninguna'.\n"
        "No copies la implementación. Describí la función."
    )
    return _generacion_segura.completar_texto(prompt, system=_SYSTEM, max_tokens=1600)