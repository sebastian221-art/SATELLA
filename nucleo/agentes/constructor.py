"""
nucleo/agentes/constructor.py — EL CONSTRUCTOR (Capa 4, Fase 1).
─────────────────────────────────────────────────────────────────────────────
Hasta acá los agentes solo LEÍAN. Esto los deja CREAR código — pero vigilados:

  1. GENERA código para lo que se pidió (vía el modelo).
  2. Lo PRUEBA en el sandbox (nucleo.sandbox.ejecutar_seguro): aislado, entorno
     limpio sin API keys, con timeout que mata loops. NO toca nada real.
  3. Si FALLA por un error chico, lee el error y lo ARREGLA solo (hasta N intentos).
  4. Devuelve el código + el resultado REAL del sandbox.

La pieza clave del diseño: el resultado del sandbox es la EVIDENCIA DE CAMPO.
Cuando Laura diga "el script funciona", el supervisor va a poder chequear ese
"funciona" contra lo que el sandbox realmente devolvió. El sandbox es la fuente
de verdad: un agente no puede mentir sobre si su código corrió, porque corrió de
verdad y quedó registrado.

Fase 1: solo prueba en sandbox (sin riesgo, sin efecto real). Ejecutar algo con
efecto real en el mundo llega después, con la correa del gobernador pidiendo tu OK.
"""
import logging

log = logging.getLogger("satella.constructor")

_MAX_INTENTOS = 3

_PROMPT_GENERAR = """Escribí un script de Python que cumpla exactamente esto:

«{instruccion}»

REGLAS:
- Código completo y ejecutable, listo para correr tal cual.
- Tiene que imprimir (print) su resultado, para poder verificar que funciona.
- Usá solo la librería estándar de Python salvo que sea imprescindible otra cosa.
- Nada de pedir input al usuario ni abrir ventanas: tiene que correr solo.
- Respondé SOLO el código Python, sin explicaciones y sin ```."""

_PROMPT_ARREGLAR = """Este script de Python falló al ejecutarse. Arreglalo.

OBJETIVO: «{instruccion}»

CÓDIGO ACTUAL:
{codigo}

ERROR QUE TIRÓ:
{error}

Devolvé SOLO el código Python corregido y completo, sin explicaciones y sin ```."""


def _limpiar_codigo(salida: str) -> str:
    """Saca fences ``` y razonamiento, deja el código pelado."""
    import re
    if not salida:
        return ""
    s = re.sub(r"<think>.*?</think>", "", salida, flags=re.DOTALL)
    # si vino en un bloque ```python ... ```, quedarse con el contenido
    m = re.search(r"```(?:python)?\s*(.*?)```", s, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return s.strip()


def _generar(instruccion: str, codigo_previo: str = "", error: str = "") -> str:
    from nucleo.habilidades.python import _llm
    if not _llm.disponible():
        return ""
    if codigo_previo and error:
        prompt = _PROMPT_ARREGLAR.format(instruccion=instruccion,
                                         codigo=codigo_previo[:2500], error=error[:1200])
    else:
        prompt = _PROMPT_GENERAR.format(instruccion=instruccion)
    salida = _llm.chat(prompt, max_tokens=2500, temperature=0.2, reasoning_effort="low")
    if not salida:
        salida = _llm.chat(prompt, max_tokens=4000, temperature=0.2)
    return _limpiar_codigo(salida)


def construir(instruccion: str, avisar=None, max_intentos: int = _MAX_INTENTOS) -> dict:
    """Genera código, lo prueba en sandbox y lo arregla si falla.
    Devuelve:
      {ok, codigo, intentos, sandbox: {ejecutado,ok,stdout,stderr,...}, evidencia, resumen}
    `evidencia` es el texto que el supervisor usa como verdad de campo."""
    from nucleo import sandbox

    def _av(t):
        if avisar:
            try:
                avisar(t)
            except Exception:
                pass

    if not instruccion or len(instruccion.strip()) < 4:
        return {"ok": False, "codigo": "", "intentos": 0, "sandbox": {},
                "evidencia": "No me dijeron qué construir.", "resumen": "sin instrucción"}

    _av("🔨 Generando código…")
    codigo = _generar(instruccion)
    if not codigo:
        return {"ok": False, "codigo": "", "intentos": 0, "sandbox": {},
                "evidencia": "No pude generar código (sin modelo).",
                "resumen": "no pude generar el código"}

    ultimo = {}
    for intento in range(1, max_intentos + 1):
        _av(f"🧪 Probando en sandbox (intento {intento}/{max_intentos})…")
        res = sandbox.ejecutar_seguro(codigo, timeout=10)
        ultimo = res

        if res.get("ejecutado") and res.get("ok"):
            salida = (res.get("stdout") or "").strip()
            evidencia = (f"El código corrió en sandbox SIN errores (intento {intento}).\n"
                         f"Salida real del programa:\n{salida or '(sin salida impresa)'}")
            return {"ok": True, "codigo": codigo, "intentos": intento, "sandbox": res,
                    "evidencia": evidencia,
                    "resumen": f"código probado y funcionando en sandbox ({intento} intento/s)"}

        # Falló. ¿Por qué? Si fue por riesgo/seguridad, NO insistir (es correcto que lo frene).
        if not res.get("ejecutado") and "seguridad" in (res.get("razon") or "").lower():
            evidencia = (f"El sandbox NO ejecutó el código por seguridad: {res.get('razon')}.\n"
                         f"Esto requiere tu aprobación; no es un error a arreglar.")
            return {"ok": False, "codigo": codigo, "intentos": intento, "sandbox": res,
                    "evidencia": evidencia, "resumen": "frenado por seguridad — requiere tu OK"}

        # Error chico → leer el error y arreglar.
        error = (res.get("stderr") or res.get("razon") or "error desconocido").strip()
        if intento < max_intentos:
            _av(f"🔧 Falló, lo arreglo: {error[:80]}")
            nuevo = _generar(instruccion, codigo_previo=codigo, error=error)
            if not nuevo or nuevo == codigo:
                break
            codigo = nuevo

    # Agotó intentos.
    error = (ultimo.get("stderr") or ultimo.get("razon") or "error desconocido").strip()
    evidencia = (f"El código NO logró correr bien tras {max_intentos} intentos.\n"
                 f"Último error real del sandbox:\n{error[:800]}")
    return {"ok": False, "codigo": codigo, "intentos": max_intentos, "sandbox": ultimo,
            "evidencia": evidencia, "resumen": f"no logré que funcione ({max_intentos} intentos)"}


def formatear(resultado: dict) -> str:
    """Bloque legible del trabajo del constructor para mostrarle a Sebas."""
    from nucleo import sandbox
    out = []
    estado = "✓ FUNCIONA" if resultado.get("ok") else "✗ NO LOGRÓ FUNCIONAR"
    out.append(f"🔨 CONSTRUCTOR — {estado} ({resultado.get('intentos', 0)} intento/s)")
    codigo = (resultado.get("codigo") or "").strip()
    if codigo:
        out.append("Código generado:")
        out.append("```python")
        out.append(codigo[:1500])
        out.append("```")
    sb = resultado.get("sandbox") or {}
    if sb:
        out.append("Prueba real en sandbox:")
        out.append(sandbox.como_texto(sb))
    return "\n".join(out)