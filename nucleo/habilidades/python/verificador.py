"""
nucleo/habilidades/python/verificador.py — QA con EJECUCIÓN
Antes de entregar: valida sintaxis + linting + LO EJECUTA. Si falla (estático o
en runtime), le pide al modelo de código que corrija. Máximo 2 ciclos.
"""
import re

from . import _llm, analizador, ejecutor


def _extraer_codigo(texto: str) -> str:
    m = re.search(r"```(?:python|py)?\s*(.*?)```", texto, re.DOTALL)
    return m.group(1).strip() if m else texto.strip()


def verificar_y_corregir(codigo: str, requerimiento: str = "", max_ciclos: int = 2) -> dict:
    ciclos = 0
    correcciones = []

    while ciclos <= max_ciclos:
        analisis = analizador.analizar(codigo)

        # Problemas bloqueantes estáticos
        errores = list(analisis["errores"])
        errores += [p for p in analisis["problemas"]
                    if "undefined name" in p.lower() or "syntax" in p.lower()]

        # Prueba de ejecución (solo si la sintaxis está OK)
        ejec = {"ok": True, "stderr": "", "stdout": "", "bloqueado": False, "tiempo_ms": 0}
        if analisis["sintaxis_ok"]:
            ejec = ejecutor.ejecutar(codigo, timeout=8)
            if not ejec["ok"] and not ejec["bloqueado"]:
                errores.append(f"Al ejecutar: {ejec['stderr'][:300]}")

        if not errores:
            return {"aprobado": True, "codigo": codigo, "ciclos": ciclos,
                    "analisis": analisis, "ejecucion": ejec, "correcciones": correcciones}

        if ciclos == max_ciclos or not _llm.disponible():
            return {"aprobado": False, "codigo": codigo, "ciclos": ciclos,
                    "analisis": analisis, "ejecucion": ejec, "correcciones": correcciones}

        prompt = (
            f"Este codigo Python tiene problemas:\n```python\n{codigo}\n```\n\n"
            "Problemas detectados por herramientas reales:\n- " + "\n- ".join(errores[:8]) + "\n\n"
            + (f'Tenia que cumplir: "{requerimiento}"\n\n' if requerimiento else "")
            + "Corregilos. Responde SOLO el codigo corregido en un bloque ```python ... ```."
        )
        crudo = _llm.chat(prompt, max_tokens=1800, temperature=0.2)
        nuevo = _extraer_codigo(crudo)
        if not nuevo or nuevo == codigo:
            return {"aprobado": False, "codigo": codigo, "ciclos": ciclos,
                    "analisis": analisis, "ejecucion": ejec, "correcciones": correcciones}
        correcciones.append(f"Ciclo {ciclos+1}: corregi {len(errores)} problema(s).")
        codigo = nuevo
        ciclos += 1

    final = analizador.analizar(codigo)
    return {"aprobado": False, "codigo": codigo, "ciclos": ciclos,
            "analisis": final, "ejecucion": {"ok": False}, "correcciones": correcciones}