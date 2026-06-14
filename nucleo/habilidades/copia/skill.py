"""
nucleo/habilidades/copia/skill.py — COPIA / SUPER-COPIA.
Reproduce la FUNCIÓN de algo (web, paquete, repo, código o descripción) como un
equivalente eficiente para Satella — no una copia literal. Pipeline:
  1. analizar    (reusa el analizador máximo)
  2. inferir     (contrato funcional: qué hace)
  3. decidir     (port adaptado / equivalente funcional / mejora)
  4. generar     (código liviano para Satella)
  5. verificar   (sintaxis + smoke test)
  6. fidelidad   (qué tan fiel es y qué tradeoffs)

Objetivo PROPIO ("es mi sitio/proyecto") → reproducción completa, incluida tu
auth/sistemas. Ajeno → equivalente funcional, nunca una réplica engañosa ni
captura de credenciales de terceros.
"""
from nucleo.habilidades import contrato
from . import detector, inferidor, decisor, generador, verificador, reporte
from nucleo.habilidades.analisis import extractor_web, paquetes, repos

NOMBRE = "copia"
DESCRIPCION = ("Reproduce la funcionalidad de algo (web, paquete, repo, código o una descripción) "
               "como un equivalente eficiente para Satella: infiere qué hace y lo reimplementa "
               "liviano, con reporte de fidelidad. Reproducción completa solo en objetivos propios.")
EJEMPLOS = [
    "copiá la funcionalidad de este login (es mi sitio) https://...",
    "hacé un equivalente liviano de spacy para detectar entidades",
    "reproducí lo que hace este código: <pegado>",
    "imitá un rate limiter pero más liviano",
]


def detecta(texto, codigo_adjunto=""):
    return detector.detecta(texto, codigo_adjunto)


def manejar(texto, contexto=None):
    tipo, ref = detector.objetivo(texto, contexto if isinstance(contexto, str) else "")
    propio = detector.es_propio(texto)
    quiere_mejora = detector.mejorar(texto)
    objetivo = (texto or "").strip()

    # 1) ANALIZAR el objetivo (si es concreto)
    facts_txt, es_codigo = _analizar(tipo, ref, propio)

    # 2) INFERIR contrato funcional
    contrato_txt = inferidor.inferir(objetivo, facts_txt or ref, es_codigo=es_codigo)

    # Sin LLM no podemos inferir/generar: devolvemos el análisis y avisamos.
    if not contrato_txt:
        cuerpo = _sin_llm(tipo, ref, facts_txt)
        return contrato.resultado(NOMBRE, tipo, "Copia: análisis listo (generación necesita el modelo).",
                                  cuerpo, ok=True)

    # 3) DECIDIR estrategia
    decision = decisor.decidir(tipo, contrato_txt, quiere_mejora)

    # 4) GENERAR equivalente
    codigo = generador.generar(objetivo, contrato_txt, decision)

    # 5) VERIFICAR
    verif = verificador.verificar(codigo) if codigo else {"sintaxis_ok": False, "error": "sin código"}

    # 6) FIDELIDAD
    fid = reporte.fidelidad(objetivo, contrato_txt, decision, codigo, verif) or \
        reporte.fidelidad_heuristica(decision, verif)

    # Armar respuesta
    partes = [
        f"Objetivo: {tipo}" + (f" ({ref})" if tipo != "descripcion" else "") +
        (" · modo PROPIO (reproducción completa)" if propio else ""),
        "── Contrato funcional (qué hace) ──\n" + contrato_txt,
        f"── Estrategia ──\n{decision['estrategia']}: {decision['razon']}",
    ]
    if codigo:
        partes.append("── Equivalente para Satella ──\n```python\n" + codigo + "\n```")
        partes.append("── Verificación ──\n" + verificador.como_texto(verif))
    partes.append("── Fidelidad ──\n" + fid)

    return contrato.resultado(NOMBRE, tipo, _resumen(tipo, decision, verif), "\n\n".join(partes), ok=True)


def _analizar(tipo, ref, propio):
    """Devuelve (texto_de_contexto, es_codigo)."""
    try:
        if tipo == "web":
            h = extractor_web.desde_url(ref, propio=propio)
            return (extractor_web.como_texto(h) if h.get("ok") else f"No se pudo traer {ref}: {h.get('error','')}"), False
        if tipo == "paquete":
            f = paquetes.analizar(ref)
            return (paquetes.como_texto(f) if f.get("ok") else f.get("error", "")), False
        if tipo == "repo":
            if "/" in ref and "\\" not in ref and not ref[1:2] == ":":
                owner, _, repo = ref.partition("/")
                f = repos.analizar_github(owner, repo)
            else:
                f = repos.analizar_local(ref)
            return (repos.como_texto(f) if f.get("ok") else f.get("error", "")), False
        if tipo == "codigo":
            return ref, True
    except Exception as e:
        return f"(no se pudo analizar el objetivo: {e})", False
    return "", False  # descripcion: sin análisis, se infiere del texto


def _sin_llm(tipo, ref, facts_txt):
    base = "El pipeline de copia necesita el modelo (Groq) para inferir y generar.\n"
    if facts_txt:
        base += "\nPor ahora, esto es lo que analicé del objetivo:\n\n" + facts_txt
    return base


def _resumen(tipo, decision, verif):
    estado = "ejecuta" if verif.get("ejecuta") else ("sintaxis OK" if verif.get("sintaxis_ok") else "con errores")
    return f"Copia ({tipo}) · {decision['estrategia']} · {estado}."