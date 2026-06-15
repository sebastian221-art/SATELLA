"""
nucleo/habilidades/navegador/skill.py — NAVEGADOR.
Maneja un navegador real como una persona, en una sesión que queda VIVA, y te la
muestra en vivo en el panel de Satella. Esta es la Fase 4A (el núcleo):

  - entrar/salir del modo navegador (sesión persistente, queda logueada)
  - ir a una URL (visitar = lectura, gratis pero auditado)
  - leer la página → lista de elementos accionables (el "ojo")
  - captura en vivo para el panel

El cerebro autónomo (buscar/poner el video solo, corregir en la misma sesión)
llega en 4B; las recetas y el modo observador en 4C. Acá queda la base sólida y
gobernada sobre la que se monta todo eso.
"""
from nucleo.habilidades import contrato
from . import detector, motor, ojo

NOMBRE = "navegador"
DESCRIPCION = (
    "Controla un navegador real como una persona, en una sesión viva que se ve en el "
    "panel de Satella: entra al modo navegador, visita sitios y lee la página. Cada "
    "acción con efecto pasa por el Gobernador. (Núcleo 4A: el agente autónomo y las "
    "recetas aprendidas llegan después.)"
)
EJEMPLOS = [
    "entrá a modo navegador",
    "andá a youtube.com",
    "qué hay en la página",
    "mostrame una captura",
    "salí del modo navegador",
]
VERSION = "0.4a"

_NO_PW = ("El navegador no está instalado todavía. En tu venv, corré (en PowerShell, "
          "un comando por línea):\n\n    pip install playwright\n    playwright install chromium\n\n"
          "Y reiniciá Satella. Después «entrá a modo navegador».")


def detecta(texto, codigo_adjunto=""):
    return detector.detecta(texto, codigo_adjunto)


def manejar(texto, contexto=None):
    accion, arg = detector.intencion(texto)

    # ── Entrar al modo navegador ──────────────────────────────────────────
    if accion == "entrar":
        if not motor.disponible():
            return contrato.resultado(NOMBRE, "navegador", "Falta instalar Playwright.", _NO_PW, ok=True)
        r = motor.abrir(headless=False)
        if not r.get("ok"):
            cuerpo = ("No pude abrir el navegador. El error exacto fue:\n\n    "
                      + str(r.get("razon", "")) +
                      "\n\nEse mensaje está también en la consola de Satella. "
                      "Decímelo y lo resolvemos.")
            return contrato.resultado(NOMBRE, "navegador", "No pude abrir el navegador.", cuerpo, ok=True)
        from . import cerebro
        cerebro.reset()
        modo_txt = " (en headless — igual lo ves en el panel)" if r.get("headless") else ""
        cuerpo = [f"🌐 **Modo navegador activo{modo_txt}.** La sesión queda viva y la vas a ver en el panel."]
        if r.get("canal") == "chromium":
            cuerpo.append("⚠️ Estoy usando el Chromium incluido, que NO reproduce contenido con DRM "
                          "(Netflix da error M7701). Para que Netflix/Crunchyroll premium anden, instalá "
                          "Google Chrome en el sistema y lo voy a usar solo.")
        if arg:
            ir = motor.ir(arg)
            if ir.get("ok"):
                cuerpo.append(f"Fui a: {ir.get('title') or ir.get('url')}")
            else:
                cuerpo.append(f"(No pude ir a {arg}: {ir.get('razon')})")
        cuerpo.append("\nDecime qué hacer: «andá a …», «qué hay en la página», «mostrame una captura», "
                      "o «salí del modo navegador».")
        return contrato.resultado(NOMBRE, "navegador", "Modo navegador activo.", "\n".join(cuerpo), ok=True)

    # ── Salir ─────────────────────────────────────────────────────────────
    if accion == "salir":
        from . import observador
        if observador.grabando():
            observador.cancelar()  # corta la grabación sin guardar basura
        motor.cerrar()
        from . import cerebro
        cerebro.reset()
        return contrato.resultado(NOMBRE, "navegador", "Salí del modo navegador.",
                                  "🔚 Cerré la sesión del navegador. Volvé a entrar cuando quieras.", ok=True)

    # si llegamos acá sin navegador abierto, recordamos cómo entrar
    if not motor.activo():
        return contrato.resultado(NOMBRE, "navegador", "El navegador no está abierto.",
                                  "Primero entrá: «entrá a modo navegador».", ok=True)

    # ── Mientras observo, el agente NO toca el navegador (vos hacés la tarea) ──
    from . import observador
    if observador.grabando() and accion not in ("observador_guardar", "observador_cancelar", "recetas"):
        return contrato.resultado(NOMBRE, "navegador", "Te estoy observando.",
                                  "👁️ Estoy grabando lo que hacés — el navegador es tuyo, yo no lo toco. "
                                  "Hacé la tarea vos mismo. Cuando termines, decime «guardá la receta como "
                                  "_nombre_», o «salí del observador» para dejar de grabar.", ok=True)

    if accion == "observador_cancelar":
        from . import observador
        if not observador.grabando():
            return contrato.resultado(NOMBRE, "navegador", "No estaba observando.",
                                      "Ya estás en modo normal. Decime qué hago o «modo observador» para grabar.", ok=True)
        observador.cancelar()
        return contrato.resultado(NOMBRE, "navegador", "Salí del modo observador.",
                                  "✋ Dejé de grabar (no guardé nada). Volvés al control normal: decime qué hago.", ok=True)

    # ── Ir a una URL ──────────────────────────────────────────────────────
    if accion == "ir":
        r = motor.ir(arg)
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No pude navegar.",
                                      f"No pude ir a {arg}: {r.get('razon','')}", ok=True)
        return contrato.resultado(NOMBRE, "navegador", f"Estoy en {r.get('title') or r.get('url')}.",
                                  f"📄 {r.get('title','')}\n{r.get('url','')}", ok=True)

    # ── Leer la página (el ojo) ───────────────────────────────────────────
    if accion == "elementos":
        els = motor.elementos()
        st = motor.estado()
        cuerpo = f"📄 {st.get('title','')} — {st.get('url','')}\n\n── Elementos accionables ──\n" + ojo.formatear(els)
        return contrato.resultado(NOMBRE, "navegador", f"{len(els)} elementos en la página.", cuerpo, ok=True)

    # ── Captura ───────────────────────────────────────────────────────────
    if accion == "screenshot":
        st = motor.estado()
        # el panel ya muestra el stream en vivo; acá confirmamos
        return contrato.resultado(NOMBRE, "navegador", "Captura enviada al panel.",
                                  f"📸 Mirá el panel: {st.get('title','')} — {st.get('url','')}", ok=True)

    # ── Estado ────────────────────────────────────────────────────────────
    if accion == "estado":
        st = motor.estado()
        return contrato.resultado(NOMBRE, "navegador", "Estado del navegador.",
                                  f"Activo · {st.get('title','')} — {st.get('url','')}", ok=True)

    # ── Credenciales seguras (llavero del sistema) ─────────────────────────
    if accion == "credencial_guardar":
        from . import credenciales
        if not credenciales.disponible():
            return contrato.resultado(NOMBRE, "navegador", "No tengo llavero disponible.",
                                      "El llavero del sistema no está accesible. Instalá el paquete «keyring» "
                                      "(pip install keyring) y reintentá.", ok=True)
        datos = motor.leer_login_pagina()
        if not datos.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No veo un login en la página.",
                                      "Escribí tu usuario y contraseña en el formulario del navegador (no acá "
                                      "en el chat), y después decime «guardá mi login de _sitio_».", ok=True)
        dom = arg or motor.estado().get("url", "")
        r = credenciales.guardar(dom, datos.get("usuario", ""), datos.get("contrasena", ""))
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No pude guardar.",
                                      f"Falló guardar la credencial: {r.get('razon','')}", ok=True)
        return contrato.resultado(NOMBRE, "navegador", "Login guardado de forma segura.",
                                  f"🔐 Guardé tu login de **{r['dominio']}** en el llavero del sistema "
                                  f"(usuario: {r.get('usuario') or '—'}). La contraseña quedó cifrada por Windows, "
                                  "nunca pasó por el chat. Ahora puedo iniciar sesión sola cuando lo pidas.", ok=True)

    if accion == "credencial_borrar":
        from . import credenciales
        r = credenciales.borrar(arg or "")
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No encontré esa credencial.",
                                      f"No tengo guardado un login de «{arg}».", ok=True)
        return contrato.resultado(NOMBRE, "navegador", "Credencial borrada.",
                                  f"🗑️ Borré tu login de **{r['dominio']}** del llavero.", ok=True)

    if accion == "credenciales":
        from . import credenciales
        cs = credenciales.listar()
        if not cs:
            return contrato.resultado(NOMBRE, "navegador", "No tengo logins guardados.",
                                      "Todavía no guardé ninguno. Iniciá sesión en un sitio y decime "
                                      "«guardá mi login de _sitio_».", ok=True)
        lineas = "\n".join(f"• **{c['dominio']}** (usuario: {c['usuario']})" for c in cs)
        return contrato.resultado(NOMBRE, "navegador", f"Tengo {len(cs)} login(s) guardado(s).",
                                  "Logins en el llavero (sin mostrar contraseñas):\n\n" + lineas, ok=True)

    # ── Memoria de navegación (lo aprendido) ───────────────────────────────
    if accion == "memoria_lista":
        from . import memoria
        ms = memoria.listar()
        if not ms:
            return contrato.resultado(NOMBRE, "navegador", "Todavía no aprendí procesos.",
                                      "Cada vez que complete una tarea, la guardo y la repito sola la próxima. "
                                      "Pedime algo y empiezo a aprender.", ok=True)
        lineas = "\n".join(f"• **{m['dominio']}**: {m['objetivo'][:60]} ({m['pasos']} pasos, {m['exitos']}x)" for m in ms[:20])
        return contrato.resultado(NOMBRE, "navegador", f"Aprendí {len(ms)} proceso(s).",
                                  "Esto ya lo sé hacer solo (lo repito cuando lo pidas):\n\n" + lineas, ok=True)

    # ── Conocimiento del mundo web ─────────────────────────────────────────
    if accion == "conocimiento_enseñar":
        from . import conocimiento
        dom = arg.get("dominio") if isinstance(arg, dict) else None
        nota = arg.get("nota") if isinstance(arg, dict) else None
        r = conocimiento.anotar(dom, nota)
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No pude anotar eso.",
                                      "Decímelo así: «recordá que en _sitio_, _lo que sea_».", ok=True)
        if r.get("ya_sabia"):
            return contrato.resultado(NOMBRE, "navegador", "Eso ya lo sabía.",
                                      f"Ya tenía esa nota sobre {dom}.", ok=True)
        return contrato.resultado(NOMBRE, "navegador", "Anotado.",
                                  f"🧠 Aprendido sobre **{r['dominio']}**: «{nota}». Lo voy a tener en cuenta "
                                  "cada vez que navegue ahí.", ok=True)

    if accion == "conocimiento_ver":
        from . import conocimiento
        if not arg:
            todo = conocimiento.listar()
            if not todo:
                return contrato.resultado(NOMBRE, "navegador", "Sé lo básico del internet.",
                                          "Tengo el conocimiento general de la web. Preguntame por un sitio: "
                                          "«qué sabés de netflix».", ok=True)
            doms = ", ".join(todo.keys())
            return contrato.resultado(NOMBRE, "navegador", "Sitios que conozco.",
                                      f"Conozco: {doms}. Preguntame por uno: «qué sabés de crunchyroll».", ok=True)
        notas = conocimiento.de_dominio(arg)
        if not notas:
            return contrato.resultado(NOMBRE, "navegador", f"De {arg} todavía no sé nada particular.",
                                      "Uso mi conocimiento general. Enseñame: «recordá que en "
                                      f"{arg}, _lo que sea_».", ok=True)
        lineas = "\n".join(f"• {n}" for n in notas)
        return contrato.resultado(NOMBRE, "navegador", f"Lo que sé de {arg}:",
                                  f"Sobre **{arg}**:\n\n" + lineas, ok=True)

    # ── Modo observador + recetas (Fase 4C) ───────────────────────────────
    if accion == "observador_iniciar":
        from . import observador
        r = observador.iniciar()
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No pude empezar a observar.",
                                      f"No arrancó la grabación: {r.get('razon','')}", ok=True)
        cuerpo = (f"👁️ **Observando.** Estoy mirando lo que hacés en {r.get('dominio','el sitio')}. "
                  "Hacé la tarea vos mismo en el navegador (clics, escribir, navegar) y voy grabando "
                  "cada paso.\n\nCuando termines, decime «guardá la receta como _nombre_» (ej: «guardá "
                  "la receta como ver wistoria») y la voy a poder repetir sola cuando quieras.\n\n"
                  "Ojo: las contraseñas NO las guardo.")
        return contrato.resultado(NOMBRE, "navegador", "Observando lo que hacés.", cuerpo, ok=True)

    if accion == "observador_guardar":
        from . import observador
        if not observador.grabando():
            return contrato.resultado(NOMBRE, "navegador", "No estaba observando.",
                                      "No tenía ninguna grabación activa. Empezá con «modo observador».", ok=True)
        if not arg:
            return contrato.resultado(NOMBRE, "navegador", "¿Con qué nombre la guardo?",
                                      "Decime el nombre: «guardá la receta como _nombre_».", ok=True)
        r = observador.detener_y_guardar(arg)
        nota_pw = f" (incluye {r['pw']} campo(s) de contraseña que NO guardé — esos los completás vos)" if r.get("pw") else ""
        cuerpo = (f"✅ Guardé la receta **{r['nombre']}** con {r['n']} pasos{nota_pw}.\n\n"
                  f"Cuando quieras, decime «hacé la receta {r['nombre']}» y la repito sola.")
        return contrato.resultado(NOMBRE, "navegador", f"Receta «{r['nombre']}» guardada.", cuerpo, ok=True)

    if accion == "recetas":
        from . import observador
        recs = observador.listar()
        if not recs:
            return contrato.resultado(NOMBRE, "navegador", "Todavía no tengo recetas.",
                                      "No aprendí ninguna todavía. Mostrame una con «modo observador».", ok=True)
        lineas = "\n".join(f"• **{c['nombre']}** — {c['titulo']} ({c['dominio']}, {c['n']} pasos)" for c in recs)
        return contrato.resultado(NOMBRE, "navegador", f"Tengo {len(recs)} receta(s).",
                                  "Recetas que aprendí:\n\n" + lineas + "\n\nUsá «hacé la receta _nombre_».", ok=True)

    if accion == "receta":
        from . import observador
        nombre = arg.get("nombre") if isinstance(arg, dict) else arg
        variable = arg.get("variable") if isinstance(arg, dict) else None
        r = observador.reproducir(nombre, variable=variable)
        if not r.get("ok"):
            if r.get("razon") == "no_existe":
                recs = observador.listar()
                disp = ", ".join(c["nombre"] for c in recs) if recs else "(ninguna todavía)"
                return contrato.resultado(NOMBRE, "navegador", "No tengo esa receta.",
                                          f"No encontré «{nombre}». Las que tengo: {disp}.", ok=True)
            return contrato.resultado(NOMBRE, "navegador", "No pude reproducir la receta.",
                                      f"Falló: {r.get('razon','')}", ok=True)
        partes = [f"▶️ Reproduje **{r.get('titulo', nombre)}**: {r.get('hechos', 0)}/{r.get('total', 0)} pasos ok."]
        if variable:
            partes.append(f"Usé «{variable}» como dato" + ("." if r.get("variable_aplicada") else " (pero no encontré dónde escribirlo)."))
        if r.get("fallidos"):
            partes.append(f"{r['fallidos']} paso(s) no salieron (la página puede haber cambiado). Mirá el panel.")
        if r.get("pendientes_pw"):
            partes.append(f"{r['pendientes_pw']} campo(s) de contraseña quedaron vacíos — completalos vos.")
        return contrato.resultado(NOMBRE, "navegador", "Receta reproducida.", " ".join(partes), ok=True)

    # ── Control del reproductor de video (Fase 4D) ─────────────────────────
    if accion == "video":
        r = motor.reproductor(arg.get("accion"), arg.get("valor"))
        if not r.get("ok"):
            return contrato.resultado(NOMBRE, "navegador", "No pude controlar el video.",
                                      f"No hay un reproductor manejable ahí ({r.get('razon','')}). "
                                      "Asegurate de estar en la página del video.", ok=True)
        etq = {"play": "▶️ Reproduciendo", "pause": "⏸️ Pausado", "minuto": "⏩ Salté al minuto",
               "adelantar": "⏩ Adelanté", "atrasar": "⏪ Retrocedí", "volumen": "🔊 Volumen",
               "silenciar": "🔇 Silenciado", "activar_sonido": "🔊 Sonido activado",
               "velocidad": "⚡ Velocidad", "pantalla_completa": "⛶ Pantalla completa"}.get(arg.get("accion"), "Listo")
        det = f" — {r.get('t',0)}s / {r.get('dur',0)}s · vol {r.get('vol',0)}% · {r.get('velocidad',1)}x"
        return contrato.resultado(NOMBRE, "navegador", "Reproductor controlado.", etq + det, ok=True)

    # ── Instrucción para el agente (4B) ───────────────────────────────────
    if accion == "instruccion":
        from . import cerebro
        rep = cerebro.ejecutar(texto)
        return contrato.resultado(NOMBRE, "navegador", rep.get("resumen", "Listo."),
                                  rep.get("cuerpo", ""), ok=True)

    return contrato.resultado(NOMBRE, "navegador", "No entendí la orden del navegador.",
                              "Probá «andá a …», «qué hay en la página» o «salí del modo navegador».", ok=True)