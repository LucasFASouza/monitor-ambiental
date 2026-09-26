"""Leitura do sensor, com implementações intercambiáveis.

`SensorDHT11Kernel` lê pelo driver de kernel, que é o caminho recomendado.
`SensorDHT11Blinka` usa a biblioteca da Adafruit, mantida só para quem já
tem esse caminho funcionando. `SensorSimulado` gera valores plausíveis sem
hardware nenhum, e é o que permite escrever e testar o coletor, o Flask e o
dashboard inteiros fora do Raspberry Pi.

Quem escolhe é `criar_sensor()`, a partir de config.SENSOR.
"""

import logging
import random
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class LeituraInvalida(RuntimeError):
    """Uma leitura falhou ou veio fora das faixas do datasheet."""


class SensorIndisponivel(RuntimeError):
    """O sensor não pôde sequer ser inicializado.

    Diferente de LeituraInvalida: aqui não adianta tentar de novo, porque
    falta configuração ou hardware. O coletor deve morrer, não insistir.
    """


def _validar(temperatura, umidade) -> tuple[float, float]:
    if temperatura is None or umidade is None:
        raise LeituraInvalida("sensor devolveu valor vazio")

    if not config.TEMPERATURA_MIN <= temperatura <= config.TEMPERATURA_MAX:
        raise LeituraInvalida(f"temperatura fora da faixa: {temperatura} °C")

    if not config.UMIDADE_MIN <= umidade <= config.UMIDADE_MAX:
        raise LeituraInvalida(f"umidade fora da faixa: {umidade} %")

    return float(temperatura), float(umidade)


class SensorDHT11Kernel:
    """DHT11 pelo driver de kernel do Linux, via sysfs (subsistema IIO).

    O kernel mede os pulsos do sensor por interrupção, com carimbo de tempo
    feito pelo próprio kernel. É muito mais confiável do que contar
    microssegundos em Python, e é o único caminho que funciona no Raspberry
    Pi 5.

    Exige uma linha no config.txt do Raspberry e um reboot:

        dtoverlay=dht11,gpiopin=4

    O driver devolve milésimos: 23400 é 23,4 °C e 75000 é 75,0 %. Ele também
    guarda a última medição por cerca de 2 segundos, então ler temperatura e
    umidade em seguida devolve o mesmo par coerente, e não duas medições
    diferentes.
    """

    RAIZ = Path("/sys/bus/iio/devices")
    NOME_DO_DRIVER = "dht11"

    ARQUIVO_TEMPERATURA = "in_temp_input"
    ARQUIVO_UMIDADE = "in_humidityrelative_input"

    def __init__(self, caminho: str = None):
        base = Path(caminho) if caminho else self._encontrar()

        self._temperatura = base / self.ARQUIVO_TEMPERATURA
        self._umidade = base / self.ARQUIVO_UMIDADE

        for arquivo in (self._temperatura, self._umidade):
            if not arquivo.is_file():
                raise SensorIndisponivel(
                    f"{arquivo} não existe. O dispositivo em {base} não parece"
                    " ser um DHT11."
                )

        logger.info(
            "DHT11 pelo driver de kernel em %s (name: %s)",
            base,
            self._nome(base) or "sem nome",
        )

    @staticmethod
    def _nome(dispositivo: Path) -> str:
        """O que o dispositivo diz ser. Nem todo driver preenche isso."""
        identificacao = dispositivo / "name"

        try:
            return identificacao.read_text().strip()
        except OSError:
            return ""

    @classmethod
    def _encontrar(cls) -> Path:
        """Procura o dispositivo pelo que ele oferece, não pelo número.

        A numeração de iio:deviceN depende da ordem de carga dos drivers e
        muda quando outro sensor entra na jogada, então fixar iio:device0
        quebraria em silêncio ao acrescentar hardware.

        A busca é por capacidade — expõe temperatura e umidade relativa — e
        não pelo arquivo `name`, porque o conteúdo dele varia conforme a
        versão do device tree. O nome só desempata se houver mais de um
        candidato.
        """
        candidatos = [
            dispositivo
            for dispositivo in sorted(cls.RAIZ.glob("iio:device*"))
            if (dispositivo / cls.ARQUIVO_TEMPERATURA).is_file()
            and (dispositivo / cls.ARQUIVO_UMIDADE).is_file()
        ]

        if not candidatos:
            raise SensorIndisponivel(cls._explicar_ausencia())

        for dispositivo in candidatos:
            # O driver publica o nome com o pino junto, como "dht11@4", então
            # a comparação é só da parte antes da arroba.
            if cls._nome(dispositivo).split("@")[0] == cls.NOME_DO_DRIVER:
                return dispositivo

        return candidatos[0]

    @classmethod
    def _explicar_ausencia(cls) -> str:
        """Mensagem de erro que mostra o que foi encontrado no lugar.

        Sem isso, quem cai aqui não tem como saber se o driver não carregou
        ou se carregou com outro formato.
        """
        vistos = [
            f"{dispositivo.name} ({cls._nome(dispositivo) or 'sem nome'})"
            for dispositivo in sorted(cls.RAIZ.glob("iio:device*"))
        ]

        return (
            f"Nenhum dispositivo com {cls.ARQUIVO_TEMPERATURA} e"
            f" {cls.ARQUIVO_UMIDADE} em {cls.RAIZ}."
            f" Encontrados: {', '.join(vistos) if vistos else 'nenhum'}."
            " Confira se o config.txt do Raspberry tem a linha"
            f" 'dtoverlay=dht11,gpiopin={config.PINO_BCM}' e se a placa"
            " foi reiniciada depois disso."
        )

    def ler(self) -> tuple[float, float]:
        try:
            temperatura = int(self._temperatura.read_text()) / 1000
            umidade = int(self._umidade.read_text()) / 1000
        except OSError as erro:
            # O driver devolve erro de E/S quando o sensor não respondeu no
            # tempo esperado. No DHT11 isso é rotina, não defeito.
            raise LeituraInvalida(f"driver não devolveu leitura: {erro}") from erro
        except ValueError as erro:
            raise LeituraInvalida(f"driver devolveu valor ilegível: {erro}") from erro

        return _validar(temperatura, umidade)

    def fechar(self) -> None:
        pass


class SensorDHT11Blinka:
    """DHT11 pela biblioteca da Adafruit, contando pulsos em Python.

    Só funciona em Raspberry Pi 4 ou anterior, e mesmo lá de forma instável:
    os pulsos do DHT11 duram de 26 a 70 microssegundos, e o Linux não é um
    sistema de tempo real, então o agendador rouba o processador no meio da
    medição e a leitura se perde. No Raspberry Pi 5 não funciona de jeito
    nenhum, porque o controlador de GPIO mudou.

    Prefira SensorDHT11Kernel. Esta implementação fica para quem já tem esse
    caminho rodando e não quer mexer.
    """

    def __init__(self, pino: int = None):
        # O import fica aqui dentro porque Adafruit-Blinka só instala e importa
        # no Raspberry. Assim este arquivo continua importável no notebook.
        import adafruit_dht
        import board

        numero = pino if pino is not None else config.PINO_BCM
        self._dispositivo = adafruit_dht.DHT11(
            getattr(board, f"D{numero}"),
            use_pulseio=False,
        )
        logger.info("DHT11 (Blinka) inicializado no GPIO%d", numero)

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


IMPLEMENTACOES = {
    "dht11": SensorDHT11Kernel,
    "dht11-blinka": SensorDHT11Blinka,
    "simulado": SensorSimulado,
}


def criar_sensor(nome: str = None):
    nome = nome or config.SENSOR

    try:
        return IMPLEMENTACOES[nome]()
    except KeyError:
        raise ValueError(
            f"MONITOR_SENSOR desconhecido: {nome!r}."
            f" Use um destes: {', '.join(sorted(IMPLEMENTACOES))}."
        ) from None
