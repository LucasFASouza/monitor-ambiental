"""Configuração central do monitor ambiental.

Todos os valores podem ser sobrescritos por variável de ambiente, para que o
mesmo código rode no notebook (sensor simulado) e no Raspberry Pi (sensor real)
sem nenhuma alteração de arquivo.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Banco SQLite. Fica fora do controle de versão.
DB_PATH = Path(os.getenv("MONITOR_DB", BASE_DIR / "data" / "monitor.db"))

# Intervalo entre gravações, em segundos.
# O DHT11 não aceita leituras a menos de 2 s de distância.
INTERVALO_SEGUNDOS = int(os.getenv("MONITOR_INTERVALO", "60"))

# Qual implementação de sensor usar:
#
#   "dht11"         driver de kernel do Linux (recomendado, exige dtoverlay)
#   "dht11-blinka"  biblioteca da Adafruit, contando pulsos em Python
#   "simulado"      valores gerados, para desenvolver fora do Raspberry
#
# O padrão é o sensor real de propósito: se o driver não estiver carregado no
# Pi, queremos um erro na cara, não dados inventados entrando no banco em
# silêncio.
SENSOR = os.getenv("MONITOR_SENSOR", "dht11")

# Pino de dados do DHT11 na numeração BCM. GPIO4 é o pino físico 7.
# Precisa bater com o gpiopin do dtoverlay no config.txt do Raspberry.
PINO_BCM = int(os.getenv("MONITOR_PINO", "4"))

# O DHT11 erra bastante: 30% a 50% de leituras inválidas é comportamento
# normal do sensor, não defeito da ligação. Por isso cada ciclo tenta
# algumas vezes antes de desistir.
TENTATIVAS = int(os.getenv("MONITOR_TENTATIVAS", "5"))
INTERVALO_TENTATIVA = float(os.getenv("MONITOR_INTERVALO_TENTATIVA", "2.5"))

# Faixas do datasheet do DHT11. Leitura fora disso é ruído e vai fora.
TEMPERATURA_MIN, TEMPERATURA_MAX = 0.0, 50.0
UMIDADE_MIN, UMIDADE_MAX = 20.0, 90.0

# Porta do dashboard Flask.
PORTA = int(os.getenv("MONITOR_PORTA", "5000"))


# --- Ruído ------------------------------------------------------------------

# Dispositivo ALSA do microfone. `arecord -l` lista os disponíveis.
RUIDO_DISPOSITIVO = os.getenv(
    "MONITOR_RUIDO_DISPOSITIVO", "plughw:CARD=sndrpigooglevoi,DEV=0"
)

# O overlay googlevoicehat-soundcard fixa a taxa em 48 kHz.
RUIDO_TAXA = int(os.getenv("MONITOR_RUIDO_TAXA", "48000"))

# Canal onde está o microfone: 0 é o esquerdo, com o L/R ligado no GND.
# O outro canal não tem microfone e vem zerado.
RUIDO_CANAL = int(os.getenv("MONITOR_RUIDO_CANAL", "0"))

# Quantos segundos de áudio entram em cada LAeq gravado.
RUIDO_JANELA_SEGUNDOS = int(os.getenv("MONITOR_RUIDO_JANELA", "60"))

# Offset de calibração, em dB, somado ao nível em dBFS para virar dB(A).
#
# O padrão sai da sensibilidade de catálogo do INMP441: -26 dBFS para
# 94 dB SPL, o que dá 120.
#
# ISSO É UM PONTO DE PARTIDA, NÃO UMA CALIBRAÇÃO. Cada módulo varia, e o valor
# real só aparece comparando com um medidor de referência no mesmo ambiente.
# Enquanto não for levantado, o número absoluto é indicativo: confie na
# variação, não no valor.
RUIDO_OFFSET_DB = float(os.getenv("MONITOR_RUIDO_OFFSET", "120.0"))


# --- Limites de classificação -----------------------------------------------
#
# Cada grandeza tem duas faixas fechadas: dentro de "bom" é bom, fora de "bom"
# mas dentro de "atencao" é atenção, fora das duas é ruim.
#
# A faixa "bom" vem de norma vigente sempre que existe uma. A faixa "atencao" é
# uma MARGEM escolhida a partir das fontes citadas, não um valor normativo: ela
# serve para separar "fora do recomendado" de "ruim mesmo".
#
#
# TEMPERATURA  ---------------------------------------------------------------
#
#   bom: 18 a 25 °C
#     NR-17, item 17.8.4.2, redação da Portaria MTP 423/2021: "observando-se o
#     parâmetro de faixa de temperatura do ar entre 18 e 25 °C para ambientes
#     climatizados". É norma de segurança do trabalho em vigor.
#
#     O piso de 18 °C bate com o mínimo das Housing and health guidelines da
#     OMS (2018), por caminho independente: lá a justificativa é mortalidade
#     por frio, não conforto.
#
#   atenção: 16 a 28 °C  [margem]
#     Abaixo de 18 °C já se está fora da NR-17, e 16 °C é onde a literatura de
#     saúde pública passa a documentar risco respiratório. No teto, 25 °C é o
#     limite da NR-17 e 26 °C era o da RE 09/2003 da ANVISA para verão, hoje
#     revogada; 28 °C fica acima de qualquer referência de conforto.
#
#
# UMIDADE  -------------------------------------------------------------------
#
#   bom: 40 a 60 %
#     Convergência de fontes, e não de norma vigente: a revogada RE 09/2003 da
#     ANVISA indicava 40 a 65 % no verão, e a OSHA recomenda 20 a 60 % (sem
#     caráter obrigatório, apoiada na ASHRAE 55). A faixa de 40 a 60 % é a que
#     aparece de forma consistente como a que minimiza tanto proliferação
#     biológica quanto irritação respiratória.
#
#   atenção: 30 a 70 %  [margem]
#     Abaixo de 30 % a irritação de vias aéreas é documentada; acima de 70 % o
#     risco de mofo cresce rápido.
#
#   RESSALVA IMPORTANTE: esta é a grandeza com menos respaldo normativo direto.
#   A NR-17 perdeu o número de umidade na revisão de 2021 — o item 17.8.4.2
#   manda controlar a umidade, mas não diz qual faixa. E a RE 09/2003 da ANVISA
#   foi revogada em julho de 2024 pela RDC 886/2024, substituída pela ABNT NBR
#   17037, que é norma paga e não foi consultada aqui. Se algum dia este
#   projeto for usado para fundamentar alguma coisa, é neste ponto que falta
#   checagem.
#
#
# RUÍDO  ---------------------------------------------------------------------
#
#   bom: até 45 dB(A)
#     A NBR 10152:2017 indica cerca de 40 dB(A) como valor de projeto para
#     escritório privativo, e a própria norma admite tolerância de até 5 dB.
#
#   atenção: até 65 dB(A)
#     NR-17, item 17.8.4.1.2: "o nível de ruído de fundo aceitável para efeito
#     de conforto acústico será de até 65 dB(A), nível de pressão sonora
#     contínuo equivalente ponderado em A e no circuito de resposta Slow (S)".
#
#     É exatamente a grandeza que este monitor calcula: LAeq. A ressalva é o
#     circuito Slow, que tem constante de tempo de 1 s e afeta o valor máximo,
#     não o equivalente — o `lamax` daqui usa blocos de 1 s, o que é
#     comparável, mas não é a mesma definição.
#
#   Nada disso é limite de insalubridade. Exposição ocupacional ao ruído é a
#   NR-15 Anexo 1, com 85 dB(A) para 8 horas, e exige medidor Tipo 1 ou 2 com
#   certificado de calibração. Ver a seção de calibração no README: este
#   monitor acompanha tendência, não sustenta laudo.
LIMITES = {
    "temperatura": {"bom": (18.0, 25.0), "atencao": (16.0, 28.0)},
    "umidade": {"bom": (40.0, 60.0), "atencao": (30.0, 70.0)},
    # Para ruído só o teto importa, então a faixa começa em zero.
    "ruido": {"bom": (0.0, 45.0), "atencao": (0.0, 65.0)},
}
