"""
nucleo/habilidades/copia/generador.py
Genera el código del EQUIVALENTE para Satella, según el contrato funcional y la
estrategia decidida.

Cerebro: CLAUDE CODE (calidad frontera, con tu CLAUDE.md). Si no está o se pasa
del tiempo, cae a Groq vía _generacion_segura (a prueba de cortes). Así la copia
nunca queda muda. generar() crea el equivalente; refinar() lo corrige si la
verificación falla. Deja registrado qué cerebro usó (fuente_usada()).
"""
import re
from nucleo.habilidades.python import _llm
from nucleo.habilidades import _generacion_segura
from . import decisor

try:
    from nucleo import claude_cli
except Exception:  # pragma: no cover
    claude_cli = None

_SYSTEM = (
    "Sos un ingeniero senior de Python. Generás código limpio, modular y LIVIANO para "
    "correr en CPU sin GPU. Implementás la FUNCIÓN pedida adaptada a esas restricciones, "
    "no copias implementación ajena. Devolvés SOLO código Python, sin explicaciones, sin "
    "markdown, sin ```."
)

_INSTR = {
    "port_adaptado": "Portá la lógica adaptándola a Satella (limpia, modular).",
    "equivalente_funcional": ("Construí un EQUIVALENTE FUNCIONAL liviano: mismo trabajo, "
                              "implementación más simple y barata (reglas, heurísticas, "
                              "estructuras chicas) en vez de lo pesado del original."),
    "mejora": ("Construí un equivalente funcional liviano Y mejorá lo que puedas (claridad, "
               "eficiencia, robustez), sin las limitaciones del original."),
}

# Qué cerebro usó la última generación (para transparencia en el reporte).
_ultima_fuente = ""


def fuente_usada() -> str:
    return _ultima_fuente


def _pensar(prompt, etiqueta, fases, timeout=360):
    """Claude Code si está; si no (o si falla/timeout), Groq. Registra la fuente."""
    global _ultima_fuente
    _ultima_fuente = ""
    # 1) Claude Code (mejor calidad). Timeout amplio para tareas grandes (ej. spacy).
    if claude_cli is not None and claude_cli.disponible():
        r = claude_cli.preguntar(
            prompt + "\n\nRespondé SOLO el código en un bloque ```python ... ```.",
            allowed_tools="Read", max_turns=6, timeout=timeout, etiqueta=etiqueta, fases=fases,
        )
        if r.get("ok"):
            _ultima_fuente = "Claude Code"
            return _limpiar(r.get("texto", ""))
    # 2) Respaldo: Groq a prueba de cortes
    if _llm.disponible():
        _ultima_fuente = "Groq (respaldo)"
        return _limpiar(_generacion_segura.completar_codigo(prompt, system=_SYSTEM, max_tokens=4000))
    return ""


def generar(objetivo, contrato_txt, decision):
    instr = _INSTR.get(decision["estrategia"], _INSTR["equivalente_funcional"])
    prompt = (
        f"Pedido: «{objetivo}».\n\n"
        f"CONTRATO FUNCIONAL a implementar:\n{contrato_txt[:4000]}\n\n"
        f"ESTRATEGIA: {decision['estrategia']} — {instr}\n"
        f"RESTRICCIONES: {decisor.restricciones_satella()}\n\n"
        "Generá el código Python del equivalente. Incluí docstring breve y, si aplica, un "
        "ejemplo de uso bajo `if __name__ == '__main__':`."
    )
    return _pensar(prompt, "Copia (equivalente)",
                   ["entendiendo qué replicar", "diseñando el equivalente liviano",
                    "escribiendo el código", "afinando los detalles"])


def refinar(objetivo, codigo, contrato_txt, decision, error):
    """Corrige el equivalente cuando la verificación falló (sintaxis o ejecución)."""
    prompt = (
        f"Este equivalente para «{objetivo}» NO pasó la verificación.\n"
        f"Error/estado: {error}\n\n"
        f"Código actual:\n```python\n{codigo}\n```\n\n"
        f"Contrato funcional a cumplir:\n{contrato_txt[:2500]}\n\n"
        f"RESTRICCIONES: {decisor.restricciones_satella()}\n\n"
        "Corregí el código para que ejecute limpio sin cambiar su función. "
        "Si tiene un `if __name__ == '__main__':` de ejemplo, dejalo simple y rápido."
    )
    return _pensar(prompt, "Copia (corrigiendo)",
                   ["leyendo el error", "corrigiendo el equivalente"], timeout=300)


def _limpiar(txt):
    if not txt:
        return ""
    txt = txt.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", txt, re.S)
    if m:
        return m.group(1).strip()
    return txt