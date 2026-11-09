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


def gravar_janela(niveis: list[float], offset: float) -> None:
    """Grava a janela em dBFS cru. O offset entra só no log, para leitura humana."""
    laeq = sensor_ruido.media_energetica(niveis)

    database.gravar_ruido(
        laeq_dbfs=round(laeq, 2),
        lamax_dbfs=round(max(niveis), 2),
        lamin_dbfs=round(min(niveis), 2),
    )

    logger.info(
        "LAeq %.1f dB(A) | máx %.1f | mín %.1f  (%d s)",
        laeq + offset,
        max(niveis) + offset,
        min(niveis) + offset,
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

    # O offset vem do banco, onde o dashboard pode alterá-lo. Aqui ele só serve
    # para o log sair em dB(A) legível: o valor gravado é sempre cru.
    offset = database.offset_ruido()

    logger.info(
        "Janela de %d s | offset de calibração em vigor %+.1f dB",
        config.RUIDO_JANELA_SEGUNDOS,
        offset,
    )

    if offset == database.OFFSET_DE_CATALOGO:
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

            # Sem offset: o que se grava é dBFS cru.
            niveis.append(sensor_ruido.nivel_ponderado_a(bloco, microfone.taxa))

            if len(niveis) >= config.RUIDO_JANELA_SEGUNDOS:
                gravar_janela(niveis, offset)
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
