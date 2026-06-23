"""
SATELLA — punto de entrada.
"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s — %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("satella")

def main():
    log.info("══════════════════════════════════════")
    log.info("  SATELLA — iniciando sistema         ")
    log.info("══════════════════════════════════════")

    from config import GROQ_API_KEY, PORT, DATOS_DIR
    if not GROQ_API_KEY:
        log.error("GROQ_API_KEY no configurada. Revisa tu .env")
        sys.exit(1)

    os.makedirs(DATOS_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATOS_DIR, "conocimiento"), exist_ok=True)

    log.info("Cargando memoria...")
    from nucleo import memoria
    memoria.inicializar()
    from nucleo import coral
    coral.inicializar()

    log.info("Cargando RAG...")
    from nucleo import rag
    docs = rag.cargar_documentos()
    log.info(f"RAG: {docs} documentos disponibles")

    log.info(f"Iniciando servidor en http://localhost:{PORT}")
    from interfaz.servidor import iniciar
    iniciar()


if __name__ == "__main__":
    main()