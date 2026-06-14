"""
nucleo/habilidades/analisis/inspectores.py
Inspectores estilo DevTools sobre HTML estático + cabeceras HTTP.
Cubren, hasta donde llega un análisis SIN ejecutar JavaScript:
  · red          → recursos declarados + dominios externos contactados (Network)
  · sources      → librerías/versiones, trackers, 1ra vs 3ra parte (Sources)
  · dom          → estructura, semántica, meta/OG, accesibilidad, JSON-LD (Elements)
  · seguridad    → headers de seguridad, cookies y sus flags (Security)
  · performance  → recursos bloqueantes, async/defer, peso, hints (Performance)

Todo es OBSERVABLE. No ejecuta nada ni sondea endpoints.
"""
import re
from urllib.parse import urlparse

# ── Catálogos ────────────────────────────────────────────────────────────────
_TRACKERS = {
    "google-analytics.com": "Google Analytics", "googletagmanager.com": "Google Tag Manager",
    "doubleclick.net": "Google Ads", "facebook.net": "Meta Pixel", "connect.facebook": "Meta",
    "hotjar.com": "Hotjar", "segment.com": "Segment", "segment.io": "Segment",
    "mixpanel.com": "Mixpanel", "fullstory.com": "FullStory", "clarity.ms": "Microsoft Clarity",
    "sentry.io": "Sentry", "cloudflareinsights.com": "Cloudflare Insights",
    "amplitude.com": "Amplitude", "intercom.io": "Intercom", "newrelic.com": "New Relic",
    "optimizely.com": "Optimizely", "tiktok.com": "TikTok Pixel", "bugsnag.com": "Bugsnag",
}
_TRACKER_INLINE = {
    "gtag(": "Google gtag", "fbq(": "Meta Pixel", "_gaq": "Google Analytics (legacy)",
    "dataLayer": "GTM dataLayer", "hj(": "Hotjar", "mixpanel.": "Mixpanel",
    "analytics.track": "Segment", "clarity(": "Microsoft Clarity",
}
_LIBS = [
    ("jQuery",     r"jquery[.\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("React",      r"react(?:-dom)?[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("Vue",        r"vue[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("Angular",    r"angular[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("Bootstrap",  r"bootstrap[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("Lodash",     r"lodash[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("D3",         r"\bd3[.@\-]?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("Three.js",   r"three[.@\-]?(?:module\.)?v?(\d+\.\d+(?:\.\d+)?)?"),
    ("GSAP",       r"gsap"),
    ("Swiper",     r"swiper"),
    ("Axios",      r"axios"),
    ("Alpine.js",  r"alpine(?:js)?"),
]
_SEC_HEADERS = {
    "content-security-policy": "CSP",
    "strict-transport-security": "HSTS",
    "x-frame-options": "X-Frame-Options",
    "x-content-type-options": "X-Content-Type-Options",
    "referrer-policy": "Referrer-Policy",
    "permissions-policy": "Permissions-Policy",
    "cross-origin-opener-policy": "COOP",
}


def _host(u):
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""


def _host_de(src, base):
    if not src:
        return base
    if src.startswith("//"):
        return src[2:].split("/")[0].lower()
    if src.startswith("http"):
        return _host(src)
    return base  # relativo = primera parte


# ── Network: recursos declarados + dominios ───────────────────────────────────
def red(soup, url):
    base = _host(url) if url else ""
    scripts = [s.get("src") for s in soup.find_all("script", src=True)]
    estilos = [l.get("href") for l in soup.find_all("link", rel="stylesheet")]
    imgs = soup.find_all("img")
    iframes = [f.get("src") for f in soup.find_all("iframe", src=True)]
    fuentes = [l.get("href") for l in soup.find_all("link")
               if (l.get("as") == "font") or re.search(r"\.(woff2?|ttf|otf)", l.get("href") or "")]

    hints = {h: len(soup.find_all("link", rel=h)) for h in ("preconnect", "dns-prefetch", "preload", "prefetch")}

    dominios = {}
    for src in scripts + estilos + iframes + [i.get("src") for i in imgs]:
        if not src:
            continue
        h = _host_de(src, base)
        if h and h != base:
            dominios[h] = dominios.get(h, 0) + 1

    return {
        "scripts_externos": len([s for s in scripts if s]),
        "stylesheets": len(estilos),
        "imagenes": len(imgs),
        "fuentes": len(fuentes),
        "iframes": len(iframes),
        "hints": {k: v for k, v in hints.items() if v},
        "dominios_externos": sorted(dominios, key=lambda d: -dominios[d])[:20],
        "total_recursos": len([s for s in scripts if s]) + len(estilos) + len(imgs) + len(iframes),
    }


# ── Sources: librerías, versiones, trackers, 1ra vs 3ra parte ─────────────────
def sources(soup, url, html_bajo):
    base = _host(url) if url else ""
    srcs = [s.get("src") for s in soup.find_all("script", src=True) if s.get("src")]
    primera = sum(1 for s in srcs if _host_de(s, base) == base)
    terceros = len(srcs) - primera
    inline = soup.find_all("script", src=False)

    libs = {}
    blob = " ".join(srcs).lower()
    for nombre, pat in _LIBS:
        m = re.search(pat, blob, re.I)
        if m:
            libs[nombre] = (m.group(1) if m.lastindex else None)

    trackers = set()
    for h, nombre in _TRACKERS.items():
        if h in blob or h in html_bajo:
            trackers.add(nombre)
    for firma, nombre in _TRACKER_INLINE.items():
        if firma.lower() in html_bajo:
            trackers.add(nombre)

    sourcemaps = "sourcemappingurl" in html_bajo or any(".map" in (s or "") for s in srcs)

    return {
        "scripts_primera_parte": primera,
        "scripts_terceros": terceros,
        "inline_scripts": len(inline),
        "librerias": [f"{n} {v}" if v else n for n, v in libs.items()],
        "trackers": sorted(trackers),
        "sourcemaps": sourcemaps,
    }


# ── Elements: estructura, semántica, meta/OG, a11y, JSON-LD ───────────────────
def dom(soup):
    def _meta(name, attr="name"):
        t = soup.find("meta", attrs={attr: name})
        return (t.get("content") or "").strip() if t else ""

    html_tag = soup.find("html")
    landmarks = {n: bool(soup.find(n)) for n in ("header", "nav", "main", "aside", "footer")}

    # accesibilidad rápida
    imgs = soup.find_all("img")
    sin_alt = sum(1 for i in imgs if not i.get("alt"))

    # JSON-LD (schema.org)
    tipos_ld = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        for m in re.findall(r'"@type"\s*:\s*"([^"]+)"', s.string or ""):
            tipos_ld.append(m)

    # profundidad de anidamiento (best-effort, acotado)
    def _prof(tag, d=0):
        hijos = [c for c in getattr(tag, "children", []) if getattr(c, "name", None)]
        return d if not hijos else max(_prof(c, d + 1) for c in hijos[:60])

    return {
        "lang": (html_tag.get("lang") if html_tag else "") or "",
        "charset": (soup.find("meta", charset=True) or {}).get("charset", "") if soup.find("meta", charset=True) else "",
        "viewport": _meta("viewport"),
        "canonical": (soup.find("link", rel="canonical") or {}).get("href", "") if soup.find("link", rel="canonical") else "",
        "robots": _meta("robots"),
        "og": {k: _meta(f"og:{k}", "property") for k in ("title", "type", "image") if _meta(f"og:{k}", "property")},
        "twitter_card": _meta("twitter:card"),
        "headings": {f"h{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)},
        "landmarks": {k: v for k, v in landmarks.items() if v},
        "total_elementos": len(soup.find_all(True)),
        "profundidad_max": _prof(soup),
        "imagenes_sin_alt": sin_alt,
        "json_ld": sorted(set(tipos_ld)),
    }


# ── Security: headers + cookies ───────────────────────────────────────────────
def seguridad(headers, set_cookies, url, soup):
    https = bool(url and url.lower().startswith("https://"))
    headers = headers or {}
    presentes, faltantes = {}, []
    for clave, nombre in _SEC_HEADERS.items():
        if clave in headers:
            presentes[nombre] = headers[clave][:80]
        else:
            faltantes.append(nombre)

    # CSP también puede venir por meta http-equiv
    meta_csp = soup.find("meta", attrs={"http-equiv": re.compile("content-security-policy", re.I)})
    if meta_csp and "CSP" in faltantes:
        presentes["CSP (meta)"] = (meta_csp.get("content") or "")[:80]
        faltantes.remove("CSP")

    cookies = []
    for c in (set_cookies or []):
        nombre = c.split("=", 1)[0].strip()
        low = c.lower()
        ss = re.search(r"samesite=(\w+)", low)
        cookies.append({
            "nombre": nombre,
            "httponly": "httponly" in low,
            "secure": "secure" in low,
            "samesite": ss.group(1) if ss else "—",
        })

    return {
        "https": https,
        "headers_presentes": presentes,
        "headers_faltantes": faltantes,
        "cookies": cookies[:12],
        "sin_cabeceras": headers == {},
    }


# ── Performance: heurísticas estáticas (Lighthouse-lite) ──────────────────────
def performance(soup, html):
    head = soup.find("head")
    scripts = soup.find_all("script", src=True)
    bloqueantes = 0
    asincronos = diferidos = 0
    for s in scripts:
        es_async = s.has_attr("async")
        es_defer = s.has_attr("defer")
        if es_async:
            asincronos += 1
        if es_defer:
            diferidos += 1
        # bloqueante = en <head>, sin async/defer
        if head and s in head.find_all("script", src=True) and not (es_async or es_defer):
            bloqueantes += 1
    css = len(soup.find_all("link", rel="stylesheet"))
    html_kb = round(len(html.encode("utf-8", errors="ignore")) / 1024, 1)
    lazy = bool(soup.find("img", attrs={"loading": "lazy"}))
    hints = soup.find_all("link", rel=re.compile("preconnect|dns-prefetch|preload", re.I))

    atencion = []
    if bloqueantes:
        atencion.append(f"{bloqueantes} script(s) síncrono(s) en <head> bloquean el render")
    if css > 6:
        atencion.append(f"{css} hojas de estilo (todas bloquean el primer pintado)")
    if html_kb > 500:
        atencion.append(f"HTML pesado: {html_kb} KB")
    if not soup.find("meta", attrs={"name": "viewport"}):
        atencion.append("Sin meta viewport (mala señal mobile)")
    if not hints:
        atencion.append("Sin preconnect/preload (oportunidad de optimización)")

    return {
        "html_kb": html_kb,
        "scripts_total": len(scripts),
        "scripts_bloqueantes": bloqueantes,
        "scripts_async": asincronos,
        "scripts_defer": diferidos,
        "stylesheets": css,
        "lazy_loading": lazy,
        "resource_hints": len(hints),
        "atencion": atencion,
    }