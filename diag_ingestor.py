"""
Diagnóstico del ingestor — NO toca nada, solo muestra qué está leyendo.
Corré desde la carpeta SATELLA (con el venv activo):  python diag_ingestor.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 64)
try:
    from nucleo import ingestor as ing
    tiene_fix = hasattr(ing, "_texto_de_json")
except Exception as e:
    print("No pude importar el ingestor:", e)
    sys.exit()

print("¿El fix está instalado? (_texto_de_json existe):", tiene_fix)
if not tiene_fix:
    print(">> El ingestor.py que está corriendo es el VIEJO. Hay que reinstalar")
    print("   el ingestor.py nuevo y limpiar el __pycache__ de nucleo/.")

ruta = os.path.join("datos", "aprender", "memories.json")
if not os.path.exists(ruta):
    print("\nNo encuentro", ruta)
    apr = os.path.join("datos", "aprender")
    if os.path.isdir(apr):
        print("Lo que SÍ hay en la carpeta:", os.listdir(apr))
    sys.exit()

raw = open(ruta, encoding="utf-8", errors="replace").read()
print("\nTamaño del archivo:", len(raw), "caracteres")
print("-" * 64)
print("PRIMEROS 400 CARACTERES DEL ARCHIVO CRUDO:")
print(raw[:400])
print("-" * 64)

try:
    data = json.loads(raw)
    print("Tipo de JSON:", type(data).__name__)
    if isinstance(data, list):
        print("Cantidad de elementos:", len(data))
        if data and isinstance(data[0], dict):
            print("Claves del PRIMER elemento:", list(data[0].keys()))
    elif isinstance(data, dict):
        print("Claves de nivel superior:", list(data.keys()))
except Exception as e:
    print("ERROR: el JSON no parsea:", e)
    sys.exit()

if tiene_fix:
    texto = ing._texto_de_json(data)
    print("-" * 64)
    print("TEXTO EXTRAÍDO:", len(texto), "caracteres")
    print("PRIMEROS 600 DEL TEXTO EXTRAÍDO:")
    print(texto[:600] if texto.strip() else "(VACÍO — acá está el problema)")
print("=" * 64)