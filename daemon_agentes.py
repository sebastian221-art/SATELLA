"""
daemon_agentes.py — EL DAEMON DE AGENTES (proceso aparte).
─────────────────────────────────────────────────────────────────────────────
Esto se corre en una terminal SEPARADA del servidor web de Satella:

    python daemon_agentes.py

Y queda latiendo solo: cada minuto mira qué agente programado toca correr, lo
despliega DESATENDIDO (con la correa estricta), lo supervisa, y deja todo en la
bandeja —escalando lo que necesita tu ojo—. Sigue trabajando aunque cierres la
ventana de Satella. Comparte los mismos archivos en disco (plantel, programación,
bandeja), así que lo que programás desde el chat, el daemon lo ejecuta.

Ctrl+C para pararlo.

Opcional: `python daemon_agentes.py 30` para latir cada 30 segundos (default 60).
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("satella.daemon")


def main():
    intervalo = 60
    if len(sys.argv) > 1:
        try:
            intervalo = max(10, int(sys.argv[1]))
        except ValueError:
            pass

    log.info("═" * 46)
    log.info("  SATELLA — daemon de agentes")
    log.info("═" * 46)

    # Cargar lo mínimo que los agentes necesitan (memoria + plantel + programación).
    try:
        from nucleo import coral, hdc, telemetria
        hdc.inicializar()
        coral.inicializar()
        telemetria.inicializar()
    except Exception as e:
        log.warning(f"Daemon: memoria parcial ({e}) — sigo igual.")

    from nucleo.agentes import plantel, programador, bandeja, gerente
    plantel.inicializar()
    programador.inicializar()
    bandeja.inicializar()

    pendientes = programador.listar()
    log.info(f"Daemon: {len(pendientes)} agente(s) programado(s) en cartelera.")
    for t in pendientes:
        log.info("  " + programador.describir(t))

    if not pendientes:
        log.info("Daemon: no hay nada programado todavía. Programá desde el chat: "
                 "«programá a Laura para que revise PSI todos los días a las 9».")

    gerente.correr(intervalo_seg=intervalo)


if __name__ == "__main__":
    main()