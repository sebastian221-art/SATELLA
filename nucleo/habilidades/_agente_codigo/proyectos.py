"""
nucleo/habilidades/agente_codigo/proyectos.py
─────────────────────────────────────────────────────────────────────────────
PROYECTOS desde GitHub — para no andar adivinando rutas locales.

Satella clona (o actualiza) un repo en una carpeta externa `proyectos/` y de
ahí en más lo referenciás por NOMBRE. El agente resuelve los archivos que
mencionás contra esa carpeta.

Carpeta por defecto:  <carpeta que contiene SATELLA>/proyectos
(configurable con PROYECTOS_DIR en config.py)

Acepta:
  - URL completa:     https://github.com/usuario/repo(.git)
  - forma corta:      usuario/repo
  - nombre pelado:    repo   (usa GITHUB_USER de config.py si está)
"""
import logging
import re
import subprocess
import unicodedata
from pathlib import Path

log = logging.getLogger("satella.agente.proyectos")

# Carpeta externa proyectos/ (hermana del repo SATELLA)
_DEFAULT_BASE = Path(__file__).resolve().parents[3].parent / "proyectos"
try:
    from config import PROYECTOS_DIR
    _BASE = Path(PROYECTOS_DIR) if PROYECTOS_DIR else _DEFAULT_BASE
except Exception:
    _BASE = _DEFAULT_BASE

try:
    from config import GITHUB_USER
except Exception:
    GITHUB_USER = ""

EXT_CODIGO = {".py", ".html", ".htm", ".css", ".js", ".json", ".md", ".txt"}


def base() -> Path:
    _BASE.mkdir(parents=True, exist_ok=True)
    return _BASE


def _slug(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", (nombre or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9._\-]+", "-", s).strip("-")


def resolver_url(referencia: str) -> tuple:
    """De una referencia suelta saca (url, nombre). (None, None) si no se puede."""
    ref = (referencia or "").strip().strip(".,;:")
    # URL completa
    m = re.search(r"https?://[^\s]+", ref)
    if m:
        url = m.group(0)
        if not url.endswith(".git"):
            url += ".git"
        nombre = re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1])
        return url, nombre
    # forma usuario/repo
    m = re.search(r"\b([\w\-]+)/([\w\-.]+)\b", ref)
    if m:
        usuario, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
        return f"https://github.com/{usuario}/{repo}.git", repo
    # nombre pelado → usa GITHUB_USER si está configurado
    m = re.search(r"\b([\w\-]{3,})\b", ref)
    if m and GITHUB_USER:
        repo = m.group(1)
        return f"https://github.com/{GITHUB_USER}/{repo}.git", repo
    return None, None


def ruta(nombre: str) -> Path:
    return base() / _slug(nombre)


def existe(nombre: str) -> bool:
    return ruta(nombre).exists()


def clonar(referencia: str) -> dict:
    """Clona el repo (o hace pull si ya está). Devuelve {ok, nombre, ruta, mensaje}."""
    url, nombre = resolver_url(referencia)
    if not url:
        return {"ok": False, "mensaje": ("No supe de qué repo hablás. Dame la URL completa "
                                         "(https://github.com/usuario/repo) o configurá GITHUB_USER "
                                         "en config.py para usar solo el nombre.")}
    destino = ruta(nombre)
    try:
        if destino.exists():
            # ya estaba → actualizar
            r = subprocess.run(["git", "-C", str(destino), "pull", "--ff-only"],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return {"ok": True, "nombre": nombre, "ruta": str(destino),
                        "mensaje": f"Ya estaba clonado en proyectos/{_slug(nombre)} (no pude actualizar: {r.stderr.strip()[:160]})."}
            return {"ok": True, "nombre": nombre, "ruta": str(destino),
                    "mensaje": f"Actualicé proyectos/{_slug(nombre)} con lo último de GitHub."}
        base()
        r = subprocess.run(["git", "clone", url, str(destino)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return {"ok": False, "mensaje": f"Falló el clone: {r.stderr.strip()[:200]}"}
        return {"ok": True, "nombre": nombre, "ruta": str(destino),
                "mensaje": f"Cloné {nombre} en proyectos/{_slug(nombre)}. Ya lo podés referenciar por nombre."}
    except FileNotFoundError:
        return {"ok": False, "mensaje": "No encontré 'git' en el sistema. Instalá Git y reintentá."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "El clone tardó demasiado (timeout)."}
    except Exception as e:
        return {"ok": False, "mensaje": f"Error clonando: {e}"}


def listar_archivos(nombre: str, exts: set = None) -> list:
    """Todos los archivos de código del proyecto (rutas absolutas)."""
    raiz = ruta(nombre)
    if not raiz.exists():
        return []
    exts = exts or EXT_CODIGO
    out = []
    for p in raiz.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts and ".git" not in p.parts:
            out.append(str(p))
    return out


def resolver_archivos(nombre: str, mencionados: list) -> list:
    """Matchea los archivos que mencionó el usuario contra el proyecto clonado.

    'panela-bloque.html' → proyectos/bellavista/panela-bloque.html (lo busca aunque
    esté en subcarpetas). Si no menciona ninguno, devuelve [] (el agente avisa)."""
    raiz = ruta(nombre)
    if not raiz.exists() or not mencionados:
        return []
    todos = listar_archivos(nombre)
    resueltos = []
    for m in mencionados:
        base_m = _slug(Path(m).name)
        for ruta_abs in todos:
            if _slug(Path(ruta_abs).name) == base_m:
                resueltos.append(ruta_abs)
                break
    return resueltos