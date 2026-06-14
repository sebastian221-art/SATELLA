"""
nucleo/habilidades/gobernador/skill.py — GOBERNADOR DE PERMISOS.
La capa de control de Satella. No genera contenido: gestiona qué puede hacer
Satella sobre el mundo real. Por chat te deja:
  - ver la política actual (modo, kill, allowlist)
  - cambiar de modo (seguro / normal / auditoría)
  - prender/apagar el kill switch (freno de emergencia)
  - ver la auditoría (qué hizo y con qué permiso)
  - ver / aprobar / rechazar acciones pendientes de confirmación

Por debajo expone `motor.evaluar(...)`, la puerta que las habilidades 4-7
(navegador, agentes, OS) van a llamar antes de actuar.
"""
from nucleo.habilidades import contrato
from . import detector, motor, politica, auditoria

NOMBRE = "gobernador"
DESCRIPCION = (
    "Capa de control y seguridad de Satella: define qué puede hacer sola y qué "
    "requiere tu confirmación, lleva un registro de auditoría y tiene un freno de "
    "emergencia (kill switch). Es el candado previo al navegador, los agentes y el OS."
)
EJEMPLOS = [
    "mostrame los permisos",
    "poné modo seguro",
    "activá el kill switch",
    "qué hiciste / mostrame la auditoría",
    "mostrame los pendientes",
    "aprobá a1b2c3d4",
]
VERSION = "1.0"

_NIVEL_DESC = {
    politica.LECTURA:    "leer / inspeccionar (sin efecto)",
    politica.ESCRITURA:  "crear / modificar archivos",
    politica.NAVEGACION: "abrir / actuar sobre webs",
    politica.EJECUCION:  "ejecutar comandos con efecto",
    politica.SISTEMA:    "acciones de sistema (alto riesgo)",
    politica.PROHIBIDO:  "credenciales ajenas / atacar terceros",
}


def detecta(texto, codigo_adjunto=""):
    return detector.detecta(texto, codigo_adjunto)


def manejar(texto, contexto=None):
    accion, arg = detector.intencion(texto)

    if accion == "kill":
        estado = motor.kill(arg)
        if estado:
            resumen = "Kill switch ACTIVADO — toda acción con efecto está bloqueada."
            cuerpo = ("🔴 **Kill switch ACTIVADO**\n\n"
                      "Satella no va a ejecutar ninguna acción con efecto (escritura, "
                      "navegación, ejecución, sistema). La lectura/análisis sigue disponible.\n\n"
                      "Para soltar el freno: «desactivá el kill switch».")
        else:
            resumen = "Kill switch desactivado — Satella vuelve a operar según el modo."
            cuerpo = ("🟢 **Kill switch desactivado**\n\n"
                      f"Satella vuelve a operar en modo **{motor.modo()}**.")
        return contrato.resultado(NOMBRE, "kill", resumen, cuerpo, ok=True)

    if accion == "modo":
        nuevo = motor.modo(arg)
        descr = {
            politica.MODO_SEGURO: "todo lo que no sea lectura pide tu confirmación.",
            politica.MODO_NORMAL: "la escritura en lo tuyo es libre; navegación, ejecución y sistema confirman.",
            politica.MODO_AUDITORIA: "como normal, pero registra absolutamente todo, incluidas las lecturas.",
        }.get(nuevo, "")
        resumen = f"Modo de seguridad: {nuevo}."
        cuerpo = f"⚙️ **Modo {nuevo}**\n\n{descr}"
        return contrato.resultado(NOMBRE, "modo", resumen, cuerpo, ok=True)

    if accion == "auditoria":
        filas = auditoria.historial(20)
        if not filas:
            return contrato.resultado(NOMBRE, "auditoria",
                                      "Auditoría vacía.",
                                      "Todavía no hay acciones registradas.", ok=True)
        lineas = ["── Auditoría (últimas acciones) ──"]
        for f in filas:
            ts = f.get("ts", "")[11:19]
            ev = f.get("evento", "?")
            if ev == "evaluar":
                lineas.append(f"[{ts}] {f.get('veredicto','?')} · {f.get('nivel','?')} · {f.get('accion','')[:70]}")
            elif ev == "confirmacion":
                ok = "aprobada" if f.get("aprobado") else "rechazada"
                lineas.append(f"[{ts}] confirmación {ok} · {f.get('accion','')[:60]}")
            elif ev == "cambio_modo":
                lineas.append(f"[{ts}] cambio de modo → {f.get('modo')}")
            elif ev == "kill_switch":
                lineas.append(f"[{ts}] kill switch {'ON' if f.get('activo') else 'OFF'}")
            elif ev == "allowlist_add":
                lineas.append(f"[{ts}] allowlist + {f.get('dominio') or f.get('ruta')}")
            else:
                lineas.append(f"[{ts}] {ev}")
        return contrato.resultado(NOMBRE, "auditoria",
                                  f"{len(filas)} eventos recientes.",
                                  "\n".join(lineas), ok=True)

    if accion == "pendientes":
        pend = motor.pendientes()
        if not pend:
            return contrato.resultado(NOMBRE, "pendientes", "No hay acciones pendientes.",
                                      "No hay nada esperando tu confirmación.", ok=True)
        lineas = ["── Acciones pendientes de confirmación ──"]
        for p in pend:
            lineas.append(f"• [{p['token']}] {p['nivel']} · {p['accion'][:70]}\n  {p['razon']}")
        lineas.append("\nAprobá con «aprobá <token>» o rechazá con «rechazá <token>».")
        return contrato.resultado(NOMBRE, "pendientes", f"{len(pend)} pendiente(s).",
                                  "\n".join(lineas), ok=True)

    if accion in ("aprobar", "rechazar"):
        if not arg:
            pend = motor.pendientes()
            if len(pend) == 1:
                arg = pend[0]["token"]   # si hay uno solo, no hace falta el token
            else:
                return contrato.resultado(
                    NOMBRE, accion, "Falta el token.",
                    "Decime cuál: «aprobá <token>». Mirá «pendientes» para ver los tokens.", ok=True)
        res = motor.confirmar(arg, aprobado=(accion == "aprobar"))
        if not res["ok"]:
            return contrato.resultado(NOMBRE, accion, "No encontré ese pendiente.",
                                      res["razon"], ok=True)
        verbo = "aprobada" if accion == "aprobar" else "rechazada"
        acc = res["accion"]["accion"]
        resumen = f"Acción {verbo}."
        cuerpo = (f"{'✅' if accion=='aprobar' else '🚫'} Acción **{verbo}**: {acc[:120]}\n\n"
                  + ("La habilidad que la pidió puede proceder." if accion == "aprobar"
                     else "La habilidad que la pidió no va a ejecutarla."))
        return contrato.resultado(NOMBRE, accion, resumen, cuerpo, ok=True)

    # Por defecto: mostrar la política/estado actual
    est = motor.politica_actual()
    pend = motor.pendientes()
    lineas = [
        "── Estado del Gobernador ──",
        f"Modo: **{est['modo']}**" + ("   ·   🔴 KILL SWITCH ACTIVO" if est["kill"] else ""),
        "",
        "Niveles de acción y qué hace Satella con cada uno:",
    ]
    for niv in politica.ORDEN:
        ver, _ = politica.decidir(est["modo"], niv, propio=False)
        marca = {politica.PERMITIDO: "libre", politica.CONFIRMAR: "pide confirmación",
                 politica.DENEGADO: "denegado"}[ver]
        lineas.append(f"  • {niv} ({_NIVEL_DESC[niv]}): {marca}")
    lineas.append("")
    lineas.append("Sobre objetivos propios («es mío»), la escritura queda libre en modo normal; "
                  "ejecución y sistema siguen pidiendo confirmación; lo prohibido nunca se permite.")
    if est["allow_dominios"] or est["allow_rutas"]:
        lineas.append(f"\nLista blanca: dominios={est['allow_dominios']} · rutas={est['allow_rutas']}")
    if pend:
        lineas.append(f"\n⏳ {len(pend)} acción(es) pendiente(s) de confirmación (pedí «pendientes»).")
    lineas.append("\nComandos: «modo seguro/normal/auditoría» · «activá/desactivá kill switch» · "
                  "«auditoría» · «pendientes» · «aprobá <token>».")
    return contrato.resultado(NOMBRE, "politica", "Estado de seguridad de Satella.",
                              "\n".join(lineas), ok=True)