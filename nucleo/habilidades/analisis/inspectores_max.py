"""
nucleo/habilidades/analisis/inspectores_max.py
Inspectores extendidos (Ola 1 — web máximo). Todo OBSERVABLE/PASIVO salvo
`seguridad_avanzada`, que sondea rutas sensibles y SOLO debe llamarse en modo
"objetivo propio" (autorizado por el usuario).

Dominios:
  infra        → TLS/certificado, CDN/WAF, redirects (red real, pasivo)
  privacidad   → cookies de 3ros, CMP, pixels, PII en formularios, links legales
  seo          → robots/sitemap, hreflang, canonical, JSON-LD, outline headings
  a11y         → labels, ARIA, idioma/dirección, alt, skip-links (score)
  diseno       → colores, tipografías, design system, dark mode, breakpoints, componentes
  pwa          → manifest, service worker, theme-color, instalabilidad
  seguridad_avanzada → rutas sensibles, métodos HTTP (SOLO objetivo propio)
"""
import re
import ssl
import socket
from urllib.parse import urlparse

try:
    import requests
    _REQ = True
except Exception:
    _REQ = False
import urllib.request

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ── INFRA: TLS + CDN/WAF ──────────────────────────────────────────────────────
_CDN_WAF = {
    "cloudflare": "Cloudflare", "cf-ray": "Cloudflare", "x-amz": "AWS",
    "x-vercel": "Vercel", "x-served-by": "Fastly/Varnish", "x-akamai": "Akamai",
    "x-azure": "Azure", "x-fastly": "Fastly", "x-github": "GitHub Pages",
}


def infra(url, headers):
    headers = headers or {}
    info = {}
    p = urlparse(url or "")
    host = p.netloc.split(":")[0]

    # CDN / WAF por cabeceras
    blob = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    cdn = sorted({nombre for firma, nombre in _CDN_WAF.items() if firma in blob})
    if "server" in headers:
        info["servidor"] = headers["server"]
    if cdn:
        info["cdn_waf"] = cdn

    # Certificado TLS (solo https)
    if p.scheme == "https" and host:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=8) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ss:
                    cert = ss.getpeercert()
                    info["tls_version"] = ss.version()
                    emisor = dict(x[0] for x in cert.get("issuer", []))
                    info["cert_emisor"] = emisor.get("organizationName", emisor.get("commonName", ""))
                    info["cert_validez"] = cert.get("notAfter", "")
                    sans = [v for (t, v) in cert.get("subjectAltName", []) if t == "DNS"]
                    info["cert_sans"] = sans[:6]
        except Exception as e:
            info["tls_error"] = str(e)[:80]
    return info


# ── PRIVACIDAD ────────────────────────────────────────────────────────────────
_CMP = {"onetrust": "OneTrust", "cookiebot": "Cookiebot", "cookieyes": "CookieYes",
        "didomi": "Didomi", "quantcast": "Quantcast", "usercentrics": "Usercentrics",
        "iubenda": "Iubenda", "cookie-consent": "consent banner genérico"}
_PIXELS = {"facebook.net": "Meta Pixel", "fbevents": "Meta Pixel", "doubleclick": "Google Ads",
           "tiktok": "TikTok Pixel", "snap.licdn": "LinkedIn Insight", "ads-twitter": "Twitter Ads",
           "bat.bing": "Microsoft Ads"}
_PII = {"email": "email", "e-mail": "email", "correo": "email", "tel": "teléfono",
        "phone": "teléfono", "celular": "teléfono", "card": "tarjeta", "tarjeta": "tarjeta",
        "cvv": "tarjeta", "ssn": "documento", "dni": "documento", "cedula": "documento",
        "address": "dirección", "direccion": "dirección"}


def privacidad(soup, html_bajo, formularios):
    cmp_ = sorted({nombre for firma, nombre in _CMP.items() if firma in html_bajo})
    pixels = sorted({nombre for firma, nombre in _PIXELS.items() if firma in html_bajo})

    # PII que piden los formularios
    pii = set()
    for f in formularios or []:
        for c in f.get("campos", []):
            etiqueta = (c.get("name", "") + " " + c.get("type", "")).lower()
            for firma, tipo in _PII.items():
                if firma in etiqueta:
                    pii.add(tipo)

    # links legales
    legales = []
    for a in soup.find_all("a", href=True):
        t = (a.get_text() or "").lower() + " " + a["href"].lower()
        if any(k in t for k in ("privac", "cookie", "terms", "términos", "terminos", "legal")):
            legales.append(a["href"])

    return {
        "cmp": cmp_,
        "pixels_publicitarios": pixels,
        "pii_solicitada": sorted(pii),
        "links_legales": sorted(set(legales))[:5],
        "tiene_banner_consentimiento": bool(cmp_),
    }


# ── SEO + estructura de sitio ─────────────────────────────────────────────────
def seo(soup, url, fetch_fn):
    out = {}
    # hreflang / idiomas
    hreflang = [l.get("hreflang") for l in soup.find_all("link", rel="alternate") if l.get("hreflang")]
    if hreflang:
        out["idiomas_hreflang"] = sorted(set(hreflang))[:12]

    # JSON-LD detallado
    tipos = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        tipos += re.findall(r'"@type"\s*:\s*"([^"]+)"', s.string or "")
    if tipos:
        out["json_ld_tipos"] = sorted(set(tipos))

    # outline de headings (problemas comunes)
    h1 = soup.find_all("h1")
    problemas = []
    if len(h1) == 0: problemas.append("sin H1")
    elif len(h1) > 1: problemas.append(f"{len(h1)} H1 (debería ser 1)")
    if not soup.find("meta", attrs={"name": "description"}): problemas.append("sin meta description")
    if not soup.find("link", rel="canonical"): problemas.append("sin canonical")
    out["problemas_seo"] = problemas

    # robots.txt + sitemap (fetch aparte, pasivo)
    if url and fetch_fn:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        robots = fetch_fn(base + "/robots.txt")
        if robots:
            sitemaps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
            disallows = re.findall(r"(?im)^disallow:\s*(\S+)", robots)
            out["robots"] = {"existe": True, "sitemaps": sitemaps[:3],
                             "rutas_bloqueadas": len(disallows), "ejemplos_bloqueados": disallows[:8]}
        else:
            out["robots"] = {"existe": False}
    return out


# ── ACCESIBILIDAD profunda ────────────────────────────────────────────────────
def a11y(soup):
    imgs = soup.find_all("img")
    sin_alt = sum(1 for i in imgs if not i.get("alt"))
    inputs = soup.find_all("input")
    labels_for = {l.get("for") for l in soup.find_all("label") if l.get("for")}
    sin_label = 0
    for i in inputs:
        if (i.get("type") or "").lower() in ("hidden", "submit", "button"):
            continue
        if not (i.get("id") in labels_for or i.get("aria-label") or i.get("aria-labelledby")):
            sin_label += 1
    botones_vacios = sum(1 for b in soup.find_all("button")
                         if not (b.get_text(strip=True) or b.get("aria-label")))
    aria_roles = len(soup.find_all(attrs={"role": True}))
    html_tag = soup.find("html")

    problemas = []
    if sin_alt: problemas.append(f"{sin_alt} imagen(es) sin alt")
    if sin_label: problemas.append(f"{sin_label} input(s) sin label/aria")
    if botones_vacios: problemas.append(f"{botones_vacios} botón(es) sin texto accesible")
    if not (html_tag and html_tag.get("lang")): problemas.append("sin atributo lang en <html>")
    if not soup.find("a", href=re.compile("#(content|main|skip)", re.I)): problemas.append("sin skip-link")

    total = (len(imgs)
             + len([i for i in inputs if (i.get("type") or "").lower() not in ("hidden", "submit", "button")])
             + len(soup.find_all("button")))
    fallos = sin_alt + sin_label + botones_vacios
    score = max(0, round(100 * (1 - fallos / max(total, 1))))
    return {"score_estimado": score, "aria_roles": aria_roles,
            "idioma_declarado": (html_tag.get("lang") if html_tag else "") or "—",
            "problemas": problemas}


# ── DISEÑO (declarado) ────────────────────────────────────────────────────────
_DESIGN_SYS = {"tailwind": "Tailwind", "bootstrap": "Bootstrap", "bulma": "Bulma",
               "material": "Material UI", "antd": "Ant Design", "chakra": "Chakra UI",
               "foundation": "Foundation", "semantic-ui": "Semantic UI"}
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_FONT = re.compile(r"font-family\s*:\s*([^;}\"']+)", re.I)


def diseno(soup, html, html_bajo):
    # design system
    sistema = sorted({n for f, n in _DESIGN_SYS.items() if f in html_bajo})

    # colores (de estilos inline + <style>)
    estilos = " ".join(s.string or "" for s in soup.find_all("style"))
    estilos += " ".join(t.get("style", "") for t in soup.find_all(style=True))
    colores = sorted(set(m.group(0).lower() for m in _HEX.finditer(estilos)))[:12]

    # tipografías
    fuentes = set()
    for m in _FONT.finditer(estilos):
        primera = m.group(1).split(",")[0].strip().strip("\"'")
        if primera and len(primera) < 40:
            fuentes.add(primera)
    # web fonts cargadas (Google Fonts, etc.)
    for l in soup.find_all("link", href=True):
        if "fonts.googleapis" in l["href"] or "fonts.gstatic" in l["href"]:
            fuentes.add("Google Fonts")
        if re.search(r"\.(woff2?|ttf|otf)", l["href"]):
            fuentes.add("web font propia")

    # dark mode, responsive
    dark = "prefers-color-scheme" in html_bajo
    breakpoints = sorted(set(re.findall(r"@media[^{]*?(\d{3,4})px", estilos)))[:8]

    # inventario simple de componentes
    componentes = {
        "botones": len(soup.find_all("button")) + len(soup.find_all("a", class_=re.compile("btn|button", re.I))),
        "cards": len(soup.find_all(class_=re.compile(r"\bcard\b", re.I))),
        "navs": len(soup.find_all("nav")),
        "modales": len(soup.find_all(class_=re.compile("modal|dialog", re.I))),
        "formularios": len(soup.find_all("form")),
    }
    return {
        "design_system": sistema,
        "paleta_colores": colores,
        "tipografias": sorted(fuentes)[:8],
        "dark_mode": dark,
        "breakpoints_px": breakpoints,
        "componentes": {k: v for k, v in componentes.items() if v},
    }


# ── PWA / mobile ──────────────────────────────────────────────────────────────
def pwa(soup):
    manifest = soup.find("link", rel="manifest")
    sw = bool(re.search(r"serviceworker\.register|navigator\.serviceworker", str(soup).lower()))
    theme = soup.find("meta", attrs={"name": "theme-color"})
    apple_icon = soup.find("link", rel=re.compile("apple-touch-icon", re.I))
    instalable = bool(manifest) and bool(theme)
    return {
        "manifest": bool(manifest),
        "service_worker_declarado": sw,
        "theme_color": (theme.get("content") if theme else "") or "",
        "apple_touch_icon": bool(apple_icon),
        "instalable_pwa": instalable,
    }


# ── SEGURIDAD AVANZADA — SOLO objetivo propio (autorizado) ────────────────────
_RUTAS_SENSIBLES = ["/.git/config", "/.env", "/admin", "/wp-admin/", "/phpmyadmin/",
                    "/.well-known/security.txt", "/backup.zip", "/config.php", "/server-status",
                    "/.htaccess", "/debug", "/api/swagger.json", "/swagger-ui.html"]


def _existe(fetch_status_fn, base, ruta):
    try:
        code = fetch_status_fn(base + ruta)
        return code
    except Exception:
        return None


def seguridad_avanzada(url, fetch_status_fn):
    """Sondea rutas sensibles. SOLO para objetivo propio autorizado."""
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    hallazgos = []
    for ruta in _RUTAS_SENSIBLES:
        code = _existe(fetch_status_fn, base, ruta)
        if code and code < 400:
            hallazgos.append({"ruta": ruta, "status": code, "nivel": "expuesto"})
        elif code in (401, 403):
            hallazgos.append({"ruta": ruta, "status": code, "nivel": "protegido (existe)"})
    return {"rutas_chequeadas": len(_RUTAS_SENSIBLES), "hallazgos": hallazgos}