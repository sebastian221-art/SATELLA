"""
nucleo/habilidades/ingestor/skill.py — APRENDER DE MIS ARCHIVOS.
─────────────────────────────────────────────────────────────────────────────
La cara conversacional del ingestor. Le decís a Satella que aprenda de los
archivos que dejaste en datos/aprender/ y ella los lee y los teje en Coral.

Modos (los detecta solo):
  aprender → "aprendé de mis archivos" / "ingerí la carpeta" / "leé lo que te dejé"
  estado   → "qué tenés para aprender" / "qué hay en la carpeta de aprender"

Siempre devuelve ok=True una vez que detecta() disparó: la respuesta es SUYA.
"""
import logging

from nucleo.habilidades import contrato

try:
    from nucleo import ingestor as _ing
    _ING_OK = True
except Exception:  # pragma: no cover
    _ING_OK = False
    _ing = None

try:
    from nucleo import progreso as _prog
except Exception:  # pragma: no cover
    _prog = None

log = logging.getLogger("satella.habilidad.ingestor")

NOMBRE = "ingestor"
DESCRIPCION = ("Aprende de los archivos que dejás en datos/aprender/ y los teje en la "
               "memoria de Satella (Coral): notas, código, documentación, exports.")
EJEMPLOS = [
    "aprendé de mis archivos",
    "ingerí la carpeta de aprender",
    "leé lo que te dejé y aprendelo",
    "qué tenés para aprender",
]

_T_ESTADO = ("qué tenés para aprender", "que tenes para aprender",
             "qué hay para aprender", "que hay para aprender",
             "qué hay en la carpeta de aprender", "que hay en la carpeta de aprender",
             "cuántos archivos tenés para aprender", "cuantos archivos tenes para aprender")
_T_APRENDER = ("aprendé de mis archivos", "aprende de mis archivos",
               "aprendé de mis notas", "aprende de mis notas",
               "ingerí la carpeta", "ingeri la carpeta", "ingerí mis archivos",
               "ingeri mis archivos", "leé lo que te dejé", "lee lo que te deje",
               "aprendé de la carpeta", "aprende de la carpeta",
               "leé mis archivos", "lee mis archivos", "cargá mis archivos",
               "carga mis archivos", "actualizá tu memoria con mis archivos",
               "actualiza tu memoria con mis archivos", "aprendé de lo que te dejé",
               "aprende de lo que te deje", "leé la carpeta de aprender",
               "lee la carpeta de aprender")
_T_FORZAR = ("de nuevo", "otra vez", "todo de nuevo", "reaprende", "reaprendé",
             "desde cero", "forzá", "forza")


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    return any(k in t for k in (_T_ESTADO + _T_APRENDER))


def manejar(texto: str, contexto: dict = None) -> dict:
    if not _ING_OK:
        return contrato.resultado(
            NOMBRE, "ingestor", "no tengo el ingestor disponible",
            "No pude cargar el ingestor (nucleo/ingestor.py). Revisá que esté en su lugar.",
            ok=True)

    t = (texto or "").lower()
    if any(k in t for k in _T_ESTADO) and not any(k in t for k in _T_APRENDER):
        return _estado()
    return _aprender(forzar=any(k in t for k in _T_FORZAR))


def _avisar(texto: str):
    if _prog is not None:
        try:
            _prog.emitir(texto)
        except Exception:
            pass


def _estado() -> dict:
    e = _ing.estado()
    if e["total"] == 0:
        return contrato.resultado(
            NOMBRE, "estado", "no hay archivos para aprender",
            f"No tengo nada en mi carpeta de aprendizaje todavía.\n"
            f"Dejá ahí tus notas, código o exports (.md, .txt, .json) y decime "
            f"«aprendé de mis archivos».\nCarpeta: {e['carpeta']}",
            ok=True)
    return contrato.resultado(
        NOMBRE, "estado", f"{e['total']} archivo(s) en la carpeta",
        f"Tengo {e['total']} archivo(s) en mi carpeta de aprendizaje, de los cuales "
        f"{e['pendientes']} están sin leer todavía.\n"
        f"Decime «aprendé de mis archivos» y los tejo en mi memoria.\nCarpeta: {e['carpeta']}",
        ok=True)


def _aprender(forzar: bool = False) -> dict:
    _avisar("Abriendo mi carpeta de aprendizaje…")
    r = _ing.ingerir_carpeta(forzar=forzar, avisar=_avisar)

    if r.get("vacia"):
        return contrato.resultado(
            NOMBRE, "aprender", "carpeta vacía",
            f"Mi carpeta de aprendizaje está vacía. Dejá ahí tus notas, código o "
            f"exports (.md, .txt, .json) y volvé a pedirme que aprenda.\n"
            f"Carpeta: {_ing.carpeta()}",
            ok=True)

    if r.get("sin_modelo"):
        return contrato.resultado(
            NOMBRE, "aprender", "no tengo el modelo para extraer",
            "Encontré archivos, pero no tengo el modelo (Groq) disponible para "
            "extraer los conceptos. Revisá la GROQ_API_KEY y volvé a intentar.",
            ok=True)

    if r["archivos"] == 0 and r["saltados"] > 0:
        return contrato.resultado(
            NOMBRE, "aprender", "ya estaba todo aprendido",
            f"Ya había leído esos {r['saltados']} archivo(s) antes — no hay nada nuevo "
            f"que aprender. Si querés que los relea de cero, decime «aprendé de mis "
            f"archivos de nuevo».",
            ok=True)

    # Detalle por archivo (acotado para no inundar).
    lineas = []
    for d in r["detalle"][:12]:
        linea = f"- {d['archivo']}: +{d['conceptos']} conceptos, +{d['relaciones']} relaciones"
        if d.get("incompleto"):
            linea += f"  ⏳ ({d.get('hechos')}/{d.get('total')} fragmentos)"
        lineas.append(linea)
    detalle = "\n".join(lineas)
    extra = f"\n(+{len(r['detalle']) - 12} archivo(s) más)" if len(r["detalle"]) > 12 else ""
    saltados = f"\nSalté {r['saltados']} que ya tenía leídos." if r["saltados"] else ""

    incompletos = [d for d in r["detalle"] if d.get("incompleto")]
    aviso_seguir = ""
    if incompletos:
        faltan = sum((d.get("total", 0) - d.get("hechos", 0)) for d in incompletos)
        aviso_seguir = (f"\n\nHay {len(incompletos)} archivo(s) grande(s) que leí por tandas: "
                        f"me faltan {faltan} fragmento(s). Decime «aprendé de mis archivos» "
                        f"otra vez y sigo desde donde quedé (no repito lo ya leído).")

    cuerpo = (
        f"Leí {r['archivos']} archivo(s) y tejí {r['conceptos']} conceptos y "
        f"{r['relaciones']} relaciones en mi memoria.{saltados}\n\n{detalle}{extra}{aviso_seguir}"
    )
    resumen = f"aprendí de {r['archivos']} archivo(s): +{r['conceptos']} conceptos"
    return contrato.resultado(NOMBRE, "aprender", resumen, cuerpo, ok=True)