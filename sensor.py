"""Leitura do sensor, com duas implementações intercambiáveis.

`SensorDHT11` fala com o hardware real pelo GPIO. `SensorSimulado` gera valores
plausíveis sem hardware nenhum, e é o que permite escrever e testar o coletor,
o Flask e o dashboard inteiros fora do Raspberry Pi.

Quem escolhe é `criar_sensor()`, a partir de config.SENSOR.
"""

import logging
import random

import config

logger = logging.getLogger(__name__)


class LeituraInvalida(RuntimeError):
    """Uma leitura falhou ou veio fora das faixas do datasheet."""


def _validar(temperatura, umidade) -> tuple[float, float]:
    if temperatura is None or umidade is None:
        raise LeituraInvalida("sensor devolveu valor vazio")

    if not config.TEMPERATURA_MIN <= temperatura <= config.TEMPERATURA_MAX:
        raise LeituraInvalida(f"temperatura fora da faixa: {temperatura} °C")

    if not config.UMIDADE_MIN <= umidade <= config.UMIDADE_MAX:
        raise LeituraInvalida(f"umidade fora da faixa: {umidade} %")

    return float(temperatura), float(umidade)


class SensorDHT11:
    """DHT11 ligado ao GPIO do Raspberry Pi."""

    def __init__(self, pino: str = None):
        # O import fica aqui dentro porque Adafruit-Blinka só instala e importa
        # no Raspberry. Assim este arquivo continua importável no notebook.
        import adafruit_dht
        import board

        nome_pino = pino or config.PINO_DADOS
        self._dispositivo = adafruit_dht.DHT11(
            getattr(board, nome_pino),
            use_pulseio=False,
        )
        logger.info("DHT11 inicializado no pino %s", nome_pino)

    def ler(self) -> tuple[float, float]:
        try:
            temperatura = self._dispositivo.temperature
            umidade = self._dispositivo.humidity
        except RuntimeError as erro:
            # A biblioteca levanta RuntimeError em toda falha de sincronismo,
            # que no DHT11 é rotina. Vira LeituraInvalida para o coletor
            # tratar como "tenta de novo", e não como defeito.
            raise LeituraInvalida(str(erro)) from erro

        return _validar(temperatura, umidade)

    def fechar(self) -> None:
        self._dispositivo.exit()


class SensorSimulado:
    """Valores gerados, para desenvolver sem o Raspberry.

    Faz um passeio aleatório em torno de uma base e, de vez em quando, falha
    de propósito, para que o caminho de repetição do coletor seja exercitado
    em desenvolvimento e não só na primeira noite no Pi.
    """

    # Proporção de leituras que falham. O DHT11 real erra bem mais que isso.
    CHANCE_DE_FALHA = 0.2

    def __init__(self, temperatura: float = 24.0, umidade: float = 55.0):
        self._temperatura = temperatura
        self._umidade = umidade
        logger.warning(
            "Usando SENSOR SIMULADO. Nenhum dado real está sendo lido."
        )

    def ler(self) -> tuple[float, float]:
        if random.random() < self.CHANCE_DE_FALHA:
            raise LeituraInvalida("falha simulada de leitura")

        self._temperatura += random.uniform(-0.4, 0.4)
        self._umidade += random.uniform(-1.0, 1.0)

        self._temperatura = min(max(self._temperatura, 15.0), 33.0)
        self._umidade = min(max(self._umidade, 25.0), 75.0)

        # O DHT11 tem resolução de 1 °C e 1%, então arredondamos para que os
        # dados simulados tenham a mesma cara dos reais.
        return _validar(round(self._temperatura), round(self._umidade))

    def fechar(self) -> None:
        pass


def criar_sensor(nome: str = None):
    nome = nome or config.SENSOR

    if nome == "dht11":
        return SensorDHT11()

    if nome == "simulado":
        return SensorSimulado()

    raise ValueError(
        f"MONITOR_SENSOR desconhecido: {nome!r}. Use 'dht11' ou 'simulado'."
    )
