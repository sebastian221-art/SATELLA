"""
nucleo/habilidades/agente_codigo/herramientas.py
─────────────────────────────────────────────────────────────────────────────
LAS MANOS Y LOS OJOS del agente. Cada herramienta opera DENTRO de la carpeta
del proyecto (sandbox: no puede salir de ahí) y devuelve una "observación" en
texto que el modelo lee para decidir el próximo paso.

Versión 1a (segura): leer / listar / buscar / editar.
La escritura pasa por el GOBERNADOR. NO hay ejecución de comandos todavía (1b).
"""
import logging
import re
import shlex
import subprocess
from pathlib import Path

log = logging.getLogger("satella.agente.herramientas")

EXT_CODIGO = {".py", ".html", ".htm", ".css", ".js", ".json", ".md", ".txt"}
# lista blanca de comandos que el agente puede correr (sin shell, sin encadenar)
COMANDOS_OK = {"python", "python3", "py", "pytest"}


def _ejecuta_habilitado() -> bool:
    try:
        import config
        return bool(getattr(config, "AGENTE_EJECUTA", True))
    except Exception:
        return True

try:
    from nucleo.habilidades.gobernador import motor as _gob, politica as _gpol
    _gob_ok = True
except Exception:
    _gob_ok = False


def _buscar_flexible(haystack: str, needle: str):
    """Encuentra needle tolerando diferencias de espacios por línea."""
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


class Herramientas:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz).resolve()

    # — sandbox: resolver una ruta relativa sin salir del proyecto —
    def _resolver(self, ruta: str) -> Path:
        p = (self.raiz / ruta).resolve()
        if self.raiz not in p.parents and p != self.raiz:
            raise ValueError(f"ruta fuera del proyecto: {ruta}")
        return p

    def listar(self, subdir: str = "") -> str:
        try:
            base = self._resolver(subdir) if subdir else self.raiz
        except ValueError as e:
            return f"ERROR: {e}"
        if not base.exists():
            return f"No existe: {subdir}"
        archivos = [str(p.relative_to(self.raiz)) for p in base.rglob("*")
                    if p.is_file() and ".git" not in p.parts and p.suffix.lower() in EXT_CODIGO]
        return "Archivos del proyecto:\n" + "\n".join(sorted(archivos)) if archivos else "(sin archivos de código)"

    def contenido_actual(self, ruta: str):
        """Contenido crudo actual de un archivo (para el workspace del bucle). None si no existe."""
        try:
            p = self._resolver(ruta)
        except ValueError:
            return None
        if not p.exists() or not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="ignore")

    def leer_archivo(self, ruta: str) -> str:
        try:
            p = self._resolver(ruta)
        except ValueError as e:
            return f"ERROR: {e}"
        if not p.exists() or not p.is_file():
            return f"No existe el archivo: {ruta}"
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if len(txt) > 12000:
            txt = txt[:12000] + "\n…(truncado)…"
        return f"--- {ruta} ---\n{txt}"

    def buscar(self, patron: str) -> str:
        if not patron:
            return "ERROR: patrón vacío"
        hits = []
        for p in self.raiz.rglob("*"):
            if not (p.is_file() and p.suffix.lower() in EXT_CODIGO) or ".git" in p.parts:
                continue
            try:
                for n, linea in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if patron.lower() in linea.lower():
                        hits.append(f"{p.relative_to(self.raiz)}:{n}: {linea.strip()[:120]}")
                        if len(hits) >= 40:
                            break
            except Exception:
                continue
            if len(hits) >= 40:
                break
        return "Coincidencias:\n" + "\n".join(hits) if hits else f"Sin coincidencias para «{patron}»"

    def editar_archivo(self, ruta: str, buscar: str = "", reemplazar: str = "", cambios: list = None) -> str:
        try:
            p = self._resolver(ruta)
        except ValueError as e:
            return f"ERROR: {e}"
        if not p.exists():
            return f"No existe el archivo: {ruta} (creá primero o revisá el nombre)"

        # un solo cambio o una lista de cambios — todo en UNA escritura
        lista = list(cambios) if cambios else [{"buscar": buscar, "reemplazar": reemplazar}]
        contenido = p.read_text(encoding="utf-8", errors="ignore")
        nuevo = contenido
        aplicados, no_encontrados = 0, []
        for c in lista:
            b, r = c.get("buscar", ""), c.get("reemplazar", "")
            if not b:
                continue
            if b in nuevo:
                nuevo = nuevo.replace(b, r, 1)
                aplicados += 1
            else:
                flexible = _buscar_flexible(nuevo, b)
                if flexible is not None:
                    nuevo = nuevo.replace(flexible, r, 1)
                    aplicados += 1
                else:
                    no_encontrados.append((b.strip().splitlines() or ["(vacío)"])[0][:60])

        if aplicados == 0:
            return f"NO ENCONTRÉ ninguno de los textos a reemplazar en {ruta}: {no_encontrados}. Leé el archivo y copiá el texto EXACTO."
        if nuevo == contenido:
            return f"Sin cambios en {ruta}: lo buscado ya era igual a lo de reemplazo."
        if p.suffix.lower() == ".py":
            try:
                compile(nuevo, str(p), "exec")
            except SyntaxError as e:
                return f"NO escribí: el conjunto de cambios rompe la sintaxis de {ruta}: {e}"
        if _gob_ok:
            v = _gob.evaluar(f"escribir {p.name}", nivel=_gpol.ESCRITURA, objetivo=str(p), propio=True)
            if v["veredicto"] == _gpol.DENEGADO:
                return f"El gobernador denegó escribir {ruta}: {v['razon']}"
            if v["veredicto"] == _gpol.CONFIRMAR:
                return f"El gobernador pide confirmación para escribir {ruta} (token {v.get('token')})."
        try:
            p.write_text(nuevo, encoding="utf-8")
        except Exception as e:
            return f"ERROR escribiendo {ruta}: {e}"
        extra = f" — sintaxis OK" if p.suffix.lower() == ".py" else ""
        pendiente = f" (OJO: no encontré {no_encontrados})" if no_encontrados else ""
        return f"OK: edité {ruta} ({aplicados} reemplazo/s){extra}{pendiente}"

    def correr_comando(self, comando: str) -> str:
        """Corre un comando de la lista blanca DENTRO del proyecto y devuelve la salida real."""
        if not _ejecuta_habilitado():
            return "Ejecución deshabilitada (activá AGENTE_EJECUTA=true en config si querés que corra código)."
        try:
            partes = shlex.split(comando, posix=False)
        except Exception:
            return "comando mal formado"
        if not partes:
            return "comando vacío"
        prog = partes[0].strip('"').lower()
        if prog not in COMANDOS_OK:
            return f"No permitido correr «{partes[0]}». Solo puedo correr {sorted(COMANDOS_OK)} dentro del proyecto."
        if _gob_ok:
            v = _gob.evaluar(f"ejecutar {prog}", nivel=_gpol.EJECUCION, objetivo=str(self.raiz), propio=True)
            if v["veredicto"] == _gpol.DENEGADO:
                return f"El gobernador denegó ejecutar: {v['razon']}"
        try:
            r = subprocess.run(partes, cwd=str(self.raiz), capture_output=True, text=True,
                               timeout=60, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return "TIMEOUT (60s): el comando no terminó. ¿Espera input? Corré con argumentos concretos, no entres a menús interactivos."
        except Exception as e:
            return f"ERROR al ejecutar: {e}"
        out = (r.stdout or "")[-2500:]
        err = (r.stderr or "")[-2500:]
        res = f"exit={r.returncode}"
        if out:
            res += f"\nSALIDA:\n{out}"
        if err:
            res += f"\nERRORES:\n{err}"
        return res if (out or err) else f"exit={r.returncode} (sin salida)"

    # — despacho por nombre —
    def usar(self, nombre: str, args: dict) -> str:
        args = args or {}
        try:
            if nombre == "listar":
                return self.listar(args.get("subdir", ""))
            if nombre == "leer_archivo":
                return self.leer_archivo(args.get("ruta", ""))
            if nombre == "buscar":
                return self.buscar(args.get("patron", ""))
            if nombre == "editar_archivo":
                return self.editar_archivo(args.get("ruta", ""), args.get("buscar", ""),
                                           args.get("reemplazar", ""), args.get("cambios"))
            if nombre == "correr_comando":
                return self.correr_comando(args.get("comando", ""))
            return f"Herramienta desconocida: {nombre}"
        except Exception as e:
            return f"ERROR en {nombre}: {e}"