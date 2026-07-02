"""
Diagnóstico 2 — ve QUÉ devuelve Groq al extraer conceptos, y prueba un parser
robusto. Corré desde la carpeta SATELLA (venv activo):  python diag2_extraccion.py
Hace UNA llamada chica a Groq. No toca nada.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nucleo import ingestor as ing
from nucleo.habilidades.python import _llm

ruta = os.path.join("datos", "aprender", "memories.json")
data = json.loads(open(ruta, encoding="utf-8", errors="replace").read())
texto = ing._texto_de_json(data)
trozos = ing._chunks(texto)
chunk = trozos[0]

print("=" * 64)
print("Modelo de extracción:", _llm.modelo())
print("Fragmentos totales:", len(trozos), "| largo del 1º:", len(chunk))
print("=" * 64)

raw = _llm.chat(ing._PROMPT_DOC.format(texto=chunk[:4500]),
                max_tokens=800, temperature=0.2)
print("RESPUESTA CRUDA DE GROQ (primeros 1600 chars):")
print(raw[:1600] if raw else ">>> VACÍA — el modelo no devolvió contenido <<<")
print("=" * 64)

print("¿El parser ACTUAL (ingestor._extraer) saca algo?:")
print("  ", ing._extraer(chunk))
print("-" * 64)


def _candidatos(s):
    s = re.sub(r"```json|```", "", s or "")
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    s = re.sub(r"<\|.*?\|>", "", s, flags=re.DOTALL)
    spans, pila = [], []
    for i, ch in enumerate(s):
        if ch == "{":
            pila.append(i)
        elif ch == "}" and pila:
            spans.append(s[pila.pop():i + 1])
    return sorted(set(spans), key=len, reverse=True)


robusto = None
for c in _candidatos(raw or ""):
    try:
        o = json.loads(c)
        if isinstance(o, dict) and ("conceptos" in o or "relaciones" in o):
            robusto = o
            break
    except Exception:
        continue
print("¿El parser ROBUSTO saca algo?:")
print("  ", robusto)
print("=" * 64)