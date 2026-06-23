"""
nucleo/coral.py — CORAL: grafo de memoria conceptual de Satella.

La memoria de episodios recuerda por RECENCIA (los últimos N). Coral recuerda por
CONEXIÓN: guarda conceptos (nodos) y cómo se relacionan (aristas), y al recordar
trae el SUBGRAFO conectado a lo que estás hablando, no una lista cronológica.

Así Satella deja de ver islas sueltas y empieza a ver el tejido: que Bell se
relaciona con el ERP, que el navegador usa Playwright, que tal problema llevó a tal
solución. Es la base de la continuidad — y de los datos para el modelo de identidad.

Todo en CPU, sin dependencias: el grafo es un JSON. (HDC se enchufa después para el
matcheo difuso de conceptos.)
"""
import json
import logging
import os
import re
from datetime import datetime

log = logging.getLogger("satella.coral")

_nodos: dict = {}     # clave -> {"nombre":str, "tipo":str, "peso":int, "visto":iso}
_aristas: dict = {}   # clave -> {vecino_clave: {"rel":str, "peso":int}}
_ruta: str = ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def inicializar(ruta_grafo: str = None):
    """Carga el grafo. Si no se pasa ruta, la deriva del archivo de episodios."""
    global _ruta, _nodos, _aristas
    if not ruta_grafo:
        try:
            from config import EPISODIOS_FILE
            ruta_grafo = os.path.join(os.path.dirname(EPISODIOS_FILE), "coral_grafo.json")
        except Exception:
            ruta_grafo = "coral_grafo.json"
    _ruta = ruta_grafo
    if os.path.exists(_ruta):
        try:
            with open(_ruta, encoding="utf-8") as f:
                data = json.load(f)
            _nodos = data.get("nodos", {})
            _aristas = data.get("aristas", {})
        except Exception as e:
            log.error(f"Coral: error cargando grafo: {e}")
            _nodos, _aristas = {}, {}
    else:
        _nodos, _aristas = {}, {}
    log.info(f"Coral: grafo cargado | {len(_nodos)} conceptos, "
             f"{sum(len(v) for v in _aristas.values()) // 2} relaciones")


def _guardar():
    if not _ruta:
        return
    try:
        os.makedirs(os.path.dirname(_ruta) or ".", exist_ok=True)
        with open(_ruta, "w", encoding="utf-8") as f:
            json.dump({"nodos": _nodos, "aristas": _aristas}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Coral: error guardando grafo: {e}")


# ── Construcción del grafo ───────────────────────────────────────────────────
def agregar_concepto(nombre: str, tipo: str = "concepto") -> str:
    k = _norm(nombre)
    if not k:
        return ""
    if k in _nodos:
        _nodos[k]["peso"] += 1
        _nodos[k]["visto"] = datetime.now().isoformat()
    else:
        _nodos[k] = {"nombre": nombre.strip(), "tipo": tipo, "peso": 1,
                     "visto": datetime.now().isoformat()}
    return k


def conectar(a: str, b: str, rel: str = "se relaciona con", peso: int = 1):
    ka, kb = agregar_concepto(a), agregar_concepto(b)
    if not ka or not kb or ka == kb:
        return
    for x, y in ((ka, kb), (kb, ka)):
        _aristas.setdefault(x, {})
        if y in _aristas[x]:
            _aristas[x][y]["peso"] += peso
        else:
            _aristas[x][y] = {"rel": rel, "peso": peso}


def ingerir(extraccion: dict, guardar: bool = True):
    """Mete en el grafo lo extraído de una sesión: conceptos + relaciones."""
    for c in extraccion.get("conceptos", []):
        if isinstance(c, dict):
            agregar_concepto(c.get("nombre", ""), c.get("tipo", "concepto"))
        elif isinstance(c, str):
            agregar_concepto(c)
    for r in extraccion.get("relaciones", []):
        if isinstance(r, dict) and r.get("a") and r.get("b"):
            conectar(r["a"], r["b"], r.get("rel", "se relaciona con"))
    if guardar:
        _guardar()


# ── Recuerdo por conexión ────────────────────────────────────────────────────
def _tokens(texto: str) -> set:
    return set(re.findall(r"\b[\wáéíóúüñ]{3,}\b", _norm(texto)))


def _semillas(texto: str, max_semillas: int = 4) -> list:
    """Nodos del grafo que aparecen en el texto (matcheo simple; HDC lo afina luego)."""
    toks = _tokens(texto)
    if not toks:
        return []
    candidatos = []
    for k, nodo in _nodos.items():
        ktoks = _tokens(k)
        # coincide si el concepto está nombrado en el texto (por tokens o substring)
        if (ktoks & toks) or (k in _norm(texto)):
            score = len(ktoks & toks) + nodo["peso"] * 0.1
            candidatos.append((score, k))
    candidatos.sort(reverse=True)
    return [k for _, k in candidatos[:max_semillas]]


def relacionados(concepto: str, max_n: int = 6) -> list:
    k = _norm(concepto)
    vecinos = _aristas.get(k, {})
    orden = sorted(vecinos.items(), key=lambda kv: kv[1]["peso"], reverse=True)
    out = []
    for vk, info in orden[:max_n]:
        if vk in _nodos:
            out.append({"nombre": _nodos[vk]["nombre"], "rel": info["rel"], "peso": info["peso"]})
    return out


def recordar(texto: str, max_semillas: int = 4, max_vecinos: int = 5) -> dict:
    """Devuelve el subgrafo conectado a lo que se está hablando."""
    semillas = _semillas(texto, max_semillas)
    bloques = []
    for k in semillas:
        nombre = _nodos[k]["nombre"]
        vecinos = relacionados(nombre, max_vecinos)
        bloques.append({"concepto": nombre, "relaciones": vecinos})
    return {"semillas": [_nodos[k]["nombre"] for k in semillas], "bloques": bloques}


def como_texto(recuerdo: dict) -> str:
    if not recuerdo.get("bloques"):
        return ""
    lineas = []
    for b in recuerdo["bloques"]:
        if b["relaciones"]:
            rels = "; ".join(f"{r['rel']} {r['nombre']}" for r in b["relaciones"])
            lineas.append(f"- {b['concepto']}: {rels}")
        else:
            lineas.append(f"- {b['concepto']}")
    return "Conexiones que recuerdo sobre esto:\n" + "\n".join(lineas)


def stats() -> dict:
    return {"conceptos": len(_nodos),
            "relaciones": sum(len(v) for v in _aristas.values()) // 2}


# ── Aprender de una sesión (extracción con Groq) ─────────────────────────────
_PROMPT_EXTRAER = """De esta conversación entre Sebas y Satella, extraé los CONCEPTOS clave (proyectos, tecnologías, problemas, decisiones, personas, ideas) y cómo se RELACIONAN entre sí.

Conversación:
{texto}

Respondé SOLO JSON, sin texto afuera:
{{"conceptos": [{{"nombre": "...", "tipo": "proyecto|tecnologia|problema|decision|persona|concepto"}}],
 "relaciones": [{{"a": "...", "b": "...", "rel": "<verbo corto: usa, tiene, resuelve, se relaciona con, llevó a>"}}]}}

Máximo 10 conceptos y 10 relaciones, los más importantes. Usá nombres concretos y consistentes."""


def extraer(texto: str) -> dict:
    """Usa Groq para sacar conceptos+relaciones de un texto de sesión."""
    vacio = {"conceptos": [], "relaciones": []}
    if not texto or not texto.strip():
        return vacio
    try:
        from nucleo.habilidades.python import _llm
    except Exception:
        return vacio
    if not _llm.disponible():
        return vacio
    try:
        salida = _llm.chat(_PROMPT_EXTRAER.format(texto=texto[:3000]),
                           max_tokens=700, temperature=0.2)
    except Exception as e:
        log.error(f"Coral: extracción falló: {e}")
        return vacio
    if not salida:
        return vacio
    s = salida.replace("```json", "").replace("```", "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        return vacio
    try:
        obj = json.loads(s[i:j + 1])
        return {"conceptos": obj.get("conceptos", []), "relaciones": obj.get("relaciones", [])}
    except Exception:
        return vacio


def aprender_de_sesion(texto: str) -> dict:
    """Extrae conceptos de la sesión y los teje en el grafo. Se llama al cerrar sesión."""
    ext = extraer(texto)
    if ext.get("conceptos") or ext.get("relaciones"):
        ingerir(ext)
        log.info(f"Coral: aprendí {len(ext.get('conceptos', []))} concepto(s) "
                 f"y {len(ext.get('relaciones', []))} relación(es) de la sesión")
    return stats()