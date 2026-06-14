"""
nucleo/habilidades/analisis/extractor_web.py
Trae una URL (requests o urllib) o parsea HTML pegado y arma HECHOS estructurados
estilo DevTools + Ola 1: infra/TLS, privacidad, SEO, a11y, diseño, PWA, CVE, y
(solo si el usuario declara que el objetivo es PROPIO) seguridad avanzada.

El alcance (incluir/excluir secciones) se aplica al armar el reporte.
"""
import re

try:
    from bs4 import BeautifulSoup
    _BS = True
except Exception:
    _BS = False
try:
    import requests
    _REQ = True
except Exception:
    _REQ = False
import urllib.request

from . import inspectores, inspectores_max, cve

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_TECH = {
    "React": ("react", "__next_data__", "data-reactroot", "_next/static"),
    "Next.js": ("__next_data__", "_next/static", "/_next/"),
    "Vue": ("vue.js", "vue.min.js", "data-v-", "__vue__", "nuxt"),
    "Angular": ("ng-version", "angular", "zone.js"),
    "Svelte": ("svelte", "__svelte"), "jQuery": ("jquery",),
    "Bootstrap": ("bootstrap.min.css", "bootstrap.css", "navbar"),
    "Tailwind": ("tailwind", "tw-"), "WordPress": ("wp-content", "wp-includes", "wp-json"),
}
_ENDPOINT_PATS = [
    re.compile(r"""fetch\(\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""axios\.\w+\(\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""\.open\(\s*['"][A-Z]+['"]\s*,\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""url\s*:\s*['"]([^'"]+)['"]""", re.I),
]


def _traer(url, timeout):
    if _REQ:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
        h = {k.lower(): v for k, v in r.headers.items()}
        try:
            cookies = r.raw.headers.get_all("Set-Cookie") or []
        except Exception:
            cookies = [r.headers["Set-Cookie"]] if "Set-Cookie" in r.headers else []
        return r.text, r.status_code, h, cookies
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(); enc = resp.headers.get_content_charset() or "utf-8"
        h = {k.lower(): v for k, v in resp.headers.items()}
        return raw.decode(enc, errors="replace"), resp.status, h, (resp.headers.get_all("Set-Cookie") or [])


def _traer_texto(url, timeout=8):
    try:
        return _traer(url, timeout)[0]
    except Exception:
        return None


def _status(url, timeout=8):
    try:
        if _REQ:
            return requests.get(url, timeout=timeout, headers={"User-Agent": _UA},
                                allow_redirects=False).status_code
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except Exception as e:
        return getattr(e, "code", None)


def _en_alcance(seccion, incluir, excluir):
    if incluir:
        return seccion in incluir
    return seccion not in (excluir or set())


def desde_url(url, timeout=12, propio=False, incluir=None, excluir=None):
    incluir, excluir = incluir or set(), excluir or set()
    try:
        html, status, headers, cookies = _traer(url, timeout)
    except Exception as e:
        codigo = getattr(e, "code", None)
        extra = f" (HTTP {codigo})" if codigo else ""
        return {"ok": False, "error": f"No pude traer la página{extra}: {e}", "url": url}

    h = desde_html(html, url=url, headers=headers, set_cookies=cookies)
    h["http"] = {"status": status, "servidor": headers.get("server", ""),
                 "content_type": headers.get("content-type", ""),
                 "content_encoding": headers.get("content-encoding", ""),
                 "cache_control": headers.get("cache-control", "")}

    # Infra (TLS + CDN/WAF)
    if _en_alcance("infra", incluir, excluir):
        h["infra"] = inspectores_max.infra(url, headers)
    # SEO + robots/sitemap
    if _en_alcance("seo", incluir, excluir):
        h["seo"] = inspectores_max.seo(BeautifulSoup(html or "", "html.parser"), url, _traer_texto)
    # CVE (parte de seguridad)
    if _en_alcance("seguridad", incluir, excluir):
        h["cve"] = cve.revisar((h.get("sources") or {}).get("librerias", []))
    # Seguridad avanzada — SOLO objetivo propio
    if propio and _en_alcance("seguridad", incluir, excluir):
        h["seguridad_avanzada"] = inspectores_max.seguridad_avanzada(url, _status)
    h["_propio"] = propio
    return h


def desde_html(html, url=None, headers=None, set_cookies=None):
    if not _BS:
        return {"ok": False, "error": "beautifulsoup4 no está instalado (pip install beautifulsoup4)."}
    soup = BeautifulSoup(html or "", "html.parser")
    bajo = (html or "").lower()

    titulo = (soup.title.string.strip() if soup.title and soup.title.string else "")
    desc_tag = soup.find("meta", attrs={"name": "description"})
    descripcion = (desc_tag.get("content") or "").strip() if desc_tag else ""
    tecnologias = sorted({n for n, fs in _TECH.items() if any(f in bajo for f in fs)})

    formularios = []
    for f in soup.find_all("form"):
        campos, tiene_pass = [], False
        for inp in f.find_all(["input", "select", "textarea"]):
            tipo = (inp.get("type") or inp.name or "text").lower()
            if tipo == "password": tiene_pass = True
            if tipo not in ("hidden", "submit", "button"):
                campos.append({"name": inp.get("name") or inp.get("id") or "", "type": tipo})
        formularios.append({"action": f.get("action") or "(misma página)",
                            "method": (f.get("method") or "get").upper(), "campos": campos[:12],
                            "es_login": tiene_pass,
                            "tiene_csrf_visible": bool(f.find("input", attrs={"name": re.compile("csrf|token", re.I)}))})

    endpoints = set()
    for sc in soup.find_all("script"):
        for pat in _ENDPOINT_PATS:
            for m in pat.findall(sc.string or ""):
                if m and not m.startswith("data:"): endpoints.add(m)
        if "/api" in (sc.get("src") or "").lower(): endpoints.add(sc.get("src"))

    return {
        "ok": True, "url": url, "titulo": titulo, "descripcion": descripcion,
        "tecnologias": tecnologias, "formularios": formularios,
        "endpoints": sorted(endpoints)[:25],
        "red": inspectores.red(soup, url),
        "sources": inspectores.sources(soup, url, bajo),
        "dom": inspectores.dom(soup),
        "seguridad": inspectores.seguridad(headers, set_cookies, url, soup),
        "performance": inspectores.performance(soup, html or ""),
        "privacidad": inspectores_max.privacidad(soup, bajo, formularios),
        "a11y": inspectores_max.a11y(soup),
        "diseno": inspectores_max.diseno(soup, html or "", bajo),
        "pwa": inspectores_max.pwa(soup),
    }


def como_texto(h, incluir=None, excluir=None):
    if not h.get("ok"):
        return h.get("error", "sin datos")
    incluir, excluir = incluir or set(), excluir or set()
    def ok(sec): return _en_alcance(sec, incluir, excluir)
    L = []

    # Identidad (siempre)
    if h.get("titulo"):      L.append(f"Título: {h['titulo']}")
    if h.get("descripcion"): L.append(f"Descripción: {h['descripcion'][:160]}")
    http = h.get("http", {})
    if http:
        linea = f"HTTP {http.get('status')} · {'HTTPS' if h.get('seguridad',{}).get('https') else 'HTTP plano'}"
        if http.get("servidor"):         linea += f" · servidor {http['servidor']}"
        if http.get("content_encoding"): linea += f" · {http['content_encoding']}"
        L.append(linea)
    if ok("sources") and h.get("tecnologias"):
        L.append("Tecnologías: " + ", ".join(h["tecnologias"]))

    # Infra
    i = h.get("infra", {})
    if ok("infra") and i:
        partes = []
        if i.get("cdn_waf"):       partes.append("CDN/WAF: " + ", ".join(i["cdn_waf"]))
        if i.get("tls_version"):   partes.append(f"TLS {i['tls_version']}")
        if i.get("cert_emisor"):   partes.append(f"cert: {i['cert_emisor']}")
        if i.get("cert_validez"):  partes.append(f"vence {i['cert_validez']}")
        if partes: L.append("\n[INFRA] " + " · ".join(partes))

    # Elements
    d = h.get("dom", {})
    if ok("dom") and d:
        hs = d.get("headings", {})
        outline = ", ".join(f"{k}:{v}" for k, v in hs.items() if v) or "sin headings"
        L.append(f"\n[ELEMENTS] {d.get('total_elementos',0)} elementos, prof {d.get('profundidad_max',0)} · {outline}")
        if d.get("landmarks"): L.append("  Semántica: " + ", ".join(d["landmarks"].keys()))

    # Network
    r = h.get("red", {})
    if ok("red") and r:
        L.append(f"\n[NETWORK] {r.get('total_recursos',0)} recursos · {r.get('scripts_externos',0)} scripts, "
                 f"{r.get('stylesheets',0)} css, {r.get('imagenes',0)} img, {r.get('fuentes',0)} fuentes")
        if r.get("dominios_externos"): L.append("  Dominios externos: " + ", ".join(r["dominios_externos"]))

    # Sources
    s = h.get("sources", {})
    if ok("sources") and s:
        L.append(f"\n[SOURCES] {s.get('scripts_primera_parte',0)} 1ra parte / {s.get('scripts_terceros',0)} terceros · "
                 f"{s.get('inline_scripts',0)} inline" + (" · sourcemaps expuestos" if s.get("sourcemaps") else ""))
        if s.get("librerias"): L.append("  Librerías: " + ", ".join(s["librerias"]))
        if s.get("trackers"):  L.append("  Trackers: " + ", ".join(s["trackers"]))

    # Diseño
    ds = h.get("diseno", {})
    if ok("diseno") and ds:
        L.append("\n[DISEÑO]")
        if ds.get("design_system"): L.append("  Design system: " + ", ".join(ds["design_system"]))
        if ds.get("paleta_colores"): L.append("  Paleta: " + ", ".join(ds["paleta_colores"]))
        if ds.get("tipografias"):   L.append("  Tipografías: " + ", ".join(ds["tipografias"]))
        if ds.get("breakpoints_px"): L.append("  Breakpoints: " + ", ".join(f"{b}px" for b in ds["breakpoints_px"]))
        L.append(f"  Dark mode: {'sí' if ds.get('dark_mode') else 'no'}"
                 + (" · Componentes: " + ", ".join(f"{k}×{v}" for k, v in ds.get("componentes", {}).items()) if ds.get("componentes") else ""))

    # Privacidad
    pr = h.get("privacidad", {})
    if ok("privacidad") and pr:
        L.append("\n[PRIVACIDAD]")
        L.append(f"  Banner de consentimiento: {', '.join(pr['cmp']) if pr['cmp'] else 'no detectado'}")
        if pr.get("pixels_publicitarios"): L.append("  Pixels publicitarios: " + ", ".join(pr["pixels_publicitarios"]))
        if pr.get("pii_solicitada"):       L.append("  Datos personales que pide: " + ", ".join(pr["pii_solicitada"]))
        if pr.get("links_legales"):        L.append(f"  Links legales: {len(pr['links_legales'])} encontrado(s)")

    # Accesibilidad
    a = h.get("a11y", {})
    if ok("a11y") and a:
        L.append(f"\n[ACCESIBILIDAD] score ~{a.get('score_estimado','?')}/100 · idioma {a.get('idioma_declarado','—')} · "
                 f"{a.get('aria_roles',0)} roles ARIA")
        for p in a.get("problemas", []): L.append(f"  ⚠ {p}")

    # SEO
    se = h.get("seo", {})
    if ok("seo") and se:
        L.append("\n[SEO]")
        if se.get("idiomas_hreflang"): L.append("  Idiomas (hreflang): " + ", ".join(se["idiomas_hreflang"]))
        if se.get("json_ld_tipos"):    L.append("  Datos estructurados: " + ", ".join(se["json_ld_tipos"]))
        for p in se.get("problemas_seo", []): L.append(f"  ⚠ {p}")
        rb = se.get("robots", {})
        if rb.get("existe"):
            L.append(f"  robots.txt: {rb.get('rutas_bloqueadas',0)} rutas bloqueadas"
                     + (f", sitemap: {', '.join(rb['sitemaps'])}" if rb.get("sitemaps") else ""))
        elif "robots" in se:
            L.append("  robots.txt: no existe")

    # PWA
    pw = h.get("pwa", {})
    if ok("pwa") and pw and (pw.get("manifest") or pw.get("service_worker_declarado")):
        L.append(f"\n[PWA] manifest: {'sí' if pw['manifest'] else 'no'} · "
                 f"service worker: {'sí' if pw['service_worker_declarado'] else 'no'} · "
                 f"instalable: {'sí' if pw['instalable_pwa'] else 'no'}")

    # Security
    seg = h.get("seguridad", {})
    if ok("seguridad") and seg and not seg.get("sin_cabeceras"):
        L.append("\n[SECURITY]")
        if seg.get("headers_presentes"): L.append("  Headers presentes: " + ", ".join(seg["headers_presentes"].keys()))
        if seg.get("headers_faltantes"): L.append("  Headers ausentes: " + ", ".join(seg["headers_faltantes"]))
        for c in seg.get("cookies", []):
            flags = [f for f, on in (("HttpOnly", c["httponly"]), ("Secure", c["secure"])) if on]
            flags.append(f"SameSite={c['samesite']}")
            L.append(f"  Cookie {c['nombre']}: " + ", ".join(flags))
        if h.get("cve"):
            L.append("  CVE de librerías:")
            L.append(cve.como_texto(h["cve"]))
    elif ok("seguridad") and seg.get("sin_cabeceras"):
        L.append("\n[SECURITY] (HTML pegado, sin cabeceras HTTP)")

    # Seguridad avanzada (objetivo propio)
    sa = h.get("seguridad_avanzada")
    if sa:
        L.append(f"\n[SEGURIDAD AVANZADA — objetivo propio] {sa['rutas_chequeadas']} rutas sensibles chequeadas")
        if sa["hallazgos"]:
            for hh in sa["hallazgos"]:
                L.append(f"  ⚠ {hh['ruta']} → HTTP {hh['status']} ({hh['nivel']})")
        else:
            L.append("  ✓ ninguna ruta sensible expuesta")

    # Performance
    p = h.get("performance", {})
    if ok("performance") and p:
        L.append(f"\n[PERFORMANCE] HTML {p.get('html_kb',0)} KB · {p.get('scripts_total',0)} scripts "
                 f"({p.get('scripts_async',0)} async, {p.get('scripts_defer',0)} defer, "
                 f"{p.get('scripts_bloqueantes',0)} bloqueantes) · {p.get('stylesheets',0)} css")
        for at in p.get("atencion", []): L.append(f"  ⚠ {at}")

    # Forms + Endpoints
    for n, f in enumerate(h.get("formularios", []), 1):
        if not ok("seguridad") and not ok("red"): break
        tipo = "LOGIN" if f["es_login"] else "form"
        campos = ", ".join(f"{c['name'] or '?'}:{c['type']}" for c in f["campos"]) or "(sin campos)"
        L.append(f"\n[FORM {n}] {tipo} {f['method']} → {f['action']} · {campos}"
                 + (" · CSRF visible" if f["tiene_csrf_visible"] else ""))
    if ok("sources") and h.get("endpoints"):
        L.append("\n[ENDPOINTS inline] " + ", ".join(h["endpoints"]))

    return "\n".join(L)