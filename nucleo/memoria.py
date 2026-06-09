"""
Memoria de Satella — modelo de Sebastian + episodios + sesión actual.
"""
import json
import os
import logging
from datetime import datetime
from config import MODELO_SEBASTIAN, EPISODIOS_FILE, MAX_HISTORIAL_TURNOS, MAX_EPISODIOS_CONTEXTO

log = logging.getLogger("satella.memoria")

_MODELO_DEFAULT = {
    "nombre": "Juan Sebastian Mora Patiño",
    "apodo": "Sebas",
    "edad": 19,
    "ciudad": "Bucaramanga",
    "trabajo": "Jelcon",
    "proyecto_principal": "BELLADONNA_V2",
    "github": "sebastian221-art",
    "proyectos": {
        "BELLADONNA_V2": {"estado": "activo", "tecnologias": ["Python", "Flask", "Groq"]},
        "Satella": {"estado": "en construcción", "tecnologias": ["Python", "Flask", "Groq", "edge-tts"]}
    },
    "preferencias": {
        "filosofia": ["calidad sobre cantidad", "principios sobre ejemplos", "profundidad sobre amplitud"],
        "comunicacion": ["directo", "honesto", "sin rodeos", "diagnóstico antes que código"],
        "tecnicas": ["Python", "arquitectura limpia", "herramientas inteligentes"]
    },
    "patrones": {
        "horario_activo": "noche",
        "estilo_trabajo": "profundo",
        "ultima_actividad": None
    },
    "ultima_actualizacion": None
}

_sesion: list[dict] = []
_modelo: dict = {}
_episodios: list[dict] = []


def inicializar():
    global _modelo, _episodios
    _modelo = _cargar_json(MODELO_SEBASTIAN, _MODELO_DEFAULT)
    _episodios = _cargar_json(EPISODIOS_FILE, [])
    if not isinstance(_episodios, list):
        _episodios = []
    log.info(f"Memoria: modelo Sebastian cargado | {len(_episodios)} episodios previos")


def _cargar_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error cargando {path}: {e}")
    return default


def _guardar_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Error guardando {path}: {e}")


def registrar_turno(rol: str, contenido: str):
    """Agrega un turno al historial de sesión actual."""
    _sesion.append({"role": rol, "content": contenido, "ts": datetime.now().isoformat()})


def historial_groq() -> list[dict]:
    """Retorna los últimos N turnos en formato Groq (sin timestamp)."""
    ultimos = _sesion[-MAX_HISTORIAL_TURNOS:]
    return [{"role": t["role"], "content": t["content"]} for t in ultimos]


def historial_texto() -> str:
    """Retorna el historial como texto legible."""
    if not _sesion:
        return ""
    lineas = []
    for t in _sesion[-6:]:
        quien = "Sebas" if t["role"] == "user" else "Satella"
        lineas.append(f"{quien}: {t['content']}")
    return "\n".join(lineas)


def modelo_compacto() -> str:
    """Retorna el modelo de Sebastian en formato compacto para prompts."""
    m = _modelo
    proyectos = ", ".join(m.get("proyectos", {}).keys())
    filosofia = " | ".join(m.get("preferencias", {}).get("filosofia", []))
    return (
        f"Nombre: {m.get('nombre','Sebastian')} | "
        f"Ciudad: {m.get('ciudad','Bucaramanga')} | "
        f"Trabajo: {m.get('trabajo','Jelcon')} | "
        f"Proyectos: {proyectos} | "
        f"Filosofía: {filosofia} | "
        f"Activo: {m.get('patrones',{}).get('horario_activo','noche')}"
    )


def episodios_compactos() -> str:
    """Retorna los últimos episodios en formato compacto."""
    if not _episodios:
        return ""
    recientes = _episodios[-MAX_EPISODIOS_CONTEXTO:]
    lineas = []
    for ep in recientes:
        fecha = ep.get("fecha", "")[:10]
        tema = ep.get("tema_principal", "")
        pendientes = ep.get("pendientes", [])
        estado = ep.get("estado_sebastian", "")
        linea = f"[{fecha}] {tema}"
        if pendientes:
            linea += f" | Pendiente: {pendientes[0]}"
        if estado:
            linea += f" | Sebastian estaba: {estado}"
        lineas.append(linea)
    return "\n".join(lineas)


def ultimo_tema() -> str:
    """Retorna el tema de la última sesión."""
    if _episodios:
        return _episodios[-1].get("tema_principal", "")
    return ""


def actualizar_modelo_sebastian(dato: dict):
    """Actualiza el modelo de Sebastian con un dato nuevo de la sesión."""
    try:
        tipo = dato.get("tipo")
        valor = dato.get("valor")
        if not tipo or not valor:
            return

        if tipo == "proyecto":
            if "proyectos" not in _modelo:
                _modelo["proyectos"] = {}
            nombre_proy = valor.get("nombre", "")
            if nombre_proy:
                _modelo["proyectos"][nombre_proy] = valor

        elif tipo == "preferencia":
            cat = valor.get("categoria", "tecnicas")
            pref = valor.get("preferencia", "")
            if pref and "preferencias" in _modelo:
                if cat not in _modelo["preferencias"]:
                    _modelo["preferencias"][cat] = []
                if pref not in _modelo["preferencias"][cat]:
                    _modelo["preferencias"][cat].append(pref)

        elif tipo == "patron":
            key = valor.get("clave", "")
            val = valor.get("valor", "")
            if key and val:
                _modelo.setdefault("patrones", {})[key] = val

        _modelo["ultima_actualizacion"] = datetime.now().isoformat()
        _modelo["patrones"]["ultima_actividad"] = datetime.now().isoformat()
        _guardar_json(MODELO_SEBASTIAN, _modelo)

    except Exception as e:
        log.error(f"Error actualizando modelo: {e}")


def cerrar_sesion(resumen: dict):
    """Guarda el resumen de la sesión como episodio."""
    if not _sesion:
        return
    resumen["fecha"] = datetime.now().isoformat()
    resumen["turnos"] = len(_sesion)
    _episodios.append(resumen)
    _guardar_json(EPISODIOS_FILE, _episodios)
    _sesion.clear()
    log.info(f"Sesión cerrada y guardada | Total episodios: {len(_episodios)}")


def sesion_activa() -> bool:
    return len(_sesion) > 0