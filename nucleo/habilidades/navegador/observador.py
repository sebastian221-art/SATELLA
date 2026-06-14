"""
nucleo/habilidades/navegador/observador.py — MODO OBSERVADOR (Fase 4C).

Satella te mira hacer una tarea UNA vez en el navegador en vivo, graba tus clics
y lo que escribís (con selector robusto + texto visible), y lo guarda como una
RECETA por sitio en datos/navegador/recetas/<nombre>.json. Después la repite sola.

- Las contraseñas NO se guardan (quedan como paso 'password' que el reproductor
  saltea). El manejo seguro de credenciales con el llavero de Windows es el
  siguiente escalón de 4C.
- Reproducir tiene self-heal: si un selector se rompió, cae a clic-por-texto.
"""
import json
import re
import time
from pathlib import Path

from . import motor

_DIR = Path("datos/navegador/recetas")
_estado = {"grabando": False, "dominio": "", "inicio": ""}


def _slug(nombre):
    return re.sub(r"[^\w-]+", "_", (nombre or "").strip().lower()).strip("_") or "receta"


def _dominio(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return (m.group(1).replace("www.", "") if m else "sitio")


def grabando():
    return _estado["grabando"]


def cancelar():
    """Corta la grabación sin guardarla (al salir del modo navegador)."""
    if _estado["grabando"]:
        try:
            motor.detener_grabacion()
        except Exception:
            pass
        _estado["grabando"] = False
    return {"ok": True}


def iniciar():
    if not motor.activo():
        return {"ok": False, "razon": "El navegador no está abierto."}
    st = motor.estado()
    inicio = st.get("url", "")
    r = motor.iniciar_grabacion(inicio_url=inicio)
    if not r.get("ok"):
        return r
    _estado.update({"grabando": True, "dominio": _dominio(inicio), "inicio": inicio})
    return {"ok": True, "dominio": _estado["dominio"]}


def detener_y_guardar(nombre):
    if not _estado["grabando"]:
        return {"ok": False, "razon": "No estaba observando nada."}
    pasos = motor.detener_grabacion()
    _estado["grabando"] = False
    # comprimir pasos redundantes consecutivos
    limpio = []
    for p in pasos:
        if limpio and p.get("tipo") == "click" and limpio[-1].get("tipo") == "click" \
                and p.get("selector") == limpio[-1].get("selector"):
            continue
        # inputs consecutivos en el mismo campo → quedarse con el último valor
        if p.get("tipo") == "input" and limpio and limpio[-1].get("tipo") == "input" \
                and p.get("selector") == limpio[-1].get("selector"):
            limpio[-1] = p
            continue
        limpio.append(p)
    slug = _slug(nombre)
    _DIR.mkdir(parents=True, exist_ok=True)
    receta = {"nombre": slug, "titulo": (nombre or slug).strip(), "dominio": _estado["dominio"],
              "inicio": _estado["inicio"], "creada": time.strftime("%Y-%m-%d %H:%M"),
              "pasos": limpio}
    (_DIR / f"{slug}.json").write_text(json.dumps(receta, ensure_ascii=False, indent=2), encoding="utf-8")
    pw = sum(1 for p in limpio if p.get("password"))
    return {"ok": True, "nombre": slug, "n": len(limpio), "pw": pw}


def listar():
    if not _DIR.exists():
        return []
    out = []
    for f in sorted(_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"nombre": d.get("nombre", f.stem), "titulo": d.get("titulo", f.stem),
                        "dominio": d.get("dominio", ""), "n": len(d.get("pasos", []))})
        except Exception:
            continue
    return out


def cargar(nombre):
    f = _DIR / f"{_slug(nombre)}.json"
    if not f.exists():
        # intentar por título aproximado
        for c in listar():
            if _slug(nombre) in c["nombre"] or _slug(nombre) in _slug(c["titulo"]):
                f = _DIR / f"{c['nombre']}.json"
                break
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def reproducir(nombre, variable=None):
    receta = cargar(nombre)
    if not receta:
        return {"ok": False, "razon": "no_existe"}
    res = motor.reproducir_pasos(receta.get("pasos", []), variable=variable)
    res["titulo"] = receta.get("titulo", nombre)
    res["total"] = len(receta.get("pasos", []))
    return res