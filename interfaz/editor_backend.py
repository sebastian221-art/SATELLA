"""
Backend del editor de código de Satella — Fase 2A + 2C.

Se registra sobre la app Flask y el socketio ya existentes, SIN tocar el chat.

Fase 2A — habilidad de código:
  - Ruta  /editor                     → sirve la página del editor.
  - 'editor_ejecutar' {codigo}        → corre el código en el sandbox.
  - 'editor_analizar' {codigo}        → análisis + razonamiento de senior.
  - 'editor_generar'  {prompt}        → genera código con el pipeline.

Fase 2C — proyectos y archivos (acceso al disco, acotado a PROYECTOS_ROOT):
  - 'editor_listar_proyectos'         → carpetas dentro de PROYECTOS_ROOT.
  - 'editor_abrir_proyecto' {proyecto}→ árbol de archivos del proyecto.
  - 'editor_abrir_archivo' {ruta}     → contenido de un archivo de texto.
  - 'editor_guardar_archivo' {ruta,contenido} → escribe el archivo.

Seguridad: toda ruta se resuelve y se valida que quede DENTRO de PROYECTOS_ROOT
(no se permite salir con ../). Límite de tamaño y solo archivos de texto.
"""
import logging
import os
import threading

from flask import render_template_string

from config import SATELLA_ROOT
from nucleo.habilidades.python import ejecutor, analizador, explicador, generador

log = logging.getLogger("satella.editor")

EDITOR_PATH = os.path.join(SATELLA_ROOT, "interfaz", "frontend", "editor.html")

# Carpeta que contiene los proyectos. Por defecto, la carpeta padre de SATELLA
# (ej: C:\Users\Sebas\sebastian_proyects). Cambiá esto si tus proyectos viven
# en otro lado.
PROYECTOS_ROOT = os.path.dirname(SATELLA_ROOT)

_IGNORAR = {".git", "__pycache__", "node_modules", "venv", ".venv", ".idea",
            ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache", "env"}
_EXT_TEXTO = {".py", ".txt", ".md", ".json", ".js", ".ts", ".jsx", ".tsx",
              ".html", ".css", ".csv", ".yml", ".yaml", ".toml", ".cfg",
              ".ini", ".env", ".sh", ".bat", ".sql", ".xml", ".log"}
_MAX_BYTES = 1_000_000  # 1 MB


def _ruta_segura(rel: str):
    """Resuelve rel contra PROYECTOS_ROOT y verifica que no se salga."""
    base = os.path.abspath(PROYECTOS_ROOT)
    full = os.path.abspath(os.path.join(base, rel or ""))
    if full == base or full.startswith(base + os.sep):
        return full
    return None


def _arbol(ruta_abs: str, rel_base: str, prof: int = 0) -> list:
    """Construye el árbol de archivos (carpetas primero, luego archivos)."""
    nodos = []
    if prof > 8:
        return nodos
    try:
        entradas = sorted(os.scandir(ruta_abs),
                          key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError:
        return nodos
    for e in entradas:
        if e.name in _IGNORAR:
            continue
        if e.name.startswith(".") and e.name != ".env":
            continue
        rel = (rel_base + "/" + e.name).replace("\\", "/")
        if e.is_dir():
            nodos.append({"nombre": e.name, "tipo": "carpeta",
                          "hijos": _arbol(e.path, rel, prof + 1)})
        else:
            ext = os.path.splitext(e.name)[1].lower()
            nodos.append({"nombre": e.name, "tipo": "archivo", "ruta": rel,
                          "abrible": ext in _EXT_TEXTO})
    return nodos


def registrar_editor(app, socketio):
    """Conecta la ruta y los eventos del editor a la app/socketio existentes."""

    @app.route("/editor")
    def editor():
        with open(EDITOR_PATH, encoding="utf-8") as f:
            return render_template_string(f.read())

    # ── Ejecutar ───────────────────────────────────────────────────────────
    @socketio.on("editor_ejecutar")
    def on_editor_ejecutar(data):
        codigo = (data or {}).get("codigo", "")

        def tarea():
            try:
                r = ejecutor.ejecutar(codigo)
                socketio.emit("editor_resultado", {
                    "tipo": "ejecucion", "ok": r.get("ok", False),
                    "stdout": r.get("stdout", ""), "stderr": r.get("stderr", ""),
                    "tiempo_ms": r.get("tiempo_ms", 0), "bloqueado": r.get("bloqueado", False),
                })
            except Exception as e:
                log.error(f"editor_ejecutar: {e}")
                socketio.emit("editor_resultado", {
                    "tipo": "ejecucion", "ok": False, "stdout": "",
                    "stderr": f"Error interno: {e}", "tiempo_ms": 0, "bloqueado": False,
                })

        threading.Thread(target=tarea, daemon=True).start()

    # ── Analizar ───────────────────────────────────────────────────────────
    @socketio.on("editor_analizar")
    def on_editor_analizar(data):
        codigo = (data or {}).get("codigo", "")

        def tarea():
            try:
                a = analizador.analizar(codigo)
                razon = ""
                try:
                    razon = explicador.explicar(codigo, a)
                except Exception as e:
                    log.warning(f"explicador falló: {e}")
                socketio.emit("editor_resultado", {
                    "tipo": "analisis", "ok": a.get("sintaxis_ok", True),
                    "resumen": a.get("resumen", ""), "razonamiento": razon,
                    "problemas": a.get("problemas", []), "metricas": a.get("metricas", {}),
                })
            except Exception as e:
                log.error(f"editor_analizar: {e}")
                socketio.emit("editor_resultado", {
                    "tipo": "analisis", "ok": False,
                    "resumen": f"Error interno: {e}", "razonamiento": "",
                    "problemas": [], "metricas": {},
                })

        threading.Thread(target=tarea, daemon=True).start()

    # ── Generar ────────────────────────────────────────────────────────────
    @socketio.on("editor_generar")
    def on_editor_generar(data):
        prompt = (data or {}).get("prompt", "").strip()
        if not prompt:
            return
        socketio.emit("editor_estado", {"estado": "generando"})

        def tarea():
            try:
                r = generador.generar(prompt)
                if r.get("ok"):
                    socketio.emit("editor_resultado", {
                        "tipo": "generacion", "ok": True, "codigo": r.get("codigo", ""),
                        "tests_pasaron": r.get("tests_pasaron"), "ciclos": r.get("ciclos", 0),
                    })
                else:
                    socketio.emit("editor_resultado", {
                        "tipo": "generacion", "ok": False, "codigo": "",
                        "error": "No se pudo generar código (¿modelo de código disponible?).",
                    })
            except Exception as e:
                log.error(f"editor_generar: {e}")
                socketio.emit("editor_resultado", {
                    "tipo": "generacion", "ok": False, "codigo": "", "error": str(e),
                })
            finally:
                socketio.emit("editor_estado", {"estado": "listo"})

        threading.Thread(target=tarea, daemon=True).start()

    # ── Proyectos y archivos (Fase 2C) ──────────────────────────────────────
    @socketio.on("editor_listar_proyectos")
    def on_listar_proyectos(data=None):
        try:
            proys = sorted(
                d.name for d in os.scandir(PROYECTOS_ROOT)
                if d.is_dir() and d.name not in _IGNORAR and not d.name.startswith(".")
            )
            socketio.emit("editor_proyectos", {"ok": True, "proyectos": proys,
                                               "root": PROYECTOS_ROOT})
        except Exception as e:
            log.error(f"listar_proyectos: {e}")
            socketio.emit("editor_proyectos", {"ok": False, "error": str(e), "proyectos": []})

    @socketio.on("editor_abrir_proyecto")
    def on_abrir_proyecto(data):
        nombre = (data or {}).get("proyecto", "")
        full = _ruta_segura(nombre)
        if not full or not os.path.isdir(full):
            socketio.emit("editor_arbol", {"ok": False, "error": "Proyecto no encontrado."})
            return
        socketio.emit("editor_arbol", {"ok": True, "proyecto": nombre,
                                       "arbol": _arbol(full, nombre)})

    @socketio.on("editor_abrir_archivo")
    def on_abrir_archivo(data):
        rel = (data or {}).get("ruta", "")
        full = _ruta_segura(rel)
        if not full or not os.path.isfile(full):
            socketio.emit("editor_archivo", {"ok": False, "error": "Archivo no encontrado."})
            return
        try:
            if os.path.getsize(full) > _MAX_BYTES:
                socketio.emit("editor_archivo", {"ok": False, "error": "Archivo muy grande (>1MB)."})
                return
            with open(full, encoding="utf-8") as f:
                contenido = f.read()
            socketio.emit("editor_archivo", {"ok": True, "ruta": rel, "contenido": contenido})
        except UnicodeDecodeError:
            socketio.emit("editor_archivo", {"ok": False, "error": "No es un archivo de texto."})
        except Exception as e:
            log.error(f"abrir_archivo: {e}")
            socketio.emit("editor_archivo", {"ok": False, "error": str(e)})

    @socketio.on("editor_guardar_archivo")
    def on_guardar_archivo(data):
        rel = (data or {}).get("ruta", "")
        contenido = (data or {}).get("contenido", "")
        full = _ruta_segura(rel)
        if not full:
            socketio.emit("editor_guardado", {"ok": False, "error": "Ruta inválida."})
            return
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(contenido)
            socketio.emit("editor_guardado", {"ok": True, "ruta": rel})
            log.info(f"[EDITOR] guardado {rel}")
        except Exception as e:
            log.error(f"guardar_archivo: {e}")
            socketio.emit("editor_guardado", {"ok": False, "error": str(e)})

    log.info(f"Editor de código registrado en /editor (proyectos: {PROYECTOS_ROOT})")