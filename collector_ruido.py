"""Coletor de ruído: mede o nível do microfone e grava um LAeq por janela.

Processo separado do coletor de ar, porque a natureza da medida é outra. O
DHT11 é lido de minuto em minuto e cada leitura vale por si. O microfone
precisa ser amostrado sem interrupção, e o que se grava é a energia acumulada
da janela inteira.

    python collector_ruido.py

A própria taxa do áudio serve de relógio: cada bloco lido é exatamente um
segundo de som, então a janela fecha contando blocos, sem depender do
agendador do sistema.
"""

import logging
import signal
import threading

import config
import database
import sensor_ruido

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("ruido")

encerrar = threading.Event()


def _tratar_sinal(numero, _quadro):
    logger.info("Sinal %s recebido, encerrando.", signal.Signals(numero).name)
    encerrar.set()


def gravar_janela(niveis: list[float]) -> None:
    laeq = sensor_ruido.media_energetica(niveis)

    database.gravar_ruido(
        laeq=round(laeq, 1),
        lamax=round(max(niveis), 1),
        lamin=round(min(niveis), 1),
    )

    logger.info(
        "LAeq %.1f dB(A) | máx %.1f | mín %.1f  (%d s)",
        laeq,
        max(niveis),
        min(niveis),
        len(niveis),
    )


def main() -> None:
    signal.signal(signal.SIGTERM, _tratar_sinal)
    signal.signal(signal.SIGINT, _tratar_sinal)

    database.criar_esquema()

    microfone = sensor_ruido.MicrofoneI2S()

    try:
        microfone.abrir()
    except sensor_ruido.CapturaIndisponivel as erro:
        logger.error("Captura indisponível: %s", erro)
        raise SystemExit(1)

    logger.info(
        "Janela de %d s | offset de calibração %+.1f dB",
        config.RUIDO_JANELA_SEGUNDOS,
        config.RUIDO_OFFSET_DB,
    )

    if config.RUIDO_OFFSET_DB == 120.0:
        logger.warning(
            "Offset ainda é o valor de catálogo do INMP441, não uma"
            " calibração. O número absoluto é indicativo."
        )

    niveis: list[float] = []

    try:
        while not encerrar.is_set():
            try:
                bloco = microfone.ler_bloco()
            except sensor_ruido.CapturaIndisponivel as erro:
                if encerrar.is_set():
                    break

                # A captura morreu no meio. Não há como seguir medindo, e
                # insistir daria janelas com buracos: melhor sair e deixar o
                # systemd reabrir tudo do zero.
                logger.error("Captura interrompida: %s", erro)
                raise SystemExit(1)

            nivel = (
                sensor_ruido.nivel_ponderado_a(bloco, microfone.taxa)
                + config.RUIDO_OFFSET_DB
            )
            niveis.append(nivel)

            if len(niveis) >= config.RUIDO_JANELA_SEGUNDOS:
                gravar_janela(niveis)
                niveis = []
    finally:
        microfone.fechar()

        if niveis:
            # Janela incompleta não vira registro: misturar durações
            # diferentes tornaria o histórico incomparável.
            logger.info("Descartando janela incompleta de %d s.", len(niveis))

        logger.info("Coletor de ruído encerrado.")


if __name__ == "__main__":
    main()
