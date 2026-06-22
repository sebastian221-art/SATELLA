"""
nucleo/habilidades/agente_codigo/agente.py
─────────────────────────────────────────────────────────────────────────────
EL ESQUELETO DEL AGENTE.

Recibe una MISIÓN sobre un PROYECTO y corre el loop:
    recordar (manual) → proponer EDICIONES puntuales (cerebro) → aplicar →
    VERIFICAR → si funciona: guardar en el manual
              → si no, reintentar; si se agota: ESCALAR a Sebas.

CAMBIO CLAVE vs v1: NO reescribe el archivo entero (frágil, se trunca en
archivos grandes). Pide ediciones tipo BUSCAR/REEMPLAZAR y las aplica por
string-replace. Salida chica → sin truncamiento → sirve hasta en el index de
1781 líneas.

Las "manos": Python → tu ejecutor (verificación real); web → chequeo estructural
(+ gancho a tu navegador). Toda escritura pasa por el GOBERNADOR.
"""
import logging
import re
from pathlib import Path

from . import manual, cerebro

log = logging.getLogger("satella.agente")

MAX_CICLOS = 3
EXT_WEB = {".html", ".htm", ".css", ".js"}
EXT_PY = {".py"}

# ── Gobernador ───────────────────────────────────────────────────────────────
try:
    from nucleo.habilidades.gobernador import motor as _gob, politica as _gpol
    _gob_ok = True
except Exception as e:
    _gob_ok = False
    log.warning(f"[AGENTE] gobernador no disponible, escribo sin él: {e}")


def _permitido(accion: str, objetivo: str) -> tuple:
    if not _gob_ok:
        return True, "sin gobernador"
    v = _gob.evaluar(accion, nivel=_gpol.ESCRITURA, objetivo=objetivo, propio=True)
    if v["veredicto"] == _gpol.PERMITIDO:
        return True, v["razon"]
    if v["veredicto"] == _gpol.CONFIRMAR:
        return False, f"requiere tu confirmación (token {v.get('token')}): {v['razon']}"
    return False, f"denegado: {v['razon']}"


# ── Verificación (verdad de tierra) ──────────────────────────────────────────
_RX_NO_AISLADO = re.compile(
    r"(ModuleNotFoundError|ImportError|No module named|cannot import name|"
    r"attempted relative import|SystemExit|the following arguments are required|^usage:)",
    re.I | re.M,
)


def _verificar(ruta: Path, codigo: str, mision: str = "") -> tuple:
    ext = ruta.suffix.lower()
    if ext in EXT_PY:
        # 1. sintaxis: si rompió, es culpa de la edición → falla dura
        try:
            compile(codigo, str(ruta), "exec")
        except SyntaxError as e:
            return False, f"error de sintaxis: {e}"
        # 2. ejecución consciente (imports del proyecto / argparse no cuentan como error)
        estado_exec, det_exec = _ejecutar_aware(codigo)
        if estado_exec is False:
            return False, det_exec
        # 3. revisión semántica (lo que la ejecución no puede ver)
        ok_rev, det_rev = _revisar(ruta, codigo, mision)
        if not ok_rev:
            return False, det_rev
        return True, f"{det_exec} + {det_rev}"
    if ext in EXT_WEB:
        ok, det = _verificar_web(ruta, codigo)
        if not ok:
            return False, det
        ok_rev, det_rev = _revisar(ruta, codigo, mision)
        if not ok_rev:
            return False, det_rev
        return True, f"{det} + {det_rev}"
    return (bool(codigo.strip()), "archivo no vacío (sin verificación específica)")


def _ejecutar_aware(codigo: str) -> tuple:
    """(estado, detalle). estado: True=corrió, None=no ejecutable aislado, False=error real."""
    try:
        from nucleo.habilidades.python import ejecutor
    except Exception:
        return None, "sintaxis OK (ejecutor no disponible)"
    r = ejecutor.ejecutar(codigo)
    if r.get("ok"):
        return True, f"corrió OK en {r.get('tiempo_ms', 0)}ms"
    err = (r.get("stderr") or "falló la ejecución").strip()
    if _RX_NO_AISLADO.search(err):
        return None, "sintaxis OK (no ejecutable aislado: necesita el proyecto o argumentos)"
    return False, err[:500]


def _revisar(ruta: Path, codigo: str, mision: str) -> tuple:
    """Revisión semántica por el modelo: ¿el cambio cumple el objetivo sin errores obvios?"""
    if not mision or not cerebro.disponible():
        return True, "sin revisión"
    sistema = (
        "Revisás un cambio de código. Te doy el OBJETIVO y el archivo YA modificado. "
        "Decí si el cambio cumple el objetivo SIN introducir errores obvios (variables o "
        "campos inexistentes, lógica invertida, imports que falten para lo NUEVO que se agregó). "
        "No te quejes de imports del proyecto que ya venían de antes. "
        "Respondé EXACTAMENTE 'OK' si está bien, o 'PROBLEMA: <explicación corta>' si algo está mal."
    )
    prompt = f"OBJETIVO: {mision}\nARCHIVO {ruta.name} (ya modificado):\n```\n{codigo}\n```"
    resp = (cerebro.pensar_codigo(prompt, sistema) or "").strip()
    if not resp:
        return True, "sin revisión"
    if resp.upper().startswith("OK"):
        return True, "revisión OK"
    m = re.search(r"PROBLEMA:?\s*(.+)", resp, re.I | re.DOTALL)
    if m:
        return False, "revisión: " + m.group(1).strip()[:300]
    return True, "revisión sin objeciones claras"


def _verificar_web(ruta: Path, codigo: str) -> tuple:
    problemas = []
    low = codigo.lower()
    if "<html" in low and "</html>" not in low:
        problemas.append("falta cerrar </html>")
    if low.count("<style") != low.count("</style>"):
        problemas.append("bloques <style> desbalanceados")
    if low.count("<script") != low.count("</script>"):
        problemas.append("bloques <script> desbalanceados")
    if problemas:
        return False, "; ".join(problemas)
    return True, "estructura OK (lo visual lo mirás vos)"


# ── Ediciones puntuales BUSCAR/REEMPLAZAR ────────────────────────────────────
_RX_BLOQUE = re.compile(
    r"<<<<<<<\s*BUSCAR\s*\n(.*?)\n=======\s*\n(.*?)\n>>>>>>>\s*REEMPLAZAR",
    re.DOTALL,
)


_RX_YA = re.compile(r"(ya (está|esta|estaba|existe|presente|incluid)|no (hace falta|es necesario|hay (nada|cambios)))", re.I)


def _proponer_ediciones(ruta: Path, contenido: str, mision: str,
                        contexto_manual: str, error_previo: str = "") -> tuple:
    """Devuelve (estado, ediciones). estado ∈ {ediciones, sin_cambios, vacio}."""
    sistema = (
        "Sos un agente de código de Satella. Editás archivos reales de un proyecto. "
        "NO reescribas el archivo entero. Devolvés SOLO los cambios como bloques "
        "BUSCAR/REEMPLAZAR, con este formato EXACTO (podés devolver varios):\n"
        "<<<<<<< BUSCAR\n(texto EXACTO copiado del archivo, con poco contexto único)\n"
        "=======\n(texto nuevo)\n>>>>>>> REEMPLAZAR\n"
        "El texto en BUSCAR tiene que estar TAL CUAL aparece en el archivo (mismos "
        "espacios). No agregues explicaciones fuera de los bloques.\n"
        "Si el archivo YA cumple la misión y no hay NADA que cambiar, respondé "
        "EXACTAMENTE con la palabra SIN_CAMBIOS y nada más."
    )
    partes = [f"MISIÓN: {mision}", f"ARCHIVO: {ruta.name}"]
    if contexto_manual:
        partes.append(contexto_manual)
    if error_previo:
        partes.append(f"Tu intento anterior no se pudo aplicar: {error_previo}. "
                      f"Copiá el texto EXACTO del archivo en BUSCAR.")
    partes.append(f"CONTENIDO ACTUAL del archivo:\n```\n{contenido}\n```")
    partes.append("Devolvé los bloques BUSCAR/REEMPLAZAR necesarios, o SIN_CAMBIOS si ya está cumplida.")

    respuesta = cerebro.pensar_codigo("\n\n".join(partes), sistema)
    if not respuesta:
        return "vacio", []
    bloques = [(b.group(1), b.group(2)) for b in _RX_BLOQUE.finditer(respuesta)]
    bloques = [(b, r) for (b, r) in bloques if b != r]  # descartar no-ops
    if bloques:
        return "ediciones", bloques
    if "SIN_CAMBIOS" in respuesta.upper() or _RX_YA.search(respuesta):
        return "sin_cambios", []
    return "vacio", []


def _aplicar(contenido: str, ediciones: list) -> tuple:
    """Aplica los bloques. Devuelve (nuevo_contenido, no_encontrados)."""
    nuevo = contenido
    no_encontrados = []
    for buscar, reemplazar in ediciones:
        if buscar in nuevo:
            nuevo = nuevo.replace(buscar, reemplazar, 1)
        else:
            # match tolerante: ignorar diferencias de espacios al inicio/fin de línea
            flexible = _buscar_flexible(nuevo, buscar)
            if flexible is not None:
                nuevo = nuevo.replace(flexible, reemplazar, 1)
            else:
                frag = buscar.strip().splitlines()[0][:60] if buscar.strip() else "(vacío)"
                no_encontrados.append(frag)
    return nuevo, no_encontrados


def _buscar_flexible(haystack: str, needle: str):
    """Encuentra `needle` permitiendo diferencias de espacios por línea.
    Devuelve el substring EXACTO de haystack que matchea, o None."""
    nl = [l.strip() for l in needle.strip().splitlines() if l.strip()]
    if not nl:
        return None
    hlines = haystack.splitlines(keepends=True)
    for i in range(len(hlines)):
        if hlines[i].strip() == nl[0]:
            j, k = i, 0
            while k < len(nl) and j < len(hlines):
                if hlines[j].strip() == "":
                    j += 1
                    continue
                if hlines[j].strip() != nl[k]:
                    break
                j += 1
                k += 1
            if k == len(nl):
                return "".join(hlines[i:j])
    return None


# ── EL LOOP ──────────────────────────────────────────────────────────────────
def ejecutar_mision(mision: str, proyecto: str, archivos: list) -> dict:
    if not cerebro.disponible():
        return {"estado": "error", "informe": "El cerebro de código no está disponible (revisá GROQ_API_KEY / GROQ_MODEL_CODIGO)."}

    recuerdos = manual.recordar(proyecto, mision)
    contexto = manual.como_contexto(recuerdos)
    cambios, ya_estaban, fallos = [], [], []

    for ruta_str in archivos:
        ruta = Path(ruta_str)
        if not ruta.exists():
            fallos.append({"archivo": ruta.name, "motivo": "no existe el archivo"})
            continue

        contenido = ruta.read_text(encoding="utf-8", errors="ignore")
        error_previo = ""
        ok_archivo = False

        for ciclo in range(1, MAX_CICLOS + 1):
            estado_prop, ediciones = _proponer_ediciones(ruta, contenido, mision, contexto, error_previo)
            if estado_prop == "sin_cambios":
                ya_estaban.append(ruta.name)
                ok_archivo = True
                break
            if estado_prop == "vacio" or not ediciones:
                error_previo = "no devolviste bloques BUSCAR/REEMPLAZAR válidos"
                continue

            nuevo, no_encontrados = _aplicar(contenido, ediciones)
            if no_encontrados:
                error_previo = "no encontré en el archivo: " + " | ".join(no_encontrados)
                log.info(f"[AGENTE] {ruta.name} ciclo {ciclo}: {error_previo}")
                continue
            if nuevo == contenido:
                # se aplicó pero no cambió nada → ya estaba cumplida
                ya_estaban.append(ruta.name)
                ok_archivo = True
                break

            aprobado, detalle = _verificar(ruta, nuevo, mision)
            if not aprobado:
                error_previo = detalle
                log.info(f"[AGENTE] {ruta.name} ciclo {ciclo}: no pasó ({detalle})")
                continue

            puede, razon = _permitido(f"escribir {ruta.name}", str(ruta))
            if not puede:
                fallos.append({"archivo": ruta.name, "motivo": f"gobernador: {razon}"})
                break
            try:
                ruta.write_text(nuevo, encoding="utf-8")
            except Exception as e:
                fallos.append({"archivo": ruta.name, "motivo": f"no pude escribir: {e}"})
                break

            cambios.append({"archivo": ruta.name, "ciclos": ciclo, "ediciones": len(ediciones), "verificacion": detalle})
            ok_archivo = True
            break

        if not ok_archivo and not any(f["archivo"] == ruta.name for f in fallos):
            fallos.append({"archivo": ruta.name, "motivo": f"no se pudo tras {MAX_CICLOS} ciclos: {error_previo}"})

    # ── Resultado + aprendizaje ──────────────────────────────────────────────
    if (cambios or ya_estaban) and not fallos:
        partes = []
        if cambios:
            partes.append(f"Cambié {len(cambios)} archivo(s): " + ", ".join(c["archivo"] for c in cambios))
        if ya_estaban:
            partes.append(f"{len(ya_estaban)} ya estaba(n) al día: " + ", ".join(ya_estaban))
        resumen = " | ".join(partes)
        if cambios:
            manual.registrar_exito(proyecto, mision, [c["archivo"] for c in cambios], resumen)
            detalle = "\n".join(f"• {c['archivo']}: {c['ediciones']} edición(es), {c['verificacion']} (ciclo {c['ciclos']})" for c in cambios)
            resumen = resumen + "\n" + detalle
        return {"estado": "ok", "informe": resumen, "cambios": cambios, "ya_estaban": ya_estaban, "escalado": False}

    if fallos:
        motivo = "; ".join(f"{f['archivo']}: {f['motivo']}" for f in fallos)
        manual.registrar_escalacion(proyecto, mision, motivo, MAX_CICLOS)
        hechos = f"{len(cambios)} cambiado(s), {len(ya_estaban)} ya estaba(n)"
        informe = (f"No pude completar todo y te lo escalo.\n"
                   f"Hecho: {hechos}. Trabado en: {motivo}\n"
                   f"Cuando lo arregles, enseñámelo (\"aprendé que…\") y la próxima lo hago solo.")
        return {"estado": "escalado", "informe": informe, "cambios": cambios,
                "ya_estaban": ya_estaban, "escalado": True, "motivo": motivo}

    return {"estado": "sin_cambios", "informe": "No había nada que cambiar o no se especificaron archivos."}


def aprender_de_arreglo(proyecto: str, mision: str, solucion: str) -> dict:
    manual.aprender_de_arreglo(proyecto, mision, solucion)
    return {"estado": "aprendido", "informe": f"Anotado en el manual de {proyecto}. La próxima vez que aparezca algo parecido, ya sé qué hacer."}


def elegir_archivos(mision: str, archivos_abs: list, max_archivos: int = 5) -> list:
    """Dado un OBJETIVO y los archivos del proyecto, el agente decide cuáles tocar.
    Esto es lo que lo hace AGENTE y no herramienta: no necesitás señalarle el archivo."""
    if not archivos_abs:
        return []
    if len(archivos_abs) == 1:
        return archivos_abs
    if not cerebro.disponible():
        return []
    catalogo = []
    for a in archivos_abs:
        try:
            head = Path(a).read_text(encoding="utf-8", errors="ignore")[:500]
        except Exception:
            head = ""
        catalogo.append(f"### {Path(a).name}\n{head}")
    sistema = (
        "Te doy un OBJETIVO y los archivos de un proyecto (con su inicio). Decidís qué "
        "archivos hay que MODIFICAR para cumplirlo. Respondé SOLO con los nombres de archivo "
        "separados por coma — sin rutas, sin explicaciones. Incluí todos los que haga falta tocar."
    )
    prompt = f"OBJETIVO: {mision}\n\nARCHIVOS DEL PROYECTO:\n" + "\n\n".join(catalogo)
    resp = cerebro.pensar_codigo(prompt, sistema)
    if not resp:
        return []
    pedidos = [n.strip().strip("`\"'") for n in re.split(r"[,\n]", resp) if n.strip()]
    por_nombre = {Path(a).name: a for a in archivos_abs}
    elegidos = []
    for p in pedidos:
        nombre = Path(p).name
        if nombre in por_nombre and por_nombre[nombre] not in elegidos:
            elegidos.append(por_nombre[nombre])
    # fallback: si vino con prosa, buscar nombres de archivo conocidos en todo el texto
    if not elegidos:
        for nombre, ruta in por_nombre.items():
            if re.search(r"\b" + re.escape(nombre) + r"\b", resp) and ruta not in elegidos:
                elegidos.append(ruta)
    return elegidos[:max_archivos]