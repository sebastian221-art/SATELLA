"""
nucleo/habilidades/navegador/motor.py
EL MOTOR DEL NAVEGADOR. Maneja un Chromium real (Playwright) con PERFIL
PERSISTENTE — las sesiones quedan logueadas entre usos, como tu navegador.

POR QUÉ API ASYNC (y no sync): la API sync de Playwright es problemática en
hilos secundarios sobre Windows (choca con el event loop de asyncio al lanzar el
subproceso del navegador → NotImplementedError mudo). La forma robusta y soportada
es la API ASYNC corriendo su PROPIO event loop en un HILO DEDICADO (ProactorEventLoop
en Windows, que sí soporta subprocesos). Cualquier parte de Satella manda una
corrutina a ese loop con run_coroutine_threadsafe y espera el resultado. Nunca se
cruzan hilos y no se cae.

Degrada con gracia: si Playwright no está, `disponible()` es False y la skill te
dice cómo instalarlo. Permisos: ir a una URL = LECTURA; clic/escribir = NAVEGACION
(pasa por el Gobernador).
"""
import asyncio
import base64
import logging
import re
import sys
import threading
from pathlib import Path

from nucleo.habilidades.gobernador import motor as _gob, politica as _gpol, auditoria as _aud

log = logging.getLogger("satella.navegador")

_PERFIL = Path(__file__).resolve().parents[3] / "datos" / "navegador" / "perfil"

try:
    import playwright  # noqa: F401
    _PW_OK = True
except Exception:
    _PW_OK = False


def disponible() -> bool:
    return _PW_OK


# ── Estado del hilo/loop dedicado ────────────────────────────────────────────
_loop = None          # asyncio loop que vive en el hilo dedicado
_thread = None        # el hilo dedicado
_pw = None            # instancia de playwright async
_ctx = None           # contexto persistente
_page = None          # página activa
_activo = False

# ── Estado del grabador (modo observador, Fase 4C) ──────────────────────────
_grabando = False
_pasos_grabados = []
_binding_listo = False
_canal = "chromium"        # "chrome" (con DRM) o "chromium" (sin DRM de Netflix)


class _Fut:
    """Señal cruzada de hilos para el arranque."""
    __slots__ = ("ev", "val", "err")

    def __init__(self):
        self.ev = threading.Event()
        self.val = None
        self.err = None

    def ok(self, v):
        self.val = v
        self.ev.set()

    def fail(self, e):
        self.err = e
        self.ev.set()

    def result(self, timeout=60):
        if not self.ev.wait(timeout):
            raise TimeoutError("El navegador no arrancó a tiempo.")
        if self.err:
            raise self.err
        return self.val


async def _arrancar(headless: bool):
    global _pw, _ctx, _page, _activo, _canal
    from playwright.async_api import async_playwright
    _pw = await async_playwright().start()
    _PERFIL.mkdir(parents=True, exist_ok=True)
    base = dict(user_data_dir=str(_PERFIL), headless=headless,
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"])
    # 1) Chrome del sistema: trae Widevine/DRM → Netflix, Crunchyroll premium, etc.
    try:
        _ctx = await _pw.chromium.launch_persistent_context(channel="chrome", **base)
        _canal = "chrome"
    except Exception as e:
        log.info(f"[NAV] sin Chrome del sistema ({e!r}); uso Chromium incluido (sin DRM de Netflix)")
        _ctx = await _pw.chromium.launch_persistent_context(**base)
        _canal = "chromium"
    _page = _ctx.pages[0] if _ctx.pages else await _ctx.new_page()
    _activo = True
    log.info(f"[NAV] navegador listo (canal={_canal})")


def _run_loop(ready: _Fut, headless: bool):
    """Hilo dedicado: crea un loop propio (Proactor en Windows) y lo mantiene vivo."""
    global _loop, _activo
    try:
        loop = asyncio.ProactorEventLoop() if sys.platform.startswith("win") else asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _loop = loop
        loop.run_until_complete(_arrancar(headless))
    except Exception as e:
        import traceback
        log.error(f"[NAV] fallo al abrir (headless={headless}): {repr(e)}")
        log.debug(traceback.format_exc())
        try:
            if _loop:
                _loop.close()
        except Exception:
            pass
        _loop = None
        ready.fail(e)
        return
    ready.ok(True)
    loop.run_forever()                     # queda vivo para las órdenes siguientes
    # apagado prolijo: cancelar tareas pendientes antes de cerrar el loop
    try:
        pendientes = asyncio.all_tasks(loop)
        for t in pendientes:
            t.cancel()
        if pendientes:
            loop.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
    except Exception:
        pass
    try:
        loop.close()
    except Exception:
        pass
    _activo = False


def _submit(coro, timeout=45):
    """Manda una corrutina al loop del navegador y espera su resultado."""
    if not _loop:
        raise RuntimeError("El loop del navegador no está activo.")
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    return fut.result(timeout)


# ── API pública ──────────────────────────────────────────────────────────────
def activo() -> bool:
    return _activo


def abrir(headless: bool = False) -> dict:
    """
    Arranca el navegador. Intenta el modo pedido y, si falla, reintenta en
    headless (el panel igual lo muestra por screenshots). Devuelve estado.
    """
    global _thread
    if not _PW_OK:
        return {"ok": False, "razon": "Playwright no está instalado."}
    if _activo and _thread and _thread.is_alive():
        return {"ok": True, "ya_estaba": True, **estado()}

    intentos = [headless] if headless else [False, True]
    ultimo = "desconocido"
    for hl in intentos:
        ready = _Fut()
        _thread = threading.Thread(target=_run_loop, args=(ready, hl), daemon=True)
        _thread.start()
        try:
            ready.result(timeout=60)
            log.info(f"[NAV] navegador abierto (headless={hl})")
            return {"ok": True, "headless": hl, **estado()}
        except Exception as e:
            ultimo = repr(e)
            log.error(f"[NAV] no pude abrir (headless={hl}): {repr(e)}")
            continue
    return {"ok": False, "razon": f"No se pudo abrir el navegador: {ultimo}"}


def cerrar() -> dict:
    global _activo
    if not _activo:
        return {"ok": True, "ya_cerrado": True}

    async def _c():
        try:
            await _ctx.close()
            await _pw.stop()
        except Exception:
            pass

    try:
        _submit(_c(), timeout=20)
    except Exception:
        pass
    try:
        _loop.call_soon_threadsafe(_loop.stop)
    except Exception:
        pass
    _activo = False
    return {"ok": True}


def ir(url: str) -> dict:
    """Navega a una URL. Visitar = LECTURA (mirar), pasa igual por la auditoría."""
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    v = _gob.evaluar(f"navegar a {url}", nivel=_gpol.LECTURA, objetivo=url)
    if v["veredicto"] == _gpol.DENEGADO:
        return {"ok": False, "razon": v["razon"]}

    async def _go():
        await _page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await _descartar_overlays(_page)
        except Exception:
            pass
        return {"url": _page.url, "title": await _page.title()}

    try:
        return {"ok": True, **_submit(_go())}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}


def estado() -> dict:
    if not _activo:
        return {"activo": False}
    try:
        m = _gob.modo()
    except Exception:
        m = "normal"

    async def _st():
        return {"url": _page.url, "title": await _page.title()}

    try:
        return {"activo": True, "modo": m, "canal": _canal, **_submit(_st(), timeout=10)}
    except Exception:
        return {"activo": True, "modo": m, "canal": _canal, "url": "", "title": ""}


def screenshot_b64() -> str:
    """JPEG de la página actual en base64 (para el panel en vivo)."""
    if not _activo:
        return ""

    async def _shot():
        png = await _page.screenshot(type="jpeg", quality=55, full_page=False)
        return base64.b64encode(png).decode()

    try:
        return _submit(_shot(), timeout=15)
    except Exception:
        return ""


def screenshot_anotado() -> str:
    """JPEG con un número dibujado sobre cada elemento accionable (set-of-marks),
    para que el cerebro con visión MIRE la página y elija por número. Requiere que
    elementos() se haya llamado antes (es lo que pone los data-sat)."""
    if not _activo:
        return ""
    from . import ojo

    async def _shot():
        try:
            await _page.evaluate(ojo.JS_MARCAR)
        except Exception:
            pass
        png = await _page.screenshot(type="jpeg", quality=60, full_page=False)
        try:
            await _page.evaluate(ojo.JS_DESMARCAR)
        except Exception:
            pass
        return base64.b64encode(png).decode()

    try:
        return _submit(_shot(), timeout=15)
    except Exception:
        return ""


def elementos() -> list:
    """Lista de elementos accionables de la página (el 'ojo')."""
    if not _activo:
        return []
    from . import ojo

    async def _ojo():
        return await _page.evaluate(ojo.JS_EXTRAER) or []

    try:
        return _submit(_ojo())
    except Exception as e:
        log.error(f"[NAV] ojo falló: {repr(e)}")
        return []


def resumen() -> dict:
    """Resumen de la página para el cerebro: url, título, encabezados, texto."""
    if not _activo:
        return {}
    from . import ojo

    async def _r():
        return await _page.evaluate(ojo.JS_RESUMEN) or {}

    try:
        return _submit(_r(), timeout=10)
    except Exception:
        return {}


async def _descartar_overlays(page):
    """Intenta cerrar banners de cookies/consentimiento que bloquean los clics."""
    for t in ("Aceptar todo", "Aceptar", "Accept all", "Accept All", "Accept",
              "I Agree", "Got it", "Entendido", "De acuerdo", "Allow all"):
        try:
            loc = page.get_by_role("button", name=t, exact=False).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=1500)
                await page.wait_for_timeout(400)
                return True
        except Exception:
            continue
    return False


async def _hover_y_reproducir(page, texto):
    """Pasa el mouse por encima de una tarjeta (revela controles ocultos como en
    Netflix/Crunchyroll) y, si aparece un botón de reproducir, lo clickea."""
    try:
        await _descartar_overlays(page)
    except Exception:
        pass
    # 1) encontrar la tarjeta por su texto y hacer hover
    objetivo = None
    for est in (
        lambda: page.get_by_text(texto, exact=False),
        lambda: page.locator(f'[aria-label*="{texto}"]') if texto else None,
    ):
        try:
            loc = est()
            if loc is None:
                continue
            loc = loc.first
            if await loc.count():
                await loc.scroll_into_view_if_needed(timeout=3000)
                await loc.hover(timeout=3000)
                objetivo = loc
                break
        except Exception:
            continue
    await page.wait_for_timeout(900)   # dar tiempo a que aparezca el control
    # 2) clickear el botón de reproducir que ahora debería estar visible
    for est in (
        lambda: page.get_by_role("button", name=re.compile(r"reprod|ver ahora|play|watch", re.I)),
        lambda: page.get_by_role("link", name=re.compile(r"reprod|ver ahora|play|watch", re.I)),
        lambda: page.locator('[aria-label*="Reproducir"], [aria-label*="reproducir"], [aria-label*="Play"], [data-uia*="play"]'),
    ):
        try:
            b = est().first
            if await b.count() and await b.is_visible():
                await b.click(timeout=3500)
                return True
        except Exception:
            continue
    # 3) si no apareció botón, al menos clickeamos la tarjeta para abrir su página
    if objetivo is not None:
        try:
            await objetivo.click(timeout=3000)
            return True
        except Exception:
            pass
    return False


async def _clic_por_texto(page, texto):
    """Clic robusto por texto: prefiere elementos REALMENTE clickeables (link/botón)
    sobre texto suelto, y descarta overlays antes."""
    try:
        await _descartar_overlays(page)
    except Exception:
        pass
    estrategias = (
        lambda: page.get_by_role("link", name=texto, exact=False),
        lambda: page.get_by_role("button", name=texto, exact=False),
        lambda: page.locator("a, button, [role=button], [onclick]").filter(has_text=texto),
        lambda: page.get_by_text(texto, exact=False),
    )
    for est in estrategias:
        try:
            loc = est().first
            if not await loc.count():
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            await loc.click(timeout=4000)
            return True
        except Exception:
            continue
    raise Exception(f"no encontré nada clickeable con el texto '{texto}'")


def agente_accion(tipo: str, selector: str = None, texto: str = None, tecla: str = None) -> dict:
    """
    Ejecuta una acción del AGENTE (4B) sobre la página viva. Va auditada pero sin
    confirmación paso a paso: la tarea que dio el usuario ES la autorización.
    Las acciones sensibles (enviar/publicar/comprar/login) las frena el cerebro
    antes de llegar acá.
    """
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}

    async def _do():
        if tipo == "clic":
            await _page.locator(selector).first.click(timeout=8000)
            await _page.wait_for_timeout(1600)   # dar tiempo a navegación/SPA
        elif tipo == "clic_texto":
            await _clic_por_texto(_page, texto or "")
            await _page.wait_for_timeout(1600)
        elif tipo == "hover":
            # pasar el mouse por encima revela controles ocultos (botón de reproducir
            # en Netflix/Crunchyroll). Luego, si aparece un botón de play, lo clickea.
            await _hover_y_reproducir(_page, texto or "")
            await _page.wait_for_timeout(1400)
        elif tipo == "escribir":
            loc = _page.locator(selector).first
            try:
                await loc.click(timeout=5000)
            except Exception:
                pass
            await loc.fill(texto or "", timeout=8000)
            await _page.wait_for_timeout(600)
        elif tipo == "tecla":
            await _page.keyboard.press(tecla or "Enter")
            await _page.wait_for_timeout(1600)
        elif tipo == "scroll":
            await _page.mouse.wheel(0, 700)
            await _page.wait_for_timeout(800)
        elif tipo == "esperar":
            await _page.wait_for_timeout(1500)
        return {"url": _page.url}

    try:
        r = _submit(_do(), timeout=25)
        try:
            # NO guardamos el texto tipeado: puede ser una contraseña. Solo su largo.
            _aud.registrar({"evento": "agente", "tipo": tipo,
                            "selector": (selector or "")[:80],
                            "texto_len": len(texto) if texto else 0})
        except Exception:
            pass
        return {"ok": True, **r}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}


# ── Primitivas con efecto (las usará el agente en 4B) — gobernadas ───────────
def clic(selector: str, propio: bool = False) -> dict:
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}
    v = _gob.evaluar(f"clic en {selector}", nivel=_gpol.NAVEGACION,
                           objetivo=estado().get("url", ""), propio=propio)
    if v["veredicto"] == _gpol.DENEGADO:
        return {"ok": False, "razon": v["razon"]}
    if v["veredicto"] == _gpol.CONFIRMAR:
        return {"ok": False, "confirmar": True, "token": v.get("token"), "razon": v["razon"]}

    async def _clic():
        await _page.click(selector, timeout=8000)
        return {"url": _page.url}

    try:
        return {"ok": True, **_submit(_clic())}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}


def escribir(selector: str, texto: str, propio: bool = False) -> dict:
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}
    v = _gob.evaluar(f"escribir en {selector}", nivel=_gpol.NAVEGACION,
                           objetivo=estado().get("url", ""), propio=propio)
    if v["veredicto"] == _gpol.DENEGADO:
        return {"ok": False, "razon": v["razon"]}
    if v["veredicto"] == _gpol.CONFIRMAR:
        return {"ok": False, "confirmar": True, "token": v.get("token"), "razon": v["razon"]}

    async def _esc():
        await _page.fill(selector, texto, timeout=8000)
        return {"ok": True}

    try:
        return {"ok": True, **_submit(_esc())}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}


# ── Grabador (modo observador, Fase 4C) ─────────────────────────────────────
# JS que se auto-instala en cada página: escucha clics y cambios de campos y
# avisa a Python vía el binding window._satEvento. Captura un selector robusto
# (id si hay, si no una ruta css) y el texto visible, para poder reproducir.
_JS_GRABADOR = r"""
(function(){
  if (window.__satGrab) return;
  window.__satGrab = true;
  function sel(el){
    if(!el || el.nodeType!==1) return '';
    if(el.id) return '#'+CSS.escape(el.id);
    var path=[], e=el, depth=0;
    while(e && e.nodeType===1 && depth<5){
      var s=e.tagName.toLowerCase();
      var p=e.parentElement;
      if(p){
        var i=1, sib=e;
        while(sib=sib.previousElementSibling){ if(sib.tagName===e.tagName) i++; }
        s+=':nth-of-type('+i+')';
      }
      path.unshift(s); e=p; depth++;
    }
    return path.join(' > ');
  }
  function txt(el){
    var t = el.innerText || el.value || (el.getAttribute && (el.getAttribute('aria-label')||el.alt)) || '';
    return (''+t).trim().replace(/\s+/g,' ').slice(0,80);
  }
  document.addEventListener('click', function(ev){
    var el = ev.target.closest('a,button,[role=button],[onclick],input,select,textarea,[tabindex]') || ev.target;
    try{ window._satEvento({tipo:'click', selector:sel(el), texto:txt(el), tag:el.tagName.toLowerCase(), url:location.href}); }catch(e){}
  }, true);
  document.addEventListener('change', function(ev){
    var el=ev.target;
    if(!el || !('value' in el)) return;
    var pw = el.type==='password';
    try{ window._satEvento({tipo:'input', selector:sel(el), texto:(el.name||el.id||''),
         valor: pw?'***':(''+(el.value||'')).slice(0,200), password:pw, url:location.href}); }catch(e){}
  }, true);
})();
"""


def _on_evento(source, ev):
    """Callback del binding: corre en el loop del navegador. Solo apila si grabamos."""
    if _grabando and isinstance(ev, dict):
        _pasos_grabados.append(ev)


def iniciar_grabacion(inicio_url: str = None) -> dict:
    """Empieza a observar: instala el grabador y limpia los pasos."""
    global _grabando, _pasos_grabados, _binding_listo
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}

    async def _go():
        global _binding_listo
        if not _binding_listo:
            await _ctx.expose_binding("_satEvento", _on_evento)
            await _ctx.add_init_script(_JS_GRABADOR)   # futuras páginas
            _binding_listo = True
        await _page.evaluate(_JS_GRABADOR)             # página actual ya cargada
        return True

    try:
        _submit(_go())
    except Exception as e:
        return {"ok": False, "razon": repr(e)}
    _pasos_grabados = []
    if inicio_url:
        _pasos_grabados.append({"tipo": "navegar", "url": inicio_url})
    _grabando = True
    log.info("[NAV] grabación iniciada (modo observador)")
    return {"ok": True}


def detener_grabacion() -> list:
    """Para de observar y devuelve los pasos grabados."""
    global _grabando
    _grabando = False
    log.info(f"[NAV] grabación detenida — {len(_pasos_grabados)} pasos")
    return list(_pasos_grabados)


def reproducir_pasos(pasos: list, variable: str = None) -> dict:
    """Repite una receta. Self-heal: si el selector falla, prueba por texto.
    Si se pasa `variable`, reemplaza el valor del PRIMER campo de texto grabado
    (típicamente la barra de búsqueda) — eso hace la receta parametrizable."""
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}

    async def _rep():
        hechos, fallidos, pendientes_pw = 0, 0, 0
        var_usada = False
        for p in pasos:
            t = p.get("tipo")
            try:
                if t == "navegar":
                    await _page.goto(p.get("url", ""), wait_until="domcontentloaded", timeout=30000)
                    try:
                        await _descartar_overlays(_page)
                    except Exception:
                        pass
                    hechos += 1
                elif t == "click":
                    ok = False
                    if p.get("selector"):
                        try:
                            await _page.locator(p["selector"]).first.click(timeout=4000)
                            ok = True
                        except Exception:
                            ok = False
                    if not ok and p.get("texto"):
                        try:
                            await _clic_por_texto(_page, p["texto"])
                            ok = True
                        except Exception:
                            ok = False
                    hechos += 1 if ok else 0
                    fallidos += 0 if ok else 1
                elif t == "input":
                    if p.get("password"):
                        pendientes_pw += 1
                        continue
                    # parametrización: el primer campo de texto recibe la variable
                    valor = p.get("valor", "")
                    if variable and not var_usada:
                        valor = variable
                        var_usada = True
                    try:
                        await _page.locator(p["selector"]).first.fill(valor, timeout=6000)
                        hechos += 1
                    except Exception:
                        fallidos += 1
                await _page.wait_for_timeout(1100)
            except Exception:
                fallidos += 1
        return {"hechos": hechos, "fallidos": fallidos, "pendientes_pw": pendientes_pw, "variable_aplicada": var_usada}

    try:
        return {"ok": True, **_submit(_rep(), timeout=140)}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}


# ── Control del reproductor de video (Fase 4D) ──────────────────────────────
def reproductor(accion: str, valor=None) -> dict:
    """Controla el <video> HTML5 de la página: play/pause/minuto/volumen/velocidad/etc."""
    if not _activo:
        return {"ok": False, "razon": "El navegador no está abierto."}

    async def _vid():
        return await _page.evaluate(
            """(args) => {
                const acc = args[0], val = args[1];
                const vids = Array.from(document.querySelectorAll('video'));
                // elegir el video que de verdad tiene contenido (el reproductor real)
                let v = vids.find(x => x.duration && !isNaN(x.duration) && x.offsetWidth>100) || vids[0];
                if(!v) return {ok:false, razon:'no hay video en la página'};
                try {
                    if(acc==='play'){ v.play(); }
                    else if(acc==='pause'){ v.pause(); }
                    else if(acc==='minuto'){ v.currentTime = val*60; }
                    else if(acc==='segundo'){ v.currentTime = val; }
                    else if(acc==='adelantar'){ v.currentTime = Math.min((v.duration||1e9), v.currentTime + val); }
                    else if(acc==='atrasar'){ v.currentTime = Math.max(0, v.currentTime - val); }
                    else if(acc==='volumen'){ v.muted=false; v.volume = Math.max(0, Math.min(1, val/100)); }
                    else if(acc==='silenciar'){ v.muted = true; }
                    else if(acc==='activar_sonido'){ v.muted = false; }
                    else if(acc==='velocidad'){ v.playbackRate = val; }
                    else if(acc==='pantalla_completa'){ if(v.requestFullscreen) v.requestFullscreen(); }
                } catch(e) { return {ok:false, razon:''+e}; }
                return {ok:true, t: Math.round(v.currentTime), dur: Math.round(v.duration||0),
                        vol: Math.round(v.volume*100), pausado: v.paused, velocidad: v.playbackRate};
            }""",
            [accion, valor],
        )

    try:
        r = _submit(_vid(), timeout=15)
        if not r.get("ok"):
            return {"ok": False, "razon": r.get("razon", "sin video")}
        return {"ok": True, **r}
    except Exception as e:
        return {"ok": False, "razon": repr(e)}