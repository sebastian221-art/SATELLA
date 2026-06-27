"""
nucleo/habilidades/telemetria/skill.py — EL TABLERO (lectura).
─────────────────────────────────────────────────────────────────────────────
La cara visible del cuaderno: deja que le preguntes a Satella por su propio
trabajo y ella LEA la telemetría — cuánto trabajó, qué usa más, qué le falla,
cuánto gastó. Es read-only (riesgo CERO) y es el primer consumidor del cuaderno,
antes de que lleguen el auditor y el predictor.

Modos (los detecta solo):
  resumen  → "cómo venís de trabajo" / "tu tablero" / "tus métricas"
  costo    → "cuánto gastaste" / "cuánto va costando"
  ranking  → "qué habilidad usás más" / "qué es lo más lento"
  fallos   → "qué te falló" / "tus errores"

Siempre devuelve ok=True una vez que detecta() disparó: la respuesta es SUYA.
"""
import logging

from nucleo.habilidades import contrato

try:
    from nucleo import telemetria as _tel
    _TEL_OK = True
except Exception:  # pragma: no cover
    _TEL_OK = False
    _tel = None

log = logging.getLogger("satella.habilidad.telemetria")

NOMBRE = "telemetria"
DESCRIPCION = "Lee el cuaderno de Satella y reporta su propio trabajo: uso, costo, latencia y fallos."
EJEMPLOS = [
    "cómo venís de trabajo",
    "mostrame tu tablero",
    "cuánto gastaste hoy",
    "qué habilidad usás más",
    "qué te falló últimamente",
]

# ── Triggers (frases puntuales, para no robarle turnos a nadie) ──────────────
_T_COSTO = ("cuánto gastaste", "cuanto gastaste", "cuánto va costando",
            "cuanto va costando", "cuánto gastás", "cuanto gastas",
            "cuánto llevás gastado", "cuanto llevas gastado", "tu costo",
            "cuánto costó todo", "cuanto costo todo", "gasto total")
_T_RANKING = ("qué habilidad usás más", "que habilidad usas mas",
              "qué skill usás más", "que skill usas mas", "qué usás más",
              "que usas mas", "qué es lo más lento", "que es lo mas lento",
              "habilidad más usada", "habilidad mas usada", "ranking de habilidades",
              "qué es lo más rápido", "que es lo mas rapido")
_T_FALLOS = ("qué te falló", "que te fallo", "qué te ha fallado", "que te ha fallado",
             "tus errores", "qué errores tuviste", "que errores tuviste",
             "qué viene fallando", "que viene fallando", "tus fallos")
_T_RESUMEN = ("cómo venís de trabajo", "como venis de trabajo", "tu tablero",
              "mostrame tu tablero", "tus métricas", "tus metricas",
              "tu telemetría", "tu telemetria", "cómo venís trabajando",
              "como venis trabajando", "cuánto trabajaste", "cuanto trabajaste",
              "tu rendimiento", "cómo te fue de trabajo", "como te fue de trabajo",
              "tu actividad", "qué tanto trabajaste", "que tanto trabajaste")

_TODOS = _T_COSTO + _T_RANKING + _T_FALLOS + _T_RESUMEN


def detecta(texto: str, codigo_adjunto: str = "") -> bool:
    t = (texto or "").lower()
    return any(k in t for k in _TODOS)


def _modo(texto: str) -> str:
    t = (texto or "").lower()
    if any(k in t for k in _T_COSTO):
        return "costo"
    if any(k in t for k in _T_RANKING):
        return "ranking"
    if any(k in t for k in _T_FALLOS):
        return "fallos"
    return "resumen"


def manejar(texto: str, contexto: dict = None) -> dict:
    if not _TEL_OK:
        return contrato.resultado(
            NOMBRE, "tablero", "no tengo el cuaderno disponible",
            "No pude cargar la telemetría. Revisá que nucleo/telemetria.py esté en su lugar.",
            ok=True)

    modo = _modo(texto)
    try:
        if modo == "costo":
            return _costo()
        if modo == "ranking":
            return _ranking()
        if modo == "fallos":
            return _fallos()
        return _resumen()
    except Exception as e:
        log.error(f"[TEL] error leyendo cuaderno: {e}")
        return contrato.resultado(
            NOMBRE, "tablero", "no pude leer el cuaderno",
            f"Algo falló leyendo mi propio cuaderno: {e}", ok=True)


# ── Modos ────────────────────────────────────────────────────────────────────
def _resumen() -> dict:
    r = _tel.resumen()
    if r["total_eventos"] == 0:
        return contrato.resultado(
            NOMBRE, "tablero", "cuaderno vacío",
            "Mi cuaderno está vacío todavía — no he registrado trabajo. "
            "Pedime algo (código, una búsqueda, lo que sea) y empiezo a anotar.",
            ok=True)

    top = _tel.mas_usadas(3)
    top_txt = ", ".join(f"{s} (×{n})" for s, n in top) if top else "—"
    costo = f"${r['costo_total']:.4f}" if r["costo_total"] else "sin costo registrado"

    cuerpo = (
        f"Mi tablero, hasta ahora:\n"
        f"- Trabajos hechos: {r['total_eventos']} ({r['ok']} bien, {r['fallos']} fallidos · "
        f"{int(r['ok_rate']*100)}% éxito)\n"
        f"- Más usadas: {top_txt}\n"
        f"- Latencia: {r['ms_promedio']}ms promedio, {r['ms_p95']}ms en el peor 5%\n"
        f"- Costo acumulado: {costo}\n"
        f"- Habilidades distintas usadas: {r['skills_distintas']}"
    )
    resumen = (f"{r['total_eventos']} trabajos, {int(r['ok_rate']*100)}% éxito, "
               f"{('$'+format(r['costo_total'],'.4f')) if r['costo_total'] else 'sin costo'}")
    return contrato.resultado(NOMBRE, "tablero", resumen, cuerpo, ok=True)


def _costo() -> dict:
    r = _tel.resumen()
    ps = _tel.por_skill()
    con_costo = sorted(
        [(s, v["costo_total"]) for s, v in ps.items() if v["costo_total"] > 0],
        key=lambda kv: kv[1], reverse=True)

    if r["costo_total"] <= 0:
        return contrato.resultado(
            NOMBRE, "costo", "sin costo registrado todavía",
            "Todavía no tengo costo anotado. El costo se registra cuando una "
            "habilidad lo expone (por ahora, las que pasan por Claude Code). "
            "En cuanto las conectemos a reportar su gasto, esto se llena solo.",
            ok=True)

    detalle = "\n".join(f"- {s}: ${c:.4f}" for s, c in con_costo[:8])
    cuerpo = (f"Llevo gastado ${r['costo_total']:.4f} en total"
              + (f", repartido así:\n{detalle}" if detalle else "."))
    return contrato.resultado(NOMBRE, "costo",
                              f"gasto total ${r['costo_total']:.4f}", cuerpo, ok=True)


def _ranking() -> dict:
    usadas = _tel.mas_usadas(6)
    lentas = _tel.mas_lentas(5)
    if not usadas:
        return contrato.resultado(NOMBRE, "ranking", "cuaderno vacío",
                                  "Todavía no registré nada como para armar un ranking.", ok=True)
    u_txt = "\n".join(f"- {s}: {n} veces" for s, n in usadas)
    l_txt = "\n".join(f"- {s}: {ms}ms promedio" for s, ms in lentas if ms > 0)
    cuerpo = f"Lo que más uso:\n{u_txt}"
    if l_txt:
        cuerpo += f"\n\nLo que más me cuesta (lento):\n{l_txt}"
    return contrato.resultado(NOMBRE, "ranking",
                              f"top: {usadas[0][0]} (×{usadas[0][1]})", cuerpo, ok=True)


def _fallos() -> dict:
    fallos = _tel.fallos_recientes(8)
    if not fallos:
        return contrato.resultado(
            NOMBRE, "fallos", "sin fallos recientes",
            "Sin fallos en el cuaderno. Por ahora vengo limpia.", ok=True)
    lineas = []
    for e in fallos:
        err = e.get("error")
        cola = f" — {err}" if err else ""
        lineas.append(f"- [{e.get('ts','?')[-8:]}] {e.get('skill','?')} ({e.get('modo','?')}){cola}")
    cuerpo = "Lo que viene fallando:\n" + "\n".join(lineas)
    return contrato.resultado(NOMBRE, "fallos", f"{len(fallos)} fallo(s) reciente(s)", cuerpo, ok=True)