"""
scraper.py — agrega conocimiento al RAG de Satella scrapeando URLs.
Uso: python scraper.py <url> <nombre_del_archivo>
Ejemplo: python scraper.py https://rezero.fandom.com/wiki/Echidna echidna_wiki
"""
import re
import sys
import os
import httpx

CONOCIMIENTO_DIR = os.path.join(os.path.dirname(__file__), "datos", "conocimiento")


def limpiar_html(html: str) -> str:
    """Extrae texto limpio de HTML."""
    # Eliminar scripts y estilos
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    # Convertir párrafos y saltos a newlines
    html = re.sub(r'</p>|<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</h[1-6]>', '\n\n', html, flags=re.IGNORECASE)
    # Eliminar todos los tags restantes
    html = re.sub(r'<[^>]+>', ' ', html)
    # Decodificar entidades comunes
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
    html = html.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    # Limpiar espacios múltiples
    html = re.sub(r' {2,}', ' ', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


def scrapear(url: str) -> str:
    """Descarga y limpia texto de una URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SatellaBot/1.0)"}
        r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        if r.status_code == 200:
            return limpiar_html(r.text)
        print(f"Error HTTP {r.status_code} para {url}")
        return ""
    except Exception as e:
        print(f"Error scrapeando {url}: {e}")
        return ""


def guardar_conocimiento(contenido: str, nombre: str, titulo: str = "") -> bool:
    """Guarda el contenido como archivo de conocimiento para el RAG."""
    os.makedirs(CONOCIMIENTO_DIR, exist_ok=True)

    if not nombre.endswith('.txt'):
        nombre += '.txt'

    path = os.path.join(CONOCIMIENTO_DIR, nombre)

    with open(path, 'w', encoding='utf-8') as f:
        if titulo:
            f.write(f"== {titulo.upper()} ==\n\n")
        # Guardar máximo 10000 caracteres para no saturar el RAG
        f.write(contenido[:10000])

    print(f"Guardado: {path} ({len(contenido[:10000])} caracteres)")
    return True


def agregar_desde_texto(texto: str, nombre: str, titulo: str = "") -> bool:
    """Agrega conocimiento directamente desde texto (sin scraping)."""
    return guardar_conocimiento(texto, nombre, titulo)


def listar_conocimiento():
    """Lista todos los documentos en el RAG."""
    os.makedirs(CONOCIMIENTO_DIR, exist_ok=True)
    archivos = [f for f in os.listdir(CONOCIMIENTO_DIR) if f.endswith('.txt')]
    if not archivos:
        print("No hay documentos en el RAG.")
        return
    print(f"\n{len(archivos)} documentos en el RAG:")
    for f in sorted(archivos):
        path = os.path.join(CONOCIMIENTO_DIR, f)
        size = os.path.getsize(path)
        print(f"  {f} ({size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python scraper.py <url> [nombre_archivo]")
        print("  python scraper.py --lista")
        print()
        print("Ejemplos:")
        print("  python scraper.py https://rezero.fandom.com/wiki/Echidna echidna_wiki")
        print("  python scraper.py --lista")
        sys.exit(0)

    if sys.argv[1] == "--lista":
        listar_conocimiento()
        sys.exit(0)

    url = sys.argv[1]
    nombre = sys.argv[2] if len(sys.argv) > 2 else url.split('/')[-1]

    print(f"Scrapeando: {url}")
    contenido = scrapear(url)

    if contenido:
        guardar_conocimiento(contenido, nombre, titulo=nombre.replace('_', ' '))
        print("Listo. Reinicia Satella para que cargue el nuevo conocimiento.")
    else:
        print("No se pudo obtener contenido.")