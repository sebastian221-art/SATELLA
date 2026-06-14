"""
nucleo/habilidades/gobernador/politica.py
La POLÍTICA del Gobernador: define los niveles de riesgo de una acción y la
regla que decide si se permite, se pide confirmación o se deniega.

No tiene estado ni efectos: es lógica pura. El motor le pasa (modo, nivel,
propio) y la política devuelve el veredicto. Así la regla es fácil de auditar
y de testear sin tocar archivos ni red.
"""

# ── Niveles de riesgo, de menor a mayor ──────────────────────────────────────
LECTURA    = "lectura"      # leer / inspeccionar / analizar — sin efecto en el mundo
ESCRITURA  = "escritura"    # crear / modificar / borrar archivos
NAVEGACION = "navegacion"   # abrir o actuar sobre páginas web (clicks, forms, login)
EJECUCION  = "ejecucion"    # correr comandos o código con efectos
SISTEMA    = "sistema"      # nivel OS: borrar masivo, instalar, procesos, red amplia
PROHIBIDO  = "prohibido"    # NUNCA: credenciales ajenas, atacar/suplantar a terceros

ORDEN = [LECTURA, ESCRITURA, NAVEGACION, EJECUCION, SISTEMA, PROHIBIDO]

# ── Modos de operación ───────────────────────────────────────────────────────
MODO_SEGURO    = "seguro"      # todo lo que no sea lectura pide confirmación
MODO_NORMAL    = "normal"      # escritura en lo propio libre; lo demás confirma
MODO_AUDITORIA = "auditoria"   # como normal, pero registra TODO (incluidas lecturas)
MODOS = (MODO_SEGURO, MODO_NORMAL, MODO_AUDITORIA)

# ── Veredictos ───────────────────────────────────────────────────────────────
PERMITIDO = "permitido"
CONFIRMAR = "confirmar"
DENEGADO  = "denegado"

# ── Clasificación heurística por texto (respaldo) ────────────────────────────
# Lo ideal es que cada habilidad pase el `nivel` explícito. Esto es la red de
# seguridad para cuando no lo pasa: clasifica por lo que dice la acción.
_PAT_PROHIBIDO = ("contraseña de otro", "contraseñas ajenas", "credencial ajena",
                  "credenciales ajenas", "robar credencial", "exfiltrar", "keylogger",
                  "atacar", "explotar vulnerabilidad de", "ddos", "ransomware",
                  "phishing", "suplantar identidad", "spyware", "interceptar tráfico")
_PAT_SISTEMA = ("rm -rf", "format c", "del /", "shutdown", "regedit", "registry",
                "instalar paquete", "pip install", "npm install -g", "apt install",
                "uninstall", "matar proceso", "kill -9", "sudo ", "chmod 777",
                "borrar el disco", "formatear")
_PAT_EJECUCION = ("ejecutar comando", "correr comando", "os.system", "subprocess",
                  "abrir una terminal", "lanzar script", "ejecutá", "run shell")
_PAT_NAVEGACION = ("navegar", "abrir la web", "abrí la página", "hacer click", "click en",
                   "llenar formulario", "iniciar sesión en", "login en", "loguearte en",
                   "comprar en", "publicar en")
_PAT_ESCRITURA = ("crear archivo", "escribir archivo", "guardar archivo", "guardar en disco",
                  "modificar archivo", "borrar archivo", "sobrescribir", "editar el archivo")


def clasificar(accion: str, objetivo: str = "") -> str:
    """Asigna un nivel de riesgo a una acción descrita en texto."""
    blob = (str(accion) + " " + str(objetivo)).lower()
    if any(p in blob for p in _PAT_PROHIBIDO):
        return PROHIBIDO
    if any(p in blob for p in _PAT_SISTEMA):
        return SISTEMA
    if any(p in blob for p in _PAT_EJECUCION):
        return EJECUCION
    if any(p in blob for p in _PAT_NAVEGACION):
        return NAVEGACION
    if any(p in blob for p in _PAT_ESCRITURA):
        return ESCRITURA
    return LECTURA


def decidir(modo: str, nivel: str, propio: bool = False) -> tuple:
    """
    Regla central. Devuelve (veredicto, razon).
    El principio "es mío" (propio=True) relaja ESCRITURA, pero NUNCA toca lo
    prohibido ni baja la guardia de ejecución/sistema: la línea es la
    AUTORIZACIÓN sobre el objetivo, no la técnica.
    """
    if nivel == PROHIBIDO:
        return DENEGADO, ("Acción prohibida: nunca se permite, ni en objetivos propios "
                          "(toca credenciales de terceros, suplantación o ataque).")

    if nivel == LECTURA:
        return PERMITIDO, "Lectura/inspección: sin efecto en el mundo, permitido."

    # De acá para abajo, toda acción tiene efecto real.
    if modo == MODO_SEGURO:
        return CONFIRMAR, f"Modo seguro: cualquier acción de '{nivel}' necesita tu confirmación."

    if nivel == ESCRITURA:
        if propio:
            return PERMITIDO, "Escritura sobre objetivo propio en modo normal: permitido."
        return CONFIRMAR, "Escritura sobre algo no declarado como tuyo: pido confirmación."

    if nivel == NAVEGACION:
        return CONFIRMAR, ("Navegación/acción web: pido confirmación" +
                           (" (incluso en tu propio sitio, porque tiene efecto)." if propio else "."))

    if nivel == EJECUCION:
        return CONFIRMAR, "Ejecución con efecto: pido confirmación, incluso en lo propio."

    if nivel == SISTEMA:
        return CONFIRMAR, "Acción de sistema (alto riesgo): siempre requiere confirmación explícita."

    return CONFIRMAR, "Acción con efecto: por defecto pido confirmación."