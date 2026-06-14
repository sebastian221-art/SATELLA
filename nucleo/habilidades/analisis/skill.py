"""
nucleo/habilidades/analisis/skill.py — ANALIZADOR MÁXIMO (universal).
Rutea por TIPO:
  · web        → URL: análisis DevTools+ (infra, privacidad, SEO, a11y, diseño, PWA, CVE…)
  · html       → HTML pegado
  · paquete    → librería (spaCy, requests, react…): PyPI/npm + salud GitHub + CVE
  · conceptual → describe la clase de sistema
Respeta alcance ("solo diseño"), modo objetivo-propio (seguridad avanzada) y
guarda histórico de cada análisis.
"""
from nucleo.habilidades import contrato
from . import detector, extractor_web, explicador, almacen, paquetes, repos, codigo_multi, herramientas

NOMBRE = "analisis"
DESCRIPCION = ("Análisis máximo y universal: webs/sistemas (stack, red, sources, DOM, seguridad con "
               "headers/cookies/CVE, performance, infra/TLS, privacidad, SEO, accesibilidad, diseño, PWA) "
               "y paquetes/librerías (PyPI/npm, salud del repo, dependencias, CVE). Acepta alcance y "
               "modo objetivo-propio. Guarda histórico.")
EJEMPLOS = [
    "analizá esta web https://ejemplo.com",
    "analizá solo el diseño de https://...",
    "auditá la seguridad de https://... que es mi sitio",
    "analizá el paquete spacy",
    "analizá la librería requests",
]


def detecta(texto, codigo_adjunto=""):
    return detector.es_peticion(texto, codigo_adjunto)


def manejar(texto, contexto=None):
    t = detector.tipo(texto)
    objetivo = detector.objetivo(texto)
    incluir, excluir = detector.alcance(texto)
    propio = detector.es_objetivo_propio(texto)

    if t == "paquete":
        return _manejar_paquete(texto, objetivo)
    if t == "repo":
        return _manejar_repo(texto, objetivo)
    if t == "codigo":
        return _manejar_codigo(texto, objetivo)
    if t == "herramienta":
        return _manejar_herramienta(texto, objetivo)

    nota = ""
    if incluir:   nota = "Alcance: solo " + ", ".join(sorted(incluir)) + "."
    elif excluir: nota = "Alcance: todo menos " + ", ".join(sorted(excluir)) + "."

    reg = None
    if t == "web":
        url = detector.hay_url(texto)
        hechos = extractor_web.desde_url(url, propio=propio, incluir=incluir, excluir=excluir)
        if not hechos.get("ok"):
            cuerpo = (f"No pude acceder a {url}.\n{hechos.get('error','')}\n\n"
                      "Puede bloquear bots, requerir login o estar caído. Pegame el HTML y lo analizo igual.")
            return contrato.resultado(NOMBRE, "web", f"No pude traer {url}", cuerpo, ok=True)
        hechos_txt = extractor_web.como_texto(hechos, incluir, excluir)
        reg = almacen.guardar(url, _resumen_web(hechos), hechos)
    elif t == "html":
        hechos = extractor_web.desde_html(texto)
        hechos_txt = extractor_web.como_texto(hechos, incluir, excluir)
    else:
        hechos, hechos_txt = {"ok": True}, ""

    razonamiento = explicador.explicar(objetivo, hechos_txt, modo=t if t != "html" else "web",
                                        incluir=incluir, excluir=excluir)

    partes = []
    if nota: partes.append(nota)
    if propio and t == "web":
        partes.append("Modo OBJETIVO PROPIO activo — incluye sondeo de seguridad avanzada.")
    if hechos_txt:    partes.append("── Lo que se observa ──\n" + hechos_txt)
    if razonamiento:  partes.append("── Cómo funciona ──\n" + razonamiento)
    if reg and not reg.get("es_primero") and reg.get("cambios"):
        partes.append("── Cambios desde el último análisis ──\n" + "\n".join(f"· {c}" for c in reg["cambios"]))
    if not partes:
        partes.append("No tengo datos suficientes. Pasame una URL, el HTML o el nombre de un paquete.")

    return contrato.resultado(NOMBRE, t, _resumen_web(hechos), "\n\n".join(partes), ok=True)


def _manejar_repo(texto, objetivo):
    gh = detector.repo_github(texto)
    ruta = detector.ruta_local(texto)
    if gh and any(k in texto.lower() for k in detector._REPO_KW):
        f = repos.analizar_github(gh[0], gh[1])
    elif ruta:
        f = repos.analizar_local(ruta)
    else:
        return contrato.resultado(NOMBRE, "repo", "Sin repo",
                                  "Decime un repo (github.com/owner/repo) o una ruta local.", ok=True)
    if not f.get("ok"):
        return contrato.resultado(NOMBRE, "repo", "No accesible", f.get("error", ""), ok=True)
    hechos_txt = repos.como_texto(f)
    razonamiento = explicador.explicar(objetivo, hechos_txt, modo="web")
    partes = ["── Lo que se observa ──\n" + hechos_txt]
    if razonamiento:
        partes.append("── Cómo funciona ──\n" + razonamiento)
    return contrato.resultado(NOMBRE, "repo", _resumen_repo(f), "\n\n".join(partes), ok=True)


def _manejar_codigo(texto, objetivo):
    ruta = detector.ruta_local(texto)
    f = codigo_multi.analizar_archivo(ruta) if ruta else {"ok": False, "error": "Sin archivo."}
    if not f.get("ok"):
        return contrato.resultado(NOMBRE, "codigo", "No accesible", f.get("error", ""), ok=True)
    hechos_txt = codigo_multi.como_texto(f)
    razonamiento = explicador.explicar(objetivo, hechos_txt, modo="web")
    partes = ["── Lo que se observa ──\n" + hechos_txt]
    if razonamiento:
        partes.append("── Qué hace ──\n" + razonamiento)
    return contrato.resultado(NOMBRE, "codigo", f"Código {f.get('lenguaje','')}: {f.get('archivo','')}",
                              "\n\n".join(partes), ok=True)


def _manejar_herramienta(texto, objetivo):
    cmd = detector.comando_cli(texto)
    f = herramientas.analizar(cmd) if cmd else {"ok": False, "error": "Sin comando."}
    if not f.get("ok"):
        return contrato.resultado(NOMBRE, "herramienta", "No disponible", f.get("error", ""), ok=True)
    hechos_txt = herramientas.como_texto(f)
    razonamiento = explicador.explicar(objetivo, hechos_txt, modo="web")
    partes = ["── Lo que se observa ──\n" + hechos_txt]
    if razonamiento:
        partes.append("── Qué es y para qué sirve ──\n" + razonamiento)
    return contrato.resultado(NOMBRE, "herramienta", f"Herramienta {cmd}", "\n\n".join(partes), ok=True)


def _resumen_repo(f):
    if f.get("fuente") == "github":
        return f"Repo {f['repo']}: ⭐{f.get('estrellas','?')}, {f.get('total_archivos','?')} archivos."
    secs = len(f.get("secretos", []))
    aviso = f", ⚠{secs} secretos" if secs else ""
    return f"Proyecto local: {f['total_archivos']} archivos, {len(f.get('lenguajes',{}))} lenguajes{aviso}."


def _manejar_paquete(texto, objetivo):
    nombre = detector.nombre_paquete(texto)
    if not nombre:
        return contrato.resultado(NOMBRE, "paquete", "Sin nombre de paquete",
                                  "Decime el nombre del paquete a analizar (ej: 'analizá spacy').", ok=True)
    f = paquetes.analizar(nombre)
    if not f.get("ok"):
        return contrato.resultado(NOMBRE, "paquete", "No encontrado", f.get("error", ""), ok=True)
    hechos_txt = paquetes.como_texto(f)
    razonamiento = explicador.explicar(objetivo, hechos_txt, modo="web")
    partes = ["── Lo que se observa ──\n" + hechos_txt]
    if razonamiento:
        partes.append("── Qué significa ──\n" + razonamiento)
    return contrato.resultado(NOMBRE, "paquete", _resumen_pkg(f), "\n\n".join(partes), ok=True)


def _resumen_web(hechos):
    if not hechos.get("ok"):
        return "No se pudo acceder."
    tec = len(hechos.get("tecnologias", []))
    forms = hechos.get("formularios", [])
    seg = hechos.get("seguridad", {})
    faltan = len(seg.get("headers_faltantes", [])) if seg else 0
    cve = hechos.get("cve", {})
    vulns = sum(len(r.get("vulns", [])) for r in cve.get("resultados", [])) if cve.get("disponible") else 0
    t = []
    if tec:    t.append(f"{tec} tec")
    if forms:  t.append(f"{len(forms)} form")
    if faltan: t.append(f"{faltan} headers seg. ausentes")
    if vulns:  t.append(f"{vulns} CVE")
    return "Analizado: " + (", ".join(t) if t else "estructura básica") + "."


def _resumen_pkg(f):
    s = f.get("salud") or {}
    vulns = sum(len(r.get("vulns", [])) for r in f.get("cve", {}).get("resultados", []))
    extra = f", ⭐{s['estrellas']}" if s.get("estrellas") is not None else ""
    extra += f", {vulns} CVE" if vulns else ""
    return f"Paquete {f['nombre']} {f.get('version','')} ({f['ecosistema']}){extra}."