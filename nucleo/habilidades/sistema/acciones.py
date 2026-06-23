"""
nucleo/habilidades/sistema/acciones.py — REGISTRO DE ACCIONES SEGURAS sobre el PC.

Principio (igual que el sandbox y el navegador): NADA de os.system(texto_libre).
Satella solo puede ejecutar acciones de ESTE registro, cada una una función concreta.
Cada acción tiene un NIVEL DE RIESGO:
  verde   → directa (no rompe nada): abrir, buscar, volumen, info.
  amarillo→ pide confirmación (reversible pero molesto): cerrar app, bloquear, crear carpeta.
  rojo    → confirmación + validación estricta (peligroso): apagar, mover, borrar.

Borrar = mandar a la PAPELERA (reversible), nunca destruir permanente.
Rutas críticas del sistema están bloqueadas para mover/borrar.
"""
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("satella.habilidad.sistema")

_ES_WINDOWS = platform.system() == "Windows"

VERDE, AMARILLO, ROJO = "verde", "amarillo", "rojo"


# ─────────────────────────────────────────────────────────────────────────────
# VALIDACIÓN DE RUTAS — el corazón de la seguridad para mover/borrar
# ─────────────────────────────────────────────────────────────────────────────

# Carpetas cuyo ÁRBOL ENTERO se protege (la carpeta y todo lo de adentro).
def _criticas_arbol() -> list:
    if _ES_WINDOWS:
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        c = [sysroot, pf, pf86, r"C:\Windows", r"C:\Windows\System32"]
    else:
        c = ["/bin", "/boot", "/etc", "/lib", "/lib64", "/sbin", "/usr",
             "/var", "/sys", "/proc", "/dev", "/root"]
    return [os.path.normpath(p).lower() for p in c]


# Rutas que solo se protegen como punto EXACTO o como ancestro (no su contenido):
# raíces de disco — no podés borrar "C:\" pero sí cosas dentro de C:\Users\...
def _criticas_exactas() -> list:
    if _ES_WINDOWS:
        return [os.path.normpath(f"{chr(d)}:\\").lower() for d in range(ord("A"), ord("Z") + 1)]
    return ["/"]


def validar_ruta_modificable(ruta: str) -> tuple[bool, str]:
    """¿Es seguro mover/borrar esta ruta? Devuelve (ok, razón_si_no)."""
    if not ruta or not str(ruta).strip():
        return False, "ruta vacía"
    try:
        p = Path(ruta).expanduser().resolve()
    except Exception as e:
        return False, f"ruta inválida: {e}"

    if not p.exists():
        return False, f"no existe: {p}"

    norm = os.path.normpath(str(p)).lower()
    arbol = _criticas_arbol()
    exactas = _criticas_exactas()

    # 1) ¿Es, o está DENTRO de, una carpeta crítica protegida por árbol? → bloquear.
    for c in arbol:
        if norm == c or norm.startswith(c + os.sep):
            return False, f"ruta dentro de carpeta protegida del sistema: {p}"

    # 2) ¿Es exactamente una raíz de disco / la raíz? → bloquear.
    if norm in exactas:
        return False, f"raíz del sistema, protegida: {p}"

    # 3) ¿Es ANCESTRO de una crítica (demasiado amplia, ej. contiene Windows)? → bloquear.
    for c in arbol + exactas:
        if c.startswith(norm + os.sep):
            return False, f"ruta demasiado amplia / protegida: {p}"

    # 4) Profundidad mínima: nada a un solo nivel de la raíz del disco.
    partes = [x for x in p.parts if x not in ("\\", "/")]
    if len(partes) < 2:
        return False, f"ruta demasiado cerca de la raíz, no permitida: {p}"

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# ACCIONES — VERDE (directas)
# ─────────────────────────────────────────────────────────────────────────────

def _resolver_carpeta_conocida(nombre: str):
    """Mapea nombres comunes ('descargas', 'escritorio', 'carpeta de documentos')
    a su ruta real. Devuelve un Path o None."""
    n = (nombre or "").strip().lower().strip("\"'")
    home = Path.home()
    mapa = {
        "descargas": home / "Downloads", "downloads": home / "Downloads",
        "escritorio": home / "Desktop", "desktop": home / "Desktop",
        "documentos": home / "Documents", "documents": home / "Documents", "mis documentos": home / "Documents",
        "imágenes": home / "Pictures", "imagenes": home / "Pictures", "pictures": home / "Pictures", "fotos": home / "Pictures",
        "música": home / "Music", "musica": home / "Music", "music": home / "Music",
        "vídeos": home / "Videos", "videos": home / "Videos",
        "home": home, "casa": home, "perfil": home, "carpeta personal": home,
    }
    if n in mapa:
        return mapa[n]
    # coincidencia por contención: "carpeta de descargas" → descargas
    for clave in sorted(mapa, key=len, reverse=True):
        if clave in n:
            return mapa[clave]
    return None


def abrir_app(nombre: str) -> dict:
    """Abre una aplicación por nombre/ejecutable (ej. 'notepad', 'code', 'spotify')."""
    try:
        if _ES_WINDOWS:
            os.startfile(nombre)  # noqa: usa la asociación del sistema
        else:
            subprocess.Popen([nombre])
        return {"ok": True, "detalle": f"abrí {nombre}"}
    except Exception as e:
        return {"ok": False, "detalle": f"no pude abrir {nombre}: {e}"}


def abrir_ruta(ruta: str) -> dict:
    """Abre un archivo o carpeta con su app por defecto. Resuelve nombres conocidos."""
    p = Path(ruta).expanduser()
    if not p.exists():
        conocida = _resolver_carpeta_conocida(ruta)
        if conocida and conocida.exists():
            p = conocida
    if not p.exists():
        return {"ok": False, "detalle": f"no encontré: {ruta}"}
    try:
        if _ES_WINDOWS:
            os.startfile(str(p))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"ok": True, "detalle": f"abrí {p}"}
    except Exception as e:
        return {"ok": False, "detalle": f"no pude abrir {ruta}: {e}"}


def buscar_archivos(patron: str, raiz: str = None, max_resultados: int = 30) -> dict:
    """Busca archivos cuyo nombre contenga 'patron' bajo 'raiz' (default: home).
    'raiz' acepta nombres conocidos ('descargas', 'documentos', ...)."""
    if raiz:
        conocida = _resolver_carpeta_conocida(raiz)
        base = conocida if (conocida and conocida.exists()) else Path(raiz).expanduser()
    else:
        base = Path.home()
    if not base.exists():
        return {"ok": False, "detalle": f"no existe la carpeta: {base}"}
    encontrados = []
    pl = patron.lower()
    try:
        for root, dirs, files in os.walk(base):
            # no entrar a carpetas de sistema/ocultas pesadas
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in
                       ("node_modules", "$recycle.bin", "windows", "appdata")]
            for f in files:
                if pl in f.lower():
                    encontrados.append(str(Path(root) / f))
                    if len(encontrados) >= max_resultados:
                        return {"ok": True, "detalle": f"{len(encontrados)}+ resultados",
                                "resultados": encontrados}
        return {"ok": True, "detalle": f"{len(encontrados)} resultado(s)", "resultados": encontrados}
    except Exception as e:
        return {"ok": False, "detalle": f"error buscando: {e}"}


def _tecla_virtual(code: int, veces: int = 1):
    """Manda una tecla virtual de Windows (volumen/multimedia) sin dependencias."""
    import ctypes
    for _ in range(veces):
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)


# Códigos de teclas virtuales de Windows
_VK = {"vol_up": 0xAF, "vol_down": 0xAE, "vol_mute": 0xAD,
       "play_pause": 0xB3, "siguiente": 0xB0, "anterior": 0xB1, "stop": 0xB2}


def volumen(accion: str, pasos: int = 5) -> dict:
    """accion: subir | bajar | silenciar."""
    if not _ES_WINDOWS:
        return {"ok": False, "detalle": "control de volumen por tecla solo en Windows en esta versión"}
    try:
        if accion == "subir":
            _tecla_virtual(_VK["vol_up"], pasos)
        elif accion == "bajar":
            _tecla_virtual(_VK["vol_down"], pasos)
        elif accion == "silenciar":
            _tecla_virtual(_VK["vol_mute"])
        else:
            return {"ok": False, "detalle": f"acción de volumen desconocida: {accion}"}
        return {"ok": True, "detalle": f"volumen: {accion}"}
    except Exception as e:
        return {"ok": False, "detalle": f"error volumen: {e}"}


def multimedia(accion: str) -> dict:
    """accion: play_pausa | siguiente | anterior | stop."""
    if not _ES_WINDOWS:
        return {"ok": False, "detalle": "control multimedia por tecla solo en Windows en esta versión"}
    code = _VK.get(accion)
    if code is None:
        return {"ok": False, "detalle": f"acción multimedia desconocida: {accion}"}
    try:
        _tecla_virtual(code)
        return {"ok": True, "detalle": f"multimedia: {accion}"}
    except Exception as e:
        return {"ok": False, "detalle": f"error multimedia: {e}"}


def info_sistema() -> dict:
    """Info útil del sistema: hora, batería, RAM, disco."""
    import datetime
    datos = {"hora": datetime.datetime.now().strftime("%H:%M:%S"),
             "fecha": datetime.datetime.now().strftime("%d/%m/%Y"),
             "sistema": platform.system(), "equipo": platform.node()}
    try:
        import psutil
        datos["ram_%"] = psutil.virtual_memory().percent
        datos["cpu_%"] = psutil.cpu_percent(interval=0.3)
        bat = psutil.sensors_battery()
        if bat:
            datos["bateria_%"] = bat.percent
            datos["enchufado"] = bat.power_plugged
        disco = psutil.disk_usage(str(Path.home()))
        datos["disco_libre_gb"] = round(disco.free / (1024**3), 1)
    except Exception:
        datos["nota"] = "instalá psutil para batería/RAM/disco (pip install psutil)"
    return {"ok": True, "detalle": "info del sistema", "datos": datos}


def apps_abiertas(max_n: int = 25) -> dict:
    """Lista procesos/apps con ventana (aproximado por nombre de proceso)."""
    try:
        import psutil
        nombres = sorted({p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]})
        return {"ok": True, "detalle": f"{len(nombres)} procesos", "resultados": nombres[:max_n]}
    except Exception:
        return {"ok": False, "detalle": "instalá psutil para listar apps (pip install psutil)"}


# ─────────────────────────────────────────────────────────────────────────────
# ACCIONES — AMARILLO (piden confirmación)
# ─────────────────────────────────────────────────────────────────────────────

def cerrar_app(nombre: str) -> dict:
    """Cierra procesos cuyo nombre coincida. Confirmación requerida (lo gestiona la skill)."""
    try:
        import psutil
        cerrados = 0
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if nombre.lower() in n:
                try:
                    p.terminate()
                    cerrados += 1
                except Exception:
                    pass
        return {"ok": cerrados > 0, "detalle": f"cerré {cerrados} proceso(s) de '{nombre}'"}
    except Exception as e:
        return {"ok": False, "detalle": f"error cerrando: {e}"}


def bloquear() -> dict:
    """Bloquea la pantalla."""
    try:
        if _ES_WINDOWS:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        else:
            return {"ok": False, "detalle": "bloqueo solo implementado en Windows"}
        return {"ok": True, "detalle": "pantalla bloqueada"}
    except Exception as e:
        return {"ok": False, "detalle": f"error bloqueando: {e}"}


def crear_carpeta(ruta: str) -> dict:
    """Crea una carpeta (y sus padres)."""
    try:
        Path(ruta).expanduser().mkdir(parents=True, exist_ok=True)
        return {"ok": True, "detalle": f"creé la carpeta {ruta}"}
    except Exception as e:
        return {"ok": False, "detalle": f"no pude crear {ruta}: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# ACCIONES — ROJO (confirmación + validación estricta)
# ─────────────────────────────────────────────────────────────────────────────

def apagar(reiniciar: bool = False, segundos: int = 15) -> dict:
    """Apaga o reinicia, con margen para cancelar (shutdown /a)."""
    if not _ES_WINDOWS:
        return {"ok": False, "detalle": "apagado solo implementado en Windows en esta versión"}
    try:
        flag = "/r" if reiniciar else "/s"
        subprocess.run(["shutdown", flag, "/t", str(segundos)], check=True)
        accion = "reiniciar" if reiniciar else "apagar"
        return {"ok": True, "detalle": f"voy a {accion} en {segundos}s. Para cancelar: 'shutdown /a'"}
    except Exception as e:
        return {"ok": False, "detalle": f"error: {e}"}


def mover(origen: str, destino: str) -> dict:
    """Mueve un archivo/carpeta, validando que el origen sea seguro."""
    ok, razon = validar_ruta_modificable(origen)
    if not ok:
        return {"ok": False, "detalle": f"no muevo: {razon}"}
    try:
        shutil.move(str(Path(origen).expanduser()), str(Path(destino).expanduser()))
        return {"ok": True, "detalle": f"moví {origen} → {destino}"}
    except Exception as e:
        return {"ok": False, "detalle": f"error moviendo: {e}"}


def borrar(ruta: str) -> dict:
    """Manda a la PAPELERA (reversible), nunca destruye permanente. Valida la ruta."""
    ok, razon = validar_ruta_modificable(ruta)
    if not ok:
        return {"ok": False, "detalle": f"no borro: {razon}"}
    try:
        from send2trash import send2trash
    except Exception:
        return {"ok": False, "detalle": "necesito 'send2trash' para borrar de forma reversible "
                                        "(pip install send2trash). No borro permanente por seguridad."}
    try:
        send2trash(str(Path(ruta).expanduser()))
        return {"ok": True, "detalle": f"mandé a la papelera: {ruta} (recuperable)"}
    except Exception as e:
        return {"ok": False, "detalle": f"error mandando a papelera: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO — el catálogo de lo que Satella PUEDE hacer, con su nivel de riesgo
# ─────────────────────────────────────────────────────────────────────────────

REGISTRO = {
    "abrir_app":      {"fn": abrir_app,      "riesgo": VERDE,    "args": ["nombre"]},
    "abrir_ruta":     {"fn": abrir_ruta,     "riesgo": VERDE,    "args": ["ruta"]},
    "buscar_archivos":{"fn": buscar_archivos,"riesgo": VERDE,    "args": ["patron", "raiz?"]},
    "volumen":        {"fn": volumen,        "riesgo": VERDE,    "args": ["accion", "pasos?"]},
    "multimedia":     {"fn": multimedia,     "riesgo": VERDE,    "args": ["accion"]},
    "info_sistema":   {"fn": info_sistema,   "riesgo": VERDE,    "args": []},
    "apps_abiertas":  {"fn": apps_abiertas,  "riesgo": VERDE,    "args": []},
    "cerrar_app":     {"fn": cerrar_app,     "riesgo": AMARILLO, "args": ["nombre"]},
    "bloquear":       {"fn": bloquear,       "riesgo": AMARILLO, "args": []},
    "crear_carpeta":  {"fn": crear_carpeta,  "riesgo": AMARILLO, "args": ["ruta"]},
    "apagar":         {"fn": apagar,         "riesgo": ROJO,     "args": ["reiniciar?", "segundos?"]},
    "mover":          {"fn": mover,          "riesgo": ROJO,     "args": ["origen", "destino"]},
    "borrar":         {"fn": borrar,         "riesgo": ROJO,     "args": ["ruta"]},
}


def riesgo_de(accion: str) -> str:
    return REGISTRO.get(accion, {}).get("riesgo", ROJO)  # desconocida → trátala como roja


def ejecutar(accion: str, params: dict) -> dict:
    """Ejecuta una acción del registro con sus parámetros. NUNCA ejecuta algo fuera del registro."""
    entrada = REGISTRO.get(accion)
    if not entrada:
        return {"ok": False, "detalle": f"acción no permitida o desconocida: '{accion}'"}
    try:
        return entrada["fn"](**(params or {}))
    except TypeError as e:
        return {"ok": False, "detalle": f"parámetros inválidos para {accion}: {e}"}
    except Exception as e:
        log.error(f"[SISTEMA] error ejecutando {accion}: {e}")
        return {"ok": False, "detalle": f"error ejecutando {accion}: {e}"}