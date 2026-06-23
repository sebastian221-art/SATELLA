"""
nucleo/habilidades/analisis/seguridad.py — AUDITORÍA DE SEGURIDAD (modo hacker, solo análisis).
Encuentra vulnerabilidades, fragilidades y vectores de entrada — SIN atacar:
  1. Escáner determinista de patrones (built-in, sin instalar nada): SQLi, XSS,
     inyección de comandos, deserialización insegura, secretos, cripto débil, etc.
  2. Herramientas externas si están instaladas (Bandit/gitleaks) — bonus, degrada.
  3. Claude Code como PENTESTER: modela cómo un atacante encadenaría las fallas y
     prescribe la defensa en capas. Razonamiento ofensivo → producto defensivo.

NO inyecta, NO explota, NO manda tráfico de ataque. Solo lee y razona.
"""
import os
import re
import ast
import json
import shutil
import subprocess

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None


# ── 1) Escáner determinista de patrones ──────────────────────────────────────
# (regex, severidad, título, por qué es peligroso). Multi-lenguaje.
_PATRONES = [
    # Inyección de código
    (r"\beval\s*\(", "alta", "Uso de eval()",
     "Ejecuta texto como código: si entra input del usuario, es ejecución arbitraria."),
    (r"\bexec\s*\(", "alta", "Uso de exec()",
     "Ejecuta strings como código. Vector directo de inyección si el string no es 100% confiable."),
    (r"\bFunction\s*\(", "alta", "new Function() (JS)",
     "Equivalente a eval en JS: construye código desde strings."),
    # Inyección de comandos
    (r"os\.system\s*\(", "alta", "os.system()",
     "Corre comandos del SO. Si concatena input, es inyección de comandos."),
    (r"subprocess\.(?:call|run|Popen)\([^)]*shell\s*=\s*True", "alta", "subprocess con shell=True",
     "shell=True + input del usuario = inyección de comandos del SO."),
    (r"child_process\.(?:exec|execSync)\s*\(", "alta", "child_process.exec() (JS)",
     "Ejecuta comandos del SO en Node; con input concatenado, inyección."),
    # SQL injection
    (r"(?i)f[\"'][^\"']*\b(?:select|insert|update|delete)\b", "alta", "SQL en f-string",
     "Interpolar variables en un f-string de SQL = SQL injection. Usá queries parametrizadas."),
    (r"(?i)\b(?:select|insert|update|delete)\b.*\b(?:from|into|where|set)\b.*[\"']\s*(?:%|\+)", "alta", "SQL armado con % o +",
     "Concatenar/formatear SQL con variables = SQL injection. Usá placeholders (?, %s) parametrizados."),
    (r"(?i)\b(?:select|insert|update|delete)\b.*\.format\s*\(", "alta", "SQL con .format()",
     "Formatear SQL con .format() abre SQL injection. Usá queries parametrizadas."),
    # XSS
    (r"\.innerHTML\s*=", "media", "Asignación a innerHTML (JS)",
     "Escribir HTML sin sanitizar permite XSS. Usá textContent o sanitizá."),
    (r"document\.write\s*\(", "media", "document.write() (JS)",
     "Inyecta HTML directo; vector de XSS si incluye datos del usuario."),
    (r"dangerouslySetInnerHTML", "media", "dangerouslySetInnerHTML (React)",
     "Renderiza HTML crudo; XSS si el contenido no está sanitizado."),
    # Deserialización insegura
    (r"pickle\.loads?\s*\(", "alta", "pickle (deserialización insegura)",
     "Deserializar pickle no confiable ejecuta código arbitrario."),
    (r"yaml\.load\s*\((?![^)]*Loader)", "alta", "yaml.load() sin SafeLoader",
     "yaml.load sin Loader=SafeLoader puede instanciar objetos arbitrarios. Usá safe_load."),
    (r"marshal\.loads?\s*\(", "media", "marshal (deserialización)",
     "marshal sobre datos no confiables es peligroso."),
    # Cripto débil
    (r"hashlib\.(?:md5|sha1)\s*\(", "media", "Hash débil (MD5/SHA1)",
     "MD5/SHA1 están rotos para seguridad. Para contraseñas usá bcrypt/argon2."),
    (r"random\.(?:random|randint|choice)\s*\(", "baja", "random no criptográfico",
     "El módulo random no sirve para tokens/secretos. Usá secrets."),
    # TLS / verificación
    (r"verify\s*=\s*False", "alta", "verify=False (TLS desactivado)",
     "Desactiva la verificación del certificado: expone a man-in-the-middle."),
    (r"rejectUnauthorized\s*:\s*false", "alta", "rejectUnauthorized:false (Node TLS)",
     "Ignora certificados inválidos; MITM."),
    # Exposición
    (r"DEBUG\s*=\s*True", "media", "DEBUG = True",
     "Modo debug en producción filtra trazas y datos sensibles."),
    (r"app\.run\([^)]*debug\s*=\s*True", "media", "Flask debug=True",
     "El debugger de Flask permite ejecución de código si queda expuesto."),
    (r"cors.*origin.*\*|Access-Control-Allow-Origin.*\*", "baja", "CORS abierto (*)",
     "CORS con '*' permite que cualquier origen llame a tu API."),
]

# Secretos hardcodeados (claves, tokens, contraseñas)
_SECRETOS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
    (r"(?i)aws_secret_access_key\s*[=:]\s*[\"'][^\"']{20,}", "AWS Secret Key"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "Clave privada"),
    (r"(?i)(?:api[_-]?key|apikey|secret|token|password|passwd|pwd)\s*[=:]\s*[\"'][^\"'\s]{8,}[\"']", "Credencial hardcodeada"),
    (r"sk-[a-zA-Z0-9]{20,}", "API key estilo OpenAI/Stripe"),
    (r"gh[pousr]_[A-Za-z0-9]{30,}", "Token de GitHub"),
    (r"(?i)bearer\s+[a-z0-9._\-]{20,}", "Bearer token"),
]


def escanear_patrones(codigo: str) -> list:
    """Escanea el código línea por línea contra el catálogo. Sin red, sin ejecutar."""
    hallazgos = []
    if not codigo:
        return hallazgos
    lineas = codigo.splitlines()
    for i, linea in enumerate(lineas, 1):
        # comentarios obvios se saltean para bajar falsos positivos
        desnuda = linea.strip()
        for patron, sev, titulo, porque in _PATRONES:
            if re.search(patron, linea):
                hallazgos.append({"linea": i, "severidad": sev, "titulo": titulo,
                                  "porque": porque, "fragmento": desnuda[:120]})
        for patron, tipo in _SECRETOS:
            if re.search(patron, linea):
                hallazgos.append({"linea": i, "severidad": "alta", "titulo": f"Secreto expuesto: {tipo}",
                                  "porque": "Credenciales en el código se filtran al repo y a quien lo lea.",
                                  "fragmento": "(oculto por seguridad)"})
    return hallazgos


# ── 2) Herramientas externas (opcionales, degradan) ──────────────────────────
def _correr_bandit(ruta: str) -> list:
    """Bandit (SAST de Python) si está instalado. Devuelve lista de hallazgos."""
    if not shutil.which("bandit"):
        return []
    try:
        p = subprocess.run(["bandit", "-f", "json", "-q", "-r", ruta],
                           capture_output=True, text=True, timeout=120)
        data = json.loads(p.stdout or "{}")
        out = []
        for r in data.get("results", [])[:40]:
            out.append({"linea": r.get("line_number"), "severidad": (r.get("issue_severity") or "").lower(),
                        "titulo": "Bandit: " + r.get("test_name", ""),
                        "porque": r.get("issue_text", ""), "fragmento": (r.get("code") or "").strip()[:120]})
        return out
    except Exception:
        return []


def _correr_gitleaks(ruta: str) -> list:
    """gitleaks (secretos) si está instalado."""
    if not shutil.which("gitleaks"):
        return []
    try:
        p = subprocess.run(["gitleaks", "detect", "--source", ruta, "--no-banner",
                           "--report-format", "json", "--report-path", "-"],
                          capture_output=True, text=True, timeout=120)
        data = json.loads(p.stdout or "[]")
        return [{"linea": r.get("StartLine"), "severidad": "alta",
                 "titulo": "gitleaks: " + r.get("RuleID", "secreto"),
                 "porque": r.get("Description", ""), "fragmento": "(oculto)"} for r in data[:40]]
    except Exception:
        return []


def herramientas_disponibles() -> dict:
    return {"bandit": bool(shutil.which("bandit")), "gitleaks": bool(shutil.which("gitleaks"))}


# ── 3) Claude Code como pentester ────────────────────────────────────────────
def _prompt_pentester(codigo: str, hallazgos: list, lenguaje: str, contexto: str) -> str:
    h_txt = "\n".join(f"- L{h.get('linea','?')} [{h['severidad']}] {h['titulo']}: {h['porque']}"
                      for h in hallazgos[:30]) or "(el escáner automático no marcó nada obvio)"
    return (
        "Actuá como un pentester senior haciendo una auditoría de seguridad DEFENSIVA "
        "(solo análisis, no vas a atacar nada). Te paso código y los hallazgos del "
        "escáner automático.\n\n"
        f"Contexto: {contexto}\nLenguaje: {lenguaje}\n\n"
        f"Hallazgos automáticos:\n{h_txt}\n\n"
        f"Código:\n```{lenguaje}\n{codigo[:12000]}\n```\n\n"
        "Dame un informe en español (voseo), conciso y técnico, con:\n"
        "1. VECTORES DE ENTRADA: por dónde entraría un atacante y qué fallas encadenaría.\n"
        "2. VULNERABILIDADES que el escáner pudo no ver (lógica, autenticación, autorización, "
        "validación de input, manejo de sesión, race conditions).\n"
        "3. DEFENSA EN CAPAS: para cada vector, la mitigación concreta (con el cambio de código).\n"
        "4. PRIORIDAD: qué arreglar primero por impacto/probabilidad.\n"
        "No incluyas payloads de ataque ni código de explotación; enfocá en detectar y blindar."
    )


def _pentester(codigo: str, hallazgos: list, lenguaje: str, contexto: str) -> str:
    if claude_cli is None or not claude_cli.disponible():
        return ""
    r = claude_cli.preguntar(
        _prompt_pentester(codigo, hallazgos, lenguaje, contexto),
        allowed_tools="Read", max_turns=8, timeout=300,
        etiqueta="Auditoría de seguridad",
        fases=["mapeando la superficie de ataque", "buscando vectores", "modelando amenazas",
               "armando la defensa en capas"],
    )
    return r.get("texto", "") if r.get("ok") else ""


# ── Orquestación ─────────────────────────────────────────────────────────────
def auditar(codigo: str = "", ruta: str = "", lenguaje: str = "código",
            contexto: str = "auditoría de seguridad") -> dict:
    """
    Audita seguridad sobre código pegado o un archivo/repo (ruta).
    Devuelve {ok, hallazgos, informe, herramientas, lenguaje}.
    """
    # Reunir el código a escanear
    if not codigo and ruta and os.path.isfile(ruta):
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                codigo = f.read()
        except Exception as e:
            return {"ok": False, "error": f"No pude leer {ruta}: {e}"}

    hallazgos = escanear_patrones(codigo)

    # Herramientas externas si hay una ruta real (archivo o dir)
    if ruta and os.path.exists(ruta):
        hallazgos += _correr_bandit(ruta)
        hallazgos += _correr_gitleaks(ruta)

    # Pentester (Claude Code) razona sobre código + hallazgos
    informe = _pentester(codigo, hallazgos, lenguaje, contexto) if codigo else ""

    return {"ok": True, "hallazgos": hallazgos, "informe": informe,
            "herramientas": herramientas_disponibles(), "lenguaje": lenguaje}


def como_texto(f: dict) -> str:
    if not f.get("ok"):
        return f.get("error", "No se pudo auditar.")
    partes = []
    h = f.get("hallazgos", [])
    if h:
        orden = {"alta": 0, "media": 1, "baja": 2}
        h_ord = sorted(h, key=lambda x: orden.get(x.get("severidad", "baja"), 3))
        lineas = [f"· [{x['severidad'].upper()}] L{x.get('linea','?')} — {x['titulo']}: {x['porque']}"
                  for x in h_ord[:25]]
        altas = sum(1 for x in h if x.get("severidad") == "alta")
        partes.append(f"── Hallazgos del escáner ({len(h)}: {altas} de severidad alta) ──\n" + "\n".join(lineas))
    else:
        partes.append("── Escáner ── No marcó patrones de riesgo obvios (no garantiza que esté limpio).")

    herr = f.get("herramientas", {})
    activas = [k for k, v in herr.items() if v]
    if not activas:
        partes.append("(Para SAST profesional, instalá `bandit` y `gitleaks`; el análisis se hace igual sin ellas.)")

    if f.get("informe"):
        partes.append("── Auditoría del pentester (Claude Code) ──\n" + f["informe"])
    return "\n\n".join(partes)