"""Coletor: lê o sensor em intervalos regulares e grava no SQLite.

Roda de forma independente do dashboard. Se o Flask cair, a coleta continua;
se o coletor cair, o dashboard mostra os dados antigos e avisa que estão
parados.

    python collector.py
"""

import logging
import signal
import threading
import time

import config
import database
import sensor as sensor_modulo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("coletor")

# Sinalizado quando chega SIGTERM ou SIGINT. Usado também para dormir, assim
# o desligamento é imediato em vez de esperar o intervalo inteiro passar.
encerrar = threading.Event()


def _tratar_sinal(numero, _quadro):
    logger.info("Sinal %s recebido, encerrando.", signal.Signals(numero).name)
    encerrar.set()


def ler_com_tentativas(sensor) -> tuple[float, float] | None:
    """Tenta ler algumas vezes antes de desistir do ciclo.

    Falha isolada no DHT11 é rotina, então só vale registrar em nível de aviso
    quando todas as tentativas do ciclo falharem.
    """
    for tentativa in range(1, config.TENTATIVAS + 1):
        try:
            return sensor.ler()
        except sensor_modulo.LeituraInvalida as erro:
            logger.debug("Tentativa %d falhou: %s", tentativa, erro)

        if tentativa < config.TENTATIVAS:
            if encerrar.wait(config.INTERVALO_TENTATIVA):
                return None

    return None


def main() -> None:
    signal.signal(signal.SIGTERM, _tratar_sinal)
    signal.signal(signal.SIGINT, _tratar_sinal)

    database.criar_esquema()
    logger.info("Banco em %s", config.DB_PATH)

    try:
        sensor = sensor_modulo.criar_sensor()
    except sensor_modulo.SensorIndisponivel as erro:
        # Falta configuração ou hardware: insistir não resolve. Melhor morrer
        # com a explicação no journal do que encher o log de tentativas.
        logger.error("Sensor indisponível: %s", erro)
        raise SystemExit(1)

    logger.info(
        "Coletando a cada %d s (sensor: %s)",
        config.INTERVALO_SEGUNDOS,
        config.SENSOR,
    )

    ciclos_sem_leitura = 0
    proximo = time.monotonic()

    try:
        while not encerrar.is_set():
            leitura = ler_com_tentativas(sensor)

            if leitura is None:
                if not encerrar.is_set():
                    ciclos_sem_leitura += 1
                    logger.warning(
                        "Nenhuma leitura válida em %d tentativas"
                        " (%d ciclo(s) seguido(s) sem dado).",
                        config.TENTATIVAS,
                        ciclos_sem_leitura,
                    )
            else:
                ciclos_sem_leitura = 0
                temperatura, umidade = leitura
                database.gravar(temperatura, umidade)
                logger.info(
                    "Temperatura: %.1f °C | Umidade: %.1f %%",
                    temperatura,
                    umidade,
                )

            # Agenda pelo relógio monotônico para o intervalo não escorregar
            # com o tempo gasto nas tentativas.
            proximo += config.INTERVALO_SEGUNDOS
            espera = max(proximo - time.monotonic(), 0)

            if espera == 0:
                # As tentativas passaram do intervalo. Reancora para não
                # acumular atraso ciclo após ciclo.
                proximo = time.monotonic()

            encerrar.wait(espera)
    finally:
        sensor.fechar()
        logger.info("Coletor encerrado.")


if __name__ == "__main__":
    main()
