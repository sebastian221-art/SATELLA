"""
Servidor Flask + SocketIO de Satella.
Cambio: cada emit 'satella_responde' ahora incluye 'voz' para que la interfaz
muestre la etiqueta (echidna|ram|rem|emilia).
Cambio Fase 2A: se registra el editor de código (/editor) sin tocar el chat.
"""
import logging
import threading
import time
import os
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

from config import (HOST, PORT, VOZ_HABILITADA, MINUTOS_SILENCIO_INICIACION, SATELLA_ROOT)
from nucleo import memoria, rag
from nucleo.satella import procesar_mensaje, iniciar_conversacion, cerrar_sesion
from interfaz.editor_backend import registrar_editor
from nucleo.habilidades import navegador

log = logging.getLogger("satella.servidor")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'satella_secret_2024'
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    max_http_buffer_size=10 * 1024 * 1024
)

# Estado global como dict mutable — evita problemas con global en threads
_estado = {
    "ultimo_mensaje_ts": 0.0,
    "cliente_conectado": False,
    "voz_activa": VOZ_HABILITADA,
    "saludo_enviado": False,   # evita doble saludo en reconexión rápida
    "nav_stream": False,       # ¿está corriendo el streaming del panel del navegador?
}

FRONTEND_PATH = os.path.join(SATELLA_ROOT, "interfaz", "frontend", "satella.html")

# Fase 2A: ruta /editor + eventos del editor de código.
registrar_editor(app, socketio)

# Canal de progreso: las habilidades lentas (Claude Code) avisan "sigo trabajando"
# y el mensaje llega al chat en vivo (evento 'satella_progreso').
from nucleo import progreso
progreso.set_sink(lambda txt: socketio.emit('satella_progreso', {'texto': txt}))


@app.route('/')
def index():
    with open(FRONTEND_PATH, encoding='utf-8') as f:
        resp = app.make_response(render_template_string(f.read()))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@socketio.on('connect')
def on_connect():
    _estado["cliente_conectado"] = True
    _estado["ultimo_mensaje_ts"] = time.time()
    log.info("Cliente conectado")

    # Solo enviar saludo si no se envió ya en los últimos 10 segundos
    if _estado["saludo_enviado"]:
        return

    _estado["saludo_enviado"] = True

    def saludo_inicial():
        time.sleep(1.5)
        try:
            resultado = iniciar_conversacion(voz_habilitada=_estado["voz_activa"])
            texto = resultado['respuesta']
            log.info(f"[SALUDO] ({len(texto)} chars) {texto}")
            socketio.emit('satella_responde', {
                'texto': texto,
                'audio': resultado.get('audio_b64'),
                'voz': resultado.get('voz', 'echidna'),
                'iniciacion': True,
            })
        except Exception as e:
            log.error(f"Error saludo inicial: {e}")

    threading.Thread(target=saludo_inicial, daemon=True).start()


@socketio.on('disconnect')
def on_disconnect():
    _estado["cliente_conectado"] = False
    log.info("Cliente desconectado — cerrando sesión")
    # Reset saludo después de 15 segundos (si reconecta antes, no manda otro)
    def reset_saludo():
        time.sleep(15)
        _estado["saludo_enviado"] = False
    threading.Thread(target=reset_saludo, daemon=True).start()
    try:
        cerrar_sesion()
    except Exception as e:
        log.error(f"Error cerrando sesión: {e}")


def _stream_navegador():
    """Mientras el navegador esté vivo, emite la pantalla al panel de Satella (~1 fps)."""
    _estado["nav_stream"] = True
    log.info("[NAV] streaming del panel iniciado")
    try:
        while navegador.motor.activo():
            b64 = navegador.motor.screenshot_b64()
            if b64:
                socketio.emit('navegador_frame', {'img': b64, 'estado': navegador.motor.estado()})
            socketio.sleep(1.0)
    finally:
        _estado["nav_stream"] = False
        socketio.emit('navegador_cerrado', {})
        log.info("[NAV] streaming del panel detenido")


@socketio.on('mensaje')
def on_mensaje(data):
    _estado["ultimo_mensaje_ts"] = time.time()

    texto_user = data.get('texto', '').strip()
    if not texto_user:
        return

    log.info(f"[USER] {texto_user}")
    emit('satella_pensando', {'estado': True})

    try:
        resultado = procesar_mensaje(texto_user, voz_habilitada=_estado["voz_activa"])
        respuesta = resultado['respuesta']
        log.info(f"[SATELLA] ({len(respuesta)} chars | voz={resultado.get('voz')}) {respuesta}")
        emit('satella_responde', {
            'texto': respuesta,
            'audio': resultado.get('audio_b64'),
            'tono': resultado.get('tono', 'normal'),
            'voz': resultado.get('voz', 'echidna'),
        })
        # Si el modo navegador quedó activo, arrancamos el streaming del panel en vivo.
        if navegador.motor.activo() and not _estado["nav_stream"]:
            socketio.start_background_task(_stream_navegador)
    except Exception as e:
        log.error(f"Error procesando mensaje: {e}")
        emit('satella_responde', {
            'texto': 'Hay un problema técnico. Mira la consola.',
            'audio': None,
        })
    finally:
        emit('satella_pensando', {'estado': False})


@socketio.on('toggle_voz')
def on_toggle_voz(data):
    _estado["voz_activa"] = data.get('activa', True)
    log.info(f"Voz {'activada' if _estado['voz_activa'] else 'desactivada'}")
    emit('voz_estado', {'activa': _estado["voz_activa"]})


@socketio.on('cerrar_sesion')
def on_cerrar_sesion():
    resumen = cerrar_sesion()
    emit('sesion_cerrada', {'resumen': resumen})


def _timer_iniciacion():
    SEGUNDOS_LIMITE = MINUTOS_SILENCIO_INICIACION * 60
    while True:
        time.sleep(30)
        if not _estado["cliente_conectado"]:
            continue
        if not memoria.sesion_activa():
            continue
        silencio = time.time() - _estado["ultimo_mensaje_ts"]
        if silencio >= SEGUNDOS_LIMITE:
            try:
                log.info(f"Timer: {silencio:.0f}s de silencio — Satella inicia")
                resultado = iniciar_conversacion(voz_habilitada=_estado["voz_activa"])
                texto = resultado['respuesta']
                log.info(f"[INICIACION] ({len(texto)} chars) {texto}")
                socketio.emit('satella_responde', {
                    'texto': texto,
                    'audio': resultado.get('audio_b64'),
                    'voz': resultado.get('voz', 'echidna'),
                    'iniciacion': True,
                })
                _estado["ultimo_mensaje_ts"] = time.time()
            except Exception as e:
                log.error(f"Timer iniciación error: {e}")


def _timer_agenda():
    """Dispara las tareas agendadas a su hora. Compuerta: las sensibles no se auto-ejecutan."""
    from nucleo import agenda
    while True:
        time.sleep(30)
        if not _estado["cliente_conectado"]:
            continue
        try:
            vencidas = agenda.vencidas()
        except Exception as e:
            log.error(f"[AGENDA] error revisando: {e}")
            continue
        for tarea in vencidas:
            intencion = tarea.get("intencion", "")
            try:
                if agenda.es_intencion_sensible(intencion):
                    texto = (f"Tenías agendado: \u00ab{intencion}\u00bb. Es una acci\u00f3n delicada, "
                             f"as\u00ed que no la hice sola. \u00bfQuer\u00e9s que la haga ahora?")
                    log.info(f"[AGENDA] tarea sensible #{tarea['id']} \u2192 pido confirmaci\u00f3n")
                    socketio.emit('satella_responde', {'texto': texto, 'voz': 'echidna', 'iniciacion': True})
                else:
                    log.info(f"[AGENDA] disparo #{tarea['id']}: {intencion}")
                    resultado = procesar_mensaje(intencion, voz_habilitada=_estado["voz_activa"])
                    socketio.emit('satella_responde', {
                        'texto': resultado['respuesta'],
                        'audio': resultado.get('audio_b64'),
                        'voz': resultado.get('voz', 'echidna'),
                        'iniciacion': True,
                    })
                _estado["ultimo_mensaje_ts"] = time.time()
            except Exception as e:
                log.error(f"[AGENDA] error disparando #{tarea.get('id')}: {e}")


def iniciar():
    threading.Thread(target=_timer_iniciacion, daemon=True).start()
    threading.Thread(target=_timer_agenda, daemon=True).start()
    log.info(f"Satella corriendo en http://localhost:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)