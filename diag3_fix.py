"""
Diag 3 — prueba el FIX de extracción contra tu Groq real, sobre tu memories.json.
Corré desde la carpeta SATELLA (venv activo):  python diag3_fix.py
IMPORTANTE: corré esto DESPUÉS de instalar coral.py, ingestor.py y _llm.py nuevos.
Hace 2-3 llamadas chicas a Groq. No toca tu memoria (no guarda nada).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nucleo import ingestor as ing
from nucleo import coral
from nucleo.habilidades.python import _llm

ruta = os.path.join("datos", "aprender", "memories.json")
data = json.loads(open(ruta, encoding="utf-8", errors="replace").read())
chunk = ing._chunks(ing._texto_de_json(data))[0]
prompt = ing._PROMPT_DOC.format(texto=chunk[:4500])

print("=" * 64)
print("Modelo de extracción:", _llm.modelo())
print("=" * 64)

print("PRUEBA 1 — el FIX real (coral.extraer_generico):")
r = coral.extraer_generico(prompt)
print(f"   conceptos: {len(r['conceptos'])} | relaciones: {len(r['relaciones'])}")
if r["conceptos"]:
    print("   ejemplos:", [c.get("nombre") if isinstance(c, dict) else c for c in r["conceptos"][:6]])
    print("\n>>> EL FIX FUNCIONA. Instalá los 3 archivos y decí 'aprendé de mis archivos de nuevo'.")
else:
    print("\n   El fix con gpt-oss todavía da vacío. Probando un modelo alternativo…")
    print("-" * 64)
    # Probar con un modelo NO-razonador, que para extraer suele ir mejor.
    for modelo_alt in ("llama-3.3-70b-versatile", "qwen-2.5-coder-32b"):
        try:
            _llm._MODEL = modelo_alt
            salida = _llm.chat(prompt, max_tokens=2000, temperature=0.2)
            res = coral._parsear_extraccion(salida)
            print(f"   {modelo_alt}: {len(res['conceptos'])} conceptos",
                  "← ✓ ESTE SÍ" if res["conceptos"] else "(vacío)")
        except Exception as e:
            print(f"   {modelo_alt}: error {e}")
    print("\n>>> Pegame esta salida: el modelo que diga '✓ ESTE SÍ' es el que hay que usar.")
print("=" * 64)