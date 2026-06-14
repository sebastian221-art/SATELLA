"""
nucleo/habilidades/navegador/cerebro.py — EL CEREBRO (Fase 4B, inteligente).
Agente que opera el navegador como una persona, con:

- MEMORIA DE SESIÓN: objetivo, historial y pendientes ENTRE mensajes.
- CONFIRMACIÓN UNA VEZ POR TAREA: lo sensible (enviar login/pago/publicación) se
  confirma la PRIMERA vez; tu "dale" autoriza el resto de ESA tarea. No más loop.
- CLIC POR TEXTO: si nombrás algo por su texto visible ("donde dice Episodio 13",
  "el botón ACCEDER"), lo busca y lo clickea directo — no scrollea a ciegas.
- GUARDARRAÍLES EN CÓDIGO: corta el scroll repetido y las acciones idénticas, y si
  se traba te muestra lo que ve para que lo guíes.

Loop: percibir (ojo) → planear (Groq, un paso) → actuar → repetir.
"""
import json
import logging
import re

from . import motor, ojo, _llm

log = logging.getLogger("satella.navegador")

_MAX_PASOS = 12

_sesion = {"objetivo": "", "historial": [], "pendiente": None,
           "esperando": None, "autorizado": False}


def reset():
    _sesion.update({"objetivo": "", "historial": [], "pendiente": None,
                    "esperando": None, "autorizado": False})


def _recordar(linea):
    _sesion["historial"].append(linea)
    if len(_sesion["historial"]) > 18:
        _sesion["historial"] = _sesion["historial"][-18:]


# ── Confirmaciones ───────────────────────────────────────────────────────────
_SI = ("dale", "si", "sí", "ok", "oka", "okay", "okey", "hacelo", "hacela", "hazlo",
       "confirmo", "confirma", "confirmá", "adelante", "continua", "continúa", "continuá",
       "segui", "seguí", "proceder", "procede", "obvio", "claro", "sip", "sisi")
_NO = ("no", "cancela", "cancelá", "para", "pará", "frena", "frená", "detene", "detené",
       "negativo", "nop", "nel")


def _si_no(t):
    tl = t.lower().strip()
    if tl.startswith(("mejor no", "no ", "no,")) or tl == "no":
        return "no"
    toks = re.findall(r"[a-záéíóúñü]+", tl)
    if not toks:
        return None
    if toks[0] in _NO:
        return "no"
    if toks[0] in _SI or any(tok in _SI for tok in toks[:2]):
        return "si"
    return None


def _texto_extra(t):
    m = re.match(r"^\s*(dale|sí|si|ok|okay|okey|hacelo|hazlo|confirmo|adelante|continua|continúa|seguí|segui|claro|obvio)\b[,:\s]*", t, re.I)
    return t[m.end():].strip() if m else ""


# ── Planeo ───────────────────────────────────────────────────────────────────
_SISTEMA = (
    "Sos el cerebro de navegación web de Satella. Operás un navegador real como una "
    "persona para cumplir el OBJETIVO del usuario, UN PASO POR VEZ. Respondés SIEMPRE con "
    "un único objeto JSON válido y NADA más: sin markdown, sin ``` , sin texto afuera del JSON."
)

_FORMATO = (
    '{"accion":"clic|clic_texto|hover|escribir|tecla|navegar|scroll|esperar|responder|preguntar|terminar",'
    '"indice":<n o null>,"texto":"<para escribir, o el TEXTO VISIBLE a clickear/hover>",'
    '"tecla":"<ej Enter>","url":"<si navegás>","sensible":<true|false>,"razon":"<corto>",'
    '"mensaje":"<para el usuario si respondés/preguntás/terminás>","listo":<true|false>}'
)


def _prompt_paso(objetivo, resumen, elementos, historial, nota="", con_vision=False):
    url = resumen.get("url", "")
    title = resumen.get("title", "")
    heads = " · ".join(resumen.get("headings", [])[:8])
    texto = (resumen.get("texto", "") or "")[:1400]
    lista = ojo.formatear(elementos, limite=45)
    hist = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(historial[-12:])) if historial else "  (ninguno todavía)"
    extra = f"\n⚠ NOTA: {nota}\n" if nota else ""
    vision_txt = (
        "MIRÁS una CAPTURA REAL de la página. Sobre cada elemento clickeable hay un número "
        "rojo [N] que coincide con el índice de la lista de abajo. Usá lo que VES para decidir: "
        "si ves el botón de reproducir, el episodio correcto, un banner que tapa, etc., elegí su "
        "número. Podés ver cosas que NO están en la lista de texto — confiá en la imagen.\n\n"
    ) if con_vision else ""
    return (
        vision_txt +
        f"OBJETIVO DEL USUARIO:\n{objetivo}\n{extra}\n"
        f"PÁGINA ACTUAL\nurl: {url}\ntítulo: {title}\nencabezados: {heads}\n"
        f"texto (recorte): {texto}\n\n"
        f"ELEMENTOS ACCIONABLES (elegí por índice):\n{lista}\n\n"
        f"PASOS QUE YA HICISTE EN ESTA SESIÓN:\n{hist}\n\n"
        f"Decidí el PRÓXIMO paso. Respondé SOLO este JSON:\n{_FORMATO}\n\n"
        "Reglas (importantes):\n"
        "- Si el usuario nombra algo por su TEXTO VISIBLE (ej «donde dice Episodio 13», «el botón "
        "ACCEDER»), usá \"clic_texto\" con ESE texto exacto. NO scrollees a ciegas: clic_texto lo "
        "busca en toda la página y elige el elemento clickeable correcto.\n"
        "- Si tu paso anterior NO cambió la página (te lo aviso en la NOTA), ese camino NO funcionó: "
        "probá un elemento o estrategia DISTINTA, NO repitas lo mismo.\n"
        "- STREAMING (Netflix, Crunchyroll, Disney+, etc.): el botón de Reproducir/Ver ahora de una "
        "serie o película SUELE estar OCULTO y solo aparece al pasar el mouse por encima de la tarjeta. "
        "Para reproducir un título, usá la acción \"hover\" con el TEXTO del título: pasa el mouse y "
        "clickea el play que aparece. NO scrollees buscando un botón que no se ve.\n"
        "- PROHIBIDO hacer \"scroll\" más de UNA vez seguida.\n"
        "- Si el OBJETIVO es una PREGUNTA sobre la página o un pedido de análisis/opinión (ej «analizá "
        "esto y decime qué pensás», «qué dice acá»), navegá si hace falta y después usá \"responder\" "
        "con tu respuesta basada en el texto de la página, en \"mensaje\".\n"
        "- Si el OBJETIVO menciona un sitio (crunchyroll, netflix…) y la url no es de ese sitio, \"navegar\" ahí primero.\n"
        "- Para buscar: \"clic\" en la barra, \"escribir\" el término, \"tecla\" Enter.\n"
        "- LOGIN: \"escribir\" el email, \"escribir\" la contraseña, y al final \"clic\" en enviar. "
        "Marcá \"sensible\": true SOLO en ese clic final que ENVÍA credenciales. Abrir el formulario, "
        "navegar o escribir en los campos NO es sensible.\n"
        "- Pago o publicar/enviar mensaje a terceros: \"sensible\": true.\n"
        "- ANTES de \"terminar\": verificá que el resultado coincide con el objetivo (título/sitio correcto). "
        "Usá \"terminar\" con \"mensaje\" breve y HONESTO solo cuando esté de verdad cumplido."
    )


def _parsear(crudo):
    if not crudo:
        return None
    s = crudo.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return None


def _ejecutar(accion, plan, elementos):
    if accion == "navegar":
        return motor.ir(plan.get("url", "") or "")
    if accion == "scroll":
        return motor.agente_accion("scroll")
    if accion == "esperar":
        return motor.agente_accion("esperar")
    if accion == "tecla":
        return motor.agente_accion("tecla", tecla=plan.get("tecla", "Enter"))
    if accion == "clic_texto":
        txt = (plan.get("texto") or "").strip()
        if not txt:
            return {"ok": False, "razon": "clic_texto sin texto"}
        return motor.agente_accion("clic_texto", texto=txt)
    if accion == "hover":
        txt = (plan.get("texto") or "").strip()
        if not txt:
            return {"ok": False, "razon": "hover sin texto"}
        return motor.agente_accion("hover", texto=txt)
    idx = plan.get("indice")
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(elementos):
        return {"ok": False, "razon": f"índice fuera de rango ({idx})"}
    sel = elementos[idx].get("selector")
    if accion == "clic":
        return motor.agente_accion("clic", selector=sel)
    if accion == "escribir":
        return motor.agente_accion("escribir", selector=sel, texto=plan.get("texto", ""))
    return {"ok": False, "razon": f"acción desconocida: {accion}"}


def _detalle(accion, plan):
    if accion == "escribir":
        return f"escribir en elem {plan.get('indice')}"
    if accion == "clic_texto":
        return f"clic_texto «{(plan.get('texto') or '')[:30]}»"
    if accion == "hover":
        return f"hover «{(plan.get('texto') or '')[:30]}»"
    if accion == "navegar":
        return f"navegar {plan.get('url', '')[:50]}"
    if accion == "clic":
        return f"clic en elem {plan.get('indice')}"
    if accion == "tecla":
        return f"tecla {plan.get('tecla', 'Enter')}"
    return accion


def _lo_que_veo(elementos, n=18):
    vis = [f"• {e.get('texto', '').strip()}" for e in elementos[:n] if e.get("texto", "").strip()]
    return "\n".join(vis) if vis else "(no veo elementos con texto claro)"


def _huella(resumen, elementos):
    """Firma del estado de la página: sirve para detectar si una acción cambió algo."""
    return (resumen.get("url", "") + "|" + resumen.get("title", "") + "|" + str(len(elementos))
            + "|" + "|".join((e.get("texto", "") or "")[:18] for e in elementos[:12]))


def _trabado(elementos):
    _sesion["esperando"] = "aclarar"
    return {"ok": True, "resumen": "Necesito tu ayuda acá.",
            "cuerpo": "No logro encontrar solo lo que buscás. Esto es lo que veo clickeable ahora:\n\n"
                      + _lo_que_veo(elementos) + "\n\nDecime el texto exacto del que querés "
                      "(ej «clic en Episodio 13») y lo clickeo directo.", "pregunta": True}


# ── Entrada principal ────────────────────────────────────────────────────────
def ejecutar(texto, emitir=None):
    if not motor.activo():
        return {"ok": True, "resumen": "El navegador no está abierto.",
                "cuerpo": "Primero entrá: «entrá a modo navegador»."}
    if not _llm.disponible():
        return {"ok": True, "resumen": "El cerebro necesita Groq.",
                "cuerpo": "El agente no tiene el modelo disponible (GROQ_API_KEY). Revisá la config."}

    t = (texto or "").strip()

    if _sesion["esperando"] == "confirmar" and _sesion["pendiente"]:
        signo = _si_no(t)
        pend = _sesion["pendiente"]
        _sesion["pendiente"] = None
        _sesion["esperando"] = None
        if signo == "si":
            _sesion["autorizado"] = True   # el resto de ESTA tarea ya quedó autorizado
            r = _ejecutar(pend["accion"], pend["plan"], pend["elementos"])
            _recordar(f"(confirmado) {_detalle(pend['accion'], pend['plan'])} → {'ok' if r.get('ok') else 'falló'}")
            extra = _texto_extra(t)
            if extra:
                _sesion["objetivo"] = (_sesion["objetivo"] + " — además: " + extra).strip()
            return _correr(emitir)
        if signo == "no":
            _recordar("(el usuario rechazó la última acción sensible)")
            return _correr(emitir, nota="El usuario RECHAZÓ la acción anterior. Buscá otra forma o preguntá.")
        _sesion["objetivo"] = t
        _sesion["autorizado"] = False
        return _correr(emitir)

    if _sesion["esperando"] == "aclarar":
        _sesion["esperando"] = None
        _sesion["objetivo"] = (_sesion["objetivo"] + " — " + t).strip(" —") if _sesion["objetivo"] else t
        return _correr(emitir)

    # tarea nueva
    _sesion["objetivo"] = t
    _sesion["autorizado"] = False
    return _correr(emitir)


def _correr(emitir=None, nota="", max_pasos=_MAX_PASOS):
    objetivo = _sesion["objetivo"]
    fallos = 0
    scrolls_seguidos = 0
    ultima_sig = None
    repetidos = 0
    huella_previa = None
    ultima_accion = None

    for paso in range(max_pasos):
        resumen = motor.resumen()
        elementos = motor.elementos()

        # Feedback de progreso: ¿mi acción anterior cambió algo?
        huella = _huella(resumen, elementos)
        if ultima_accion in ("clic", "clic_texto", "hover", "navegar", "tecla") and huella == huella_previa:
            nota = ((nota + " ") if nota else "") + ("Tu paso anterior NO cambió nada en la página "
                    "(mismos elementos). Ese elemento/estrategia no funcionó: probá algo DISTINTO.")
        huella_previa = huella

        # VISIÓN: si hay modelo multimodal, el cerebro MIRA la captura (con números
        # sobre cada elemento) y elige por lo que ve. Si falla, cae a texto solo.
        imagen = None
        if _llm.vision_disponible():
            try:
                imagen = motor.screenshot_anotado()
            except Exception:
                imagen = None
        prompt = _prompt_paso(objetivo, resumen, elementos, _sesion["historial"], nota, con_vision=bool(imagen))
        nota = ""
        if imagen:
            crudo = _llm.pensar_vision(_SISTEMA, prompt, imagen)
            if not crudo:                       # visión falló → texto
                crudo = _llm.pensar(_SISTEMA, prompt)
        else:
            crudo = _llm.pensar(_SISTEMA, prompt)
        plan = _parsear(crudo)
        if not plan:
            log.error(f"[NAV] cerebro: respuesta ilegible: {crudo[:120]!r}")
            return {"ok": True, "resumen": "No pude decidir el próximo paso.",
                    "cuerpo": "El modelo devolvió algo que no pude leer. Mirá el panel y decime cómo seguir."}

        accion = (plan.get("accion") or "").lower()
        razon = plan.get("razon", "")

        if accion == "scroll":
            scrolls_seguidos += 1
        else:
            scrolls_seguidos = 0
        if scrolls_seguidos >= 2:
            log.info("[NAV] corte anti-scroll: pido ayuda en vez de scrollear de nuevo")
            return _trabado(elementos)

        sig = f"{accion}:{plan.get('indice')}:{(plan.get('texto') or '')[:25]}"
        if sig == ultima_sig:
            repetidos += 1
        else:
            repetidos = 0
        ultima_sig = sig
        if repetidos >= 2:
            log.info("[NAV] corte anti-repetición: misma acción repetida")
            return _trabado(elementos)

        if emitir:
            emitir(f"paso {paso + 1}: {accion} — {razon}")
        log.info(f"[NAV] paso {paso + 1}{'👁' if imagen else ''}: {accion} — {razon}")

        if accion == "responder":
            _recordar(f"respondió: {plan.get('mensaje', '')[:50]}")
            return {"ok": True, "resumen": "Te respondo sobre la página.",
                    "cuerpo": plan.get("mensaje") or "No encontré suficiente para responder."}

        if accion == "terminar" or (plan.get("listo") and accion not in ("preguntar", "responder")):
            _recordar(f"terminado: {plan.get('mensaje', '')[:60]}")
            return {"ok": True, "resumen": "Tarea cumplida.",
                    "cuerpo": plan.get("mensaje") or "Listo, lo hice. Mirá el panel."}

        if accion == "preguntar":
            _sesion["esperando"] = "aclarar"
            return {"ok": True, "resumen": "Necesito que me aclares algo.",
                    "cuerpo": plan.get("mensaje") or "¿Cuál de las opciones querés?", "pregunta": True}

        if plan.get("sensible") and not _sesion["autorizado"]:
            _sesion["pendiente"] = {"accion": accion, "plan": plan, "elementos": elementos}
            _sesion["esperando"] = "confirmar"
            return {"ok": True, "resumen": "Confirmá antes de seguir.",
                    "cuerpo": f"Voy a hacer algo con efecto real: {razon}.\n"
                              "Decime «dale» (autorizás esta tarea) o «no» para frenar.",
                    "pregunta": True}

        r = _ejecutar(accion, plan, elementos)
        ultima_accion = accion
        _recordar(f"{_detalle(accion, plan)} → {'ok' if r.get('ok') else 'falló: ' + r.get('razon', '')}")
        if r.get("ok"):
            fallos = 0
        else:
            fallos += 1
            if fallos >= 3:
                return _trabado(elementos)

    return {"ok": True, "resumen": "Pausa: avancé varios pasos.",
            "cuerpo": "Avancé varios pasos pero todavía no lo di por terminado. Esto es lo que veo ahora:\n\n"
                      + _lo_que_veo(motor.elementos()) + "\n\nDecime el texto del que querés y sigo — me acuerdo del hilo."}