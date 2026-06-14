"""
nucleo/habilidades/copia/decisor.py
Decide la ESTRATEGIA de copia:
  · port_adaptado       → hay fuente, es liviano y simple: portar adaptado a Satella.
  · equivalente_funcional → pesado/cerrado/complejo: construir algo liviano que haga lo mismo.
  · mejora              → equivalente + mejoras pedidas explícitamente.
Heurística determinista sobre señales de "peso" y disponibilidad de fuente.
"""

import re

_PESADO = ("modelo", "neural", "red neuronal", "gpu", "cuda", "tensor", "torch",
           "tensorflow", "entrenamiento", "machine learning", "deep learning", "llm",
           "embedding", "transformer", "dataset", "millones de", "gigabyte", "petabyte",
           "inferencia", "fine-tun", "weights", "pesos del modelo")
_FUENTE_DISPONIBLE = {"codigo", "repo", "paquete"}  # tipos donde vemos/accedemos la lógica


def decidir(tipo_objetivo, contrato_txt, quiere_mejora=False):
    blob = (contrato_txt or "").lower()
    # La sección "PARTES PESADAS" lista lo que hay que EVITAR; no la contamos como peso real.
    corte = re.search(r"partes pesadas|partes\s+costosas|componentes pesados", blob)
    blob_core = blob[:corte.start()] if corte else blob
    es_pesado = any(k in blob_core for k in _PESADO)
    hay_fuente = tipo_objetivo in _FUENTE_DISPONIBLE

    if quiere_mejora:
        estrategia = "mejora"
        razon = "Pediste mejorar, no solo copiar: equivalente funcional + mejoras."
    elif es_pesado:
        estrategia = "equivalente_funcional"
        razon = ("El original tiene partes pesadas (modelo/GPU/datos grandes). Para Satella "
                 "—CPU, liviano— conviene un equivalente funcional liviano, no un port literal.")
    elif hay_fuente:
        estrategia = "port_adaptado"
        razon = "Hay fuente accesible y es liviano: portar la lógica adaptada a Satella."
    else:
        estrategia = "equivalente_funcional"
        razon = ("No hay fuente directa (caja negra): inferir el comportamiento observable y "
                 "construir el equivalente funcional para Satella.")

    return {"estrategia": estrategia, "razon": razon, "es_pesado": es_pesado, "hay_fuente": hay_fuente}


def restricciones_satella():
    return ("Python; CPU, SIN GPU; liviano (preferí stdlib o dependencias chicas); modular; "
            "que corra en una PC común; nada de modelos pesados ni servicios externos en runtime "
            "salvo que sea imprescindible.")