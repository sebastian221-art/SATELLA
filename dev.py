"""
dev.py — Satella con hot-reload automático.
Corre este en lugar de main.py durante desarrollo.
Detecta cambios en .py, .json y .html y reinicia solo.

Uso: python dev.py

Requiere: pip install watchdog
"""
import subprocess
import sys
import os
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [dev] %(message)s'
)
log = logging.getLogger("dev")

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    log.error("Watchdog no instalado. Corriendo: pip install watchdog")
    subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"])
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

RAIZ = os.path.dirname(os.path.abspath(__file__))
EXTENSIONES = {'.py', '.json', '.html'}
IGNORAR = {'__pycache__', '.git', 'venv', 'datos_entrenamiento.json',
           'episodios.json', 'correcciones.json', 'modelo_sebastian.json'}


class WatcherSatella(FileSystemEventHandler):
    def __init__(self):
        self.reiniciar = False
        self._ultimo_cambio = 0

    def on_modified(self, event):
        if event.is_directory:
            return

        ruta = event.src_path
        nombre = os.path.basename(ruta)

        # Ignorar archivos de datos que cambian constantemente
        if any(ignorado in ruta for ignorado in IGNORAR):
            return

        ext = os.path.splitext(nombre)[1].lower()
        if ext not in EXTENSIONES:
            return

        # Debounce — evitar múltiples reinicios por el mismo cambio
        ahora = time.time()
        if ahora - self._ultimo_cambio < 1.5:
            return
        self._ultimo_cambio = ahora

        log.info(f"📝 {nombre} modificado — reiniciando Satella...")
        self.reiniciar = True


def main():
    log.info("═══════════════════════════════════════════")
    log.info("  SATELLA — modo desarrollo con hot-reload")
    log.info("  Modificá cualquier archivo .py o .json")
    log.info("  y Satella se reinicia automáticamente.")
    log.info("  Ctrl+C para salir.")
    log.info("═══════════════════════════════════════════")

    watcher = WatcherSatella()
    observer = Observer()
    observer.schedule(watcher, path=RAIZ, recursive=True)
    observer.start()

    proceso = None

    try:
        while True:
            if proceso is None or watcher.reiniciar:
                if proceso is not None:
                    log.info("Cerrando proceso anterior...")
                    proceso.terminate()
                    try:
                        proceso.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proceso.kill()

                watcher.reiniciar = False
                log.info("Iniciando Satella...")
                proceso = subprocess.Popen(
                    [sys.executable, "main.py"],
                    cwd=RAIZ
                )

            time.sleep(0.5)

            # Si el proceso murió solo, reiniciar
            if proceso.poll() is not None:
                log.warning("Satella se cayó — reiniciando en 2 segundos...")
                time.sleep(2)
                proceso = None

    except KeyboardInterrupt:
        log.info("Cerrando Satella...")
        if proceso:
            proceso.terminate()
            proceso.wait()
        observer.stop()

    observer.join()
    log.info("Hasta luego.")


if __name__ == "__main__":
    main()