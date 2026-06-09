"""
Satella — cerebro central.
Orquesta comprensión → memoria → RAG → generación → validación → voz.
"""
import logging
from nucleo import comprension, memoria, rag, generacion, voz

log = logging.getLogger("satella.core")

MAX_REINTENTOS = 2


def procesar_mensaje(mensaje: str, voz_habilitada: bool = True) -> dict:
    """
    Pipeline completo de Satella.
    Retorna dict con: respuesta, audio_b64, nombre_usado, comprension
    """
    # ── Capa 1: Comprensión ─────────────────────────────────────
    ctx_texto = memoria.historial_texto()
    modelo_txt = memoria.modelo_compacto()
    comp = comprension.comprender(mensaje, ctx_texto, modelo_txt)

    log.info(f"[C1] tono={comp.get('tono')} | necesita={comp.get('necesita')} | nombre={comp.get('nombre')}")

    # ── Capa 2: Memoria ─────────────────────────────────────────
    episodios_txt = memoria.episodios_compactos()
    historial_groq = memoria.historial_groq()

    # ── Capa 3: RAG ─────────────────────────────────────────────
    rag_keywords = comp.get("rag_keywords") or mensaje
    contexto_rag = rag.consultar(rag_keywords, k=3)

    # ── Capa 4: Generación ──────────────────────────────────────
    respuesta = generacion.generar(
        mensaje=mensaje,
        comprension=comp,
        modelo=modelo_txt,
        episodios=episodios_txt,
        rag=contexto_rag,
        historial=historial_groq,
    )

    # ── Capa 5: Validación (hasta MAX_REINTENTOS) ───────────────
    for intento in range(MAX_REINTENTOS):
        valida, razon = voz.validar(respuesta, comp.get("nombre", "Sebas"))
        if valida:
            break
        log.warning(f"[C5] Respuesta inválida (intento {intento+1}): {razon}")
        respuesta = generacion.generar(
            mensaje=mensaje + f"\n[INSTRUCCIÓN: tu respuesta anterior violó una regla ({razon}). Regenera sin esa frase.]",
            comprension=comp,
            modelo=modelo_txt,
            episodios=episodios_txt,
            rag=contexto_rag,
            historial=historial_groq,
        )

    respuesta = voz.limpiar(respuesta)

    # ── Registrar turno ─────────────────────────────────────────
    memoria.registrar_turno("user", mensaje)
    memoria.registrar_turno("assistant", respuesta)

    # ── Capa 6: Voz ─────────────────────────────────────────────
    audio_b64 = None
    if voz_habilitada:
        audio_b64 = voz.sintetizar_voz(respuesta)

    return {
        "respuesta": respuesta,
        "audio_b64": audio_b64,
        "nombre_usado": comp.get("nombre", "Sebas"),
        "tono": comp.get("tono", "normal"),
        "comprension": comp,
    }


def iniciar_conversacion(voz_habilitada: bool = True) -> dict:
    """Satella inicia la conversación por su cuenta."""
    modelo_txt = memoria.modelo_compacto()
    ultimo = memoria.ultimo_tema()
    respuesta = generacion.generar_iniciacion(modelo_txt, ultimo)
    respuesta = voz.limpiar(respuesta)

    memoria.registrar_turno("assistant", respuesta)

    audio_b64 = None
    if voz_habilitada:
        audio_b64 = voz.sintetizar_voz(respuesta)

    return {
        "respuesta": respuesta,
        "audio_b64": audio_b64,
        "iniciacion": True,
    }


def cerrar_sesion() -> dict:
    """Cierra la sesión, genera el episodio y lo guarda."""
    historial = memoria.historial_texto()
    if not historial:
        return {}

    resumen = generacion.sintetizar_episodio(historial)
    memoria.cerrar_sesion(resumen)
    log.info(f"Sesión cerrada | tema: {resumen.get('tema_principal','?')}")
    return resumen