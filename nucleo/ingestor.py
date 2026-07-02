"""
nucleo/ingestor.py — INGESTOR DE MEMORIA.
─────────────────────────────────────────────────────────────────────────────
Lee los archivos que dejás en datos/aprender/ (.md/.txt/.json) y teje tu trabajo
REAL en la memoria de Satella: Coral (grafo de conceptos) + HDC (canonicalización).

Por qué importa: Coral arranca VACÍO. Vacío = Satella no sabe cómo trabajás, qué
proyectos tenés, ni cómo se conectan las cosas. Y sin eso, ningún trabajador de la
futura empresa puede pararse sobre nada — un agente que vigila tu proyecto necesita
saber qué ES tu proyecto, y eso vive en Coral. El ingestor es lo que llena ese vacío.

Cómo se usa: tirás archivos en datos/aprender/ y le decís a Satella "aprendé de
mis archivos". Lee cada uno, extrae conceptos+relaciones con Groq y los teje en
el grafo, canonicalizando por HDC (browser==navegador).

Garantías:
  - IDEMPOTENTE: lleva un manifiesto con el hash de cada archivo. Re-correr NO
    duplica — solo procesa lo nuevo o lo que cambió.
  - NUNCA ROMPE: un archivo ilegible se salta y sigue con el resto.
  - HONESTO: reporta cuántos archivos leyó, cuántos saltó y cuánto sumó al grafo.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime

log = logging.getLogger("satella.ingestor")

_dir = ""
_manifiesto_ruta = ""
_EXTS = (".md", ".markdown", ".txt", ".json", ".text", ".log")

# Tope de fragmentos por archivo: protege de que un export gigante (ej. el
# conversations.json de 35MB) dispare cientos de llamadas a Groq de una. Si un
# archivo lo supera, se leen los primeros N y se avisa honestamente.
_MAX_TROZOS = 60

# Extracción tuneada para DOCUMENTOS (no conversación): notas, código, exports.
_PROMPT_DOC = """De este material de Sebas (notas, código, documentación, o export de chat), extraé los CONCEPTOS clave (proyectos, tecnologías, problemas, decisiones, personas, ideas) y cómo se RELACIONAN entre sí.

Material:
{texto}

Respondé SOLO JSON, sin texto afuera:
{{"conceptos": [{{"nombre": "...", "tipo": "proyecto|tecnologia|problema|decision|persona|concepto"}}],
 "relaciones": [{{"a": "...", "b": "...", "rel": "<verbo corto: usa, tiene, resuelve, se relaciona con, llevó a, depende de>"}}]}}

Máximo 12 conceptos y 12 relaciones de ESTE fragmento, los más importantes. Nombres concretos y consistentes (ej. siempre 'Satella', no 'el sistema'). Si el fragmento no tiene nada relevante, devolvé listas vacías."""


# ── Inicialización ───────────────────────────────────────────────────────────
def inicializar(dir_aprender: str = None):
    global _dir, _manifiesto_ruta
    if dir_aprender:
        _dir = dir_aprender
    else:
        try:
            from config import DATOS_DIR
            _dir = os.path.join(DATOS_DIR, "aprender")
        except Exception:
            _dir = os.path.join("datos", "aprender")
    try:
        os.makedirs(_dir, exist_ok=True)
    except Exception as e:
        log.error(f"Ingestor: no pude crear la carpeta {_dir}: {e}")
    _manifiesto_ruta = os.path.join(_dir, ".manifiesto.json")
    # Arranque BARATO: contamos por nombre (sin hashear). El hash —que puede ser
    # lento con archivos grandes— se hace recién cuando se aprende de verdad, no
    # en cada inicio.
    try:
        manif = _cargar_manifiesto()
        archivos = _archivos()
        nuevos = [a for a in archivos if os.path.basename(a) not in manif]
        log.info(f"Ingestor: carpeta {_dir} | {len(archivos)} archivo(s), "
                 f"{len(nuevos)} nuevo(s)")
    except Exception:
        log.info(f"Ingestor: carpeta {_dir}")


def carpeta() -> str:
    if not _dir:
        inicializar()
    return _dir


# ── Manifiesto (para no re-procesar lo ya leído) ─────────────────────────────
def _cargar_manifiesto() -> dict:
    if not _manifiesto_ruta or not os.path.exists(_manifiesto_ruta):
        return {}
    try:
        with open(_manifiesto_ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_manifiesto(m: dict):
    try:
        with open(_manifiesto_ruta, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Ingestor: no pude guardar el manifiesto: {e}")


def _hash_archivo(ruta: str) -> str:
    try:
        h = hashlib.sha1()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return h.hexdigest()
    except Exception:
        return ""


def _archivos() -> list:
    if not _dir or not os.path.isdir(_dir):
        return []
    out = []
    for nombre in sorted(os.listdir(_dir)):
        if nombre.startswith("."):
            continue
        ruta = os.path.join(_dir, nombre)
        if os.path.isfile(ruta) and os.path.splitext(nombre)[1].lower() in _EXTS:
            out.append(ruta)
    return out


def _pendientes() -> list:
    """Archivos que faltan procesar: nuevos, cambiados, o que quedaron A MEDIAS
    (un archivo grande del que solo se leyó una tanda de fragmentos)."""
    manif = _cargar_manifiesto()
    pend = []
    for ruta in _archivos():
        h = _hash_archivo(ruta)
        prev = manif.get(os.path.basename(ruta), {})
        if not h or prev.get("hash") != h:
            pend.append(ruta)               # nuevo o cambió
            continue
        if "trozos_total" not in prev:
            pend.append(ruta)               # formato viejo → re-evaluar (puede estar a medias)
            continue
        total = prev.get("trozos_total", 0)
        hechos = prev.get("trozos_hechos", 0)
        if total and hechos < total:
            pend.append(ruta)               # quedó a medias → seguir
    return pend


# ── Lectura + troceo ─────────────────────────────────────────────────────────
# Claves que son RUIDO (estructura, no contenido) y se descartan al leer JSON.
_CLAVES_RUIDO = {"uuid", "id", "created_at", "updated_at", "timestamp", "type",
                 "model", "role_id", "conversation_id", "parent_uuid", "index",
                 "sender_id", "attachments", "files", "settings", "account"}
# Claves que SÍ son contenido legible.
_CLAVES_TEXTO = {"text", "content", "summary", "name", "description", "title",
                 "sender", "prompt", "message", "body", "memory", "note", "human",
                 "assistant", "value"}


def _es_ruido(s: str) -> bool:
    """¿Este string es estructura (uuid/timestamp/url) y no contenido humano?"""
    if re.fullmatch(r"[0-9a-fA-F\-]{16,}", s):          # uuid / hash
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ].*", s):     # timestamp ISO
        return True
    if s.startswith(("http://", "https://", "data:", "/")):
        return True
    return False


def _texto_de_json(data) -> str:
    """Saca el TEXTO legible de un JSON (memorias, conversaciones, proyectos de
    Claude), tirando la estructura: uuids, timestamps, ids. Recorre todo el árbol y
    se queda con los campos de contenido y con los strings largos naturales.
    Así Groq recibe prosa limpia, no fragmentos rotos de JSON (que era el bug)."""
    fragmentos = []

    def _walk(obj, clave_padre=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, str(k).lower())
        elif isinstance(obj, list):
            for it in obj:
                _walk(it, clave_padre)
        elif isinstance(obj, str):
            s = obj.strip()
            if not s or clave_padre in _CLAVES_RUIDO or _es_ruido(s):
                return
            # Nos quedamos con campos de contenido, o con strings largos naturales.
            if clave_padre in _CLAVES_TEXTO or len(s) > 40:
                fragmentos.append(s)

    _walk(data)
    return "\n".join(fragmentos)


def _leer(ruta: str) -> str:
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        log.error(f"Ingestor: no pude leer {ruta}: {e}")
        return ""
    # Si es JSON (export de Claude, etc.), sacamos el texto legible de adentro.
    # Si el JSON no parsea, caemos al texto crudo sin romper.
    if ruta.lower().endswith(".json"):
        try:
            datos = json.loads(raw)
            texto = _texto_de_json(datos)
            if texto.strip():
                return texto
        except Exception:
            pass
    return raw


def _chunks(texto: str, tam: int = 4200) -> list:
    """Trocea texto largo en pedazos manejables para Groq, cortando en saltos de
    línea cuando se puede para no partir a la mitad de una idea."""
    texto = (texto or "").strip()
    if not texto:
        return []
    if len(texto) <= tam:
        return [texto]
    trozos, i = [], 0
    while i < len(texto):
        fin = min(i + tam, len(texto))
        if fin < len(texto):
            corte = texto.rfind("\n", i, fin)
            if corte > i + tam // 2:
                fin = corte
        trozos.append(texto[i:fin].strip())
        i = fin
    return [t for t in trozos if t]


# ── Extracción (reusa el motor ROBUSTO de Coral, con prompt de documento) ────
def _extraer(texto: str) -> dict:
    vacio = {"conceptos": [], "relaciones": []}
    if not texto or not texto.strip():
        return vacio
    try:
        from nucleo import coral
    except Exception:
        return vacio
    return coral.extraer_generico(_PROMPT_DOC.format(texto=texto[:4500]))


# ── Orquestación principal ───────────────────────────────────────────────────
def ingerir_carpeta(forzar: bool = False, avisar=None) -> dict:
    """
    Lee y aprende de los archivos de datos/aprender/.
      forzar=True  → re-procesa TODOS (ignora el manifiesto).
      avisar       → callback opcional (texto) para progreso en el chat.
    Devuelve stats: {archivos, saltados, conceptos, relaciones, detalle, sin_modelo}.
    """
    if not _dir:
        inicializar()

    def _av(t):
        if avisar:
            try:
                avisar(t)
            except Exception:
                pass

    todos = _archivos()
    if not todos:
        return {"archivos": 0, "saltados": 0, "conceptos": 0, "relaciones": 0,
                "detalle": [], "sin_modelo": False, "vacia": True}

    # ¿Hay modelo para extraer?
    try:
        from nucleo.habilidades.python import _llm
        hay_modelo = _llm.disponible()
    except Exception:
        hay_modelo = False
    if not hay_modelo:
        return {"archivos": 0, "saltados": len(todos), "conceptos": 0,
                "relaciones": 0, "detalle": [], "sin_modelo": True, "vacia": False}

    manif = _cargar_manifiesto()
    objetivo = todos if forzar else _pendientes()
    saltados = len(todos) - len(objetivo)

    total_c, total_r, detalle = 0, 0, []
    from nucleo import coral

    for idx, ruta in enumerate(objetivo, 1):
        nombre = os.path.basename(ruta)
        h_actual = _hash_archivo(ruta)
        _av(f"Leyendo {nombre} ({idx}/{len(objetivo)})…")
        texto = _leer(ruta)
        if not texto.strip():
            detalle.append({"archivo": nombre, "conceptos": 0, "relaciones": 0})
            manif[nombre] = {"hash": h_actual, "ts": datetime.now().isoformat(),
                             "conceptos": 0, "relaciones": 0,
                             "trozos_hechos": 0, "trozos_total": 0}
            continue

        trozos = _chunks(texto)
        total_trozos = len(trozos)

        # ¿Dónde arrancamos? Si el archivo ya venía a medias (mismo hash) y NO es
        # forzado, seguimos desde donde quedó. Si es nuevo/forzado, desde 0.
        prev = manif.get(nombre, {})
        inicio = 0
        c_arch = r_arch = 0
        if not forzar and prev.get("hash") == h_actual:
            if "trozos_total" in prev:
                inicio = prev.get("trozos_hechos", 0)          # formato nuevo: seguir donde quedó
            elif total_trozos > _MAX_TROZOS:
                inicio = _MAX_TROZOS                            # formato viejo y grande: el tope anterior era _MAX_TROZOS
            else:
                inicio = total_trozos                          # formato viejo y chico: ya estaba completo
            c_arch = prev.get("conceptos", 0)
            r_arch = prev.get("relaciones", 0)

        # Esta TANDA: desde 'inicio' hasta 'inicio + _MAX_TROZOS'.
        fin = min(inicio + _MAX_TROZOS, total_trozos)
        nuevos_c = nuevos_r = 0
        for ci in range(inicio, fin):
            _av(f"Leyendo {nombre} — fragmento {ci + 1}/{total_trozos}…")
            ext = _extraer(trozos[ci])
            nc = len(ext.get("conceptos", []))
            nr = len(ext.get("relaciones", []))
            if nc or nr:
                # Canonicaliza por HDC al ingerir (browser==navegador).
                coral.ingerir(ext, guardar=False, canonicalizar=True)
                nuevos_c += nc
                nuevos_r += nr

        c_arch += nuevos_c
        r_arch += nuevos_r
        total_c += nuevos_c
        total_r += nuevos_r
        incompleto = fin < total_trozos
        detalle.append({"archivo": nombre, "conceptos": nuevos_c, "relaciones": nuevos_r,
                        "incompleto": incompleto, "hechos": fin, "total": total_trozos})
        manif[nombre] = {"hash": h_actual, "ts": datetime.now().isoformat(),
                         "conceptos": c_arch, "relaciones": r_arch,
                         "trozos_hechos": fin, "trozos_total": total_trozos}

    # Guardar el grafo UNA vez al final + el manifiesto.
    try:
        coral._guardar()
    except Exception as e:
        log.error(f"Ingestor: no pude guardar el grafo: {e}")
    _guardar_manifiesto(manif)

    log.info(f"Ingestor: {len(objetivo)} archivo(s) | +{total_c} conceptos, "
             f"+{total_r} relaciones | {saltados} ya estaban")
    return {"archivos": len(objetivo), "saltados": saltados,
            "conceptos": total_c, "relaciones": total_r,
            "detalle": detalle, "sin_modelo": False, "vacia": False}


def estado() -> dict:
    """Resumen rápido sin procesar nada (para el chat: '¿qué tenés para aprender?')."""
    if not _dir:
        inicializar()
    todos = _archivos()
    return {"carpeta": _dir, "total": len(todos), "pendientes": len(_pendientes())}