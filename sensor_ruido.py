"""Medição de nível de ruído a partir do microfone I2S.

Ruído não é uma leitura instantânea como temperatura: é uma estatística. O
microfone é amostrado continuamente a 48 kHz e cada janela de tempo vira um
número só, o LAeq — nível equivalente contínuo ponderado em A. É assim que
toda norma de ruído mede, porque é a energia acumulada que importa, não o
valor de um instante.

A captura é feita pelo `arecord`, em subprocesso, lendo áudio cru da entrada
I2S. Isso evita depender de PortAudio ou de compilar qualquer coisa no
Raspberry: o `arecord` já vem com o sistema.

AVISO SOBRE O NÚMERO ABSOLUTO: o nível em dB(A) depende de um offset de
calibração que precisa ser levantado contra um medidor de referência. Sem
isso, só a variação relativa tem significado. O offset vive no banco, em
`configuracao`: ver `database.offset_ruido`.
"""

import logging
import subprocess

import numpy as np

import config

logger = logging.getLogger(__name__)

# O INMP441 entrega 24 bits alinhados à esquerda dentro de um quadro de 32,
# então o fundo de escala é o do inteiro de 32 bits com sinal.
FUNDO_DE_ESCALA = 2.0 ** 31

# Abaixo disto o sinal é só o ruído de fundo do próprio microfone, e o
# logaritmo de zero não existe.
PISO_LINEAR = 1e-12


class CapturaIndisponivel(RuntimeError):
    """O arecord não pôde ser iniciado ou morreu durante a captura."""


def pesos_ponderacao_a(frequencias: np.ndarray) -> np.ndarray:
    """Resposta da ponderação A, em ganho linear, para cada frequência.

    É a curva que imita a sensibilidade do ouvido humano, definida na
    IEC 61672-1. Todos os limites normativos de ruído são em dB(A), então sem
    ela o número não é comparável com norma nenhuma.

    A fórmula é normalizada para ganho unitário em 1 kHz, que é a definição.
    """
    f2 = np.asarray(frequencias, dtype=np.float64) ** 2

    def resposta(quadrado_da_frequencia):
        numerador = (12194.0 ** 2) * quadrado_da_frequencia ** 2
        denominador = (
            (quadrado_da_frequencia + 20.6 ** 2)
            * np.sqrt(
                (quadrado_da_frequencia + 107.7 ** 2)
                * (quadrado_da_frequencia + 737.9 ** 2)
            )
            * (quadrado_da_frequencia + 12194.0 ** 2)
        )
        return numerador / denominador

    with np.errstate(divide="ignore", invalid="ignore"):
        ganho = resposta(f2)

    ganho = np.nan_to_num(ganho, nan=0.0, posinf=0.0, neginf=0.0)

    # Em 1 kHz a fórmula crua dá ~0,794; a definição exige 1,0 ali.
    return ganho / resposta(np.float64(1000.0) ** 2)


def nivel_ponderado_a(bloco: np.ndarray, taxa: int) -> float:
    """Nível ponderado em A de um bloco de amostras, em dBFS.

    A ponderação é aplicada no domínio da frequência, e não por filtro IIR,
    por um motivo prático: um filtro IIR é sequencial, amostra por amostra, e
    em Python isso não acompanha 48 mil amostras por segundo num Raspberry Pi 3.
    A FFT do numpy faz o mesmo trabalho de uma vez. Como aqui só interessa o
    nível, e não o sinal filtrado, as duas abordagens são equivalentes.
    """
    if bloco.size == 0:
        return float("-inf")

    espectro = np.fft.rfft(bloco)
    potencia = np.abs(espectro) ** 2

    # Os bins interiores representam também as frequências negativas, então
    # carregam o dobro da energia. O de contínua e o de Nyquist, não.
    potencia[1:-1] *= 2.0

    pesos = pesos_ponderacao_a(np.fft.rfftfreq(bloco.size, d=1.0 / taxa))

    media_quadratica = np.sum(potencia * pesos ** 2) / bloco.size ** 2

    return 10.0 * np.log10(max(media_quadratica, PISO_LINEAR))


def media_energetica(niveis) -> float:
    """Média dos níveis pela energia, que é como se soma decibel.

    Média aritmética de decibéis não significa nada: 40 dB e 80 dB não dão
    60 dB de exposição, dão praticamente 80, porque a escala é logarítmica.
    """
    niveis = np.asarray(list(niveis), dtype=np.float64)

    if niveis.size == 0:
        return float("-inf")

    return 10.0 * np.log10(np.mean(10.0 ** (niveis / 10.0)))


class MicrofoneI2S:
    """Captura contínua pelo arecord, entregando blocos de 1 segundo."""

    def __init__(self, dispositivo: str = None, taxa: int = None, canal: int = None):
        self.dispositivo = dispositivo or config.RUIDO_DISPOSITIVO
        self.taxa = taxa or config.RUIDO_TAXA
        self.canal = canal if canal is not None else config.RUIDO_CANAL

        self._processo = None

        # Um bloco de 1 s. Dois canais de 4 bytes, dos quais usamos um só: o
        # outro não tem microfone ligado e vem zerado.
        self._bytes_por_bloco = self.taxa * 2 * 4

    def abrir(self) -> None:
        comando = [
            "arecord",
            "-D", self.dispositivo,
            "-c", "2",
            "-f", "S32_LE",
            "-r", str(self.taxa),
            "-t", "raw",
            "--quiet",
        ]

        logger.info("Capturando: %s", " ".join(comando))

        try:
            self._processo = subprocess.Popen(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as erro:
            raise CapturaIndisponivel(
                "arecord não encontrado. Instale com 'sudo apt install alsa-utils'."
            ) from erro

    def ler_bloco(self) -> np.ndarray:
        """Um bloco de 1 segundo do canal com microfone, normalizado em ±1."""
        if self._processo is None:
            raise CapturaIndisponivel("captura não foi aberta")

        dados = self._processo.stdout.read(self._bytes_por_bloco)

        if len(dados) < self._bytes_por_bloco:
            erro = self._processo.stderr.read().decode("utf-8", "replace").strip()
            raise CapturaIndisponivel(
                f"captura interrompida ({len(dados)} de {self._bytes_por_bloco}"
                f" bytes). arecord disse: {erro or 'nada'}"
            )

        quadros = np.frombuffer(dados, dtype="<i4")

        return quadros[self.canal :: 2].astype(np.float64) / FUNDO_DE_ESCALA

    def fechar(self) -> None:
        if self._processo is None:
            return

        self._processo.terminate()

        try:
            self._processo.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._processo.kill()

        self._processo = None
