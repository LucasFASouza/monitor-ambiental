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


# --- Limites de classificação -----------------------------------------------
#
# PROVISÓRIOS. O handoff prevê definir e fundamentar esses limites depois.
# Os valores abaixo são um ponto de partida de conforto de ambiente interno
# (faixa de conforto térmico usual e a recomendação comum de 40% a 60% de
# umidade relativa), não uma norma aplicada.
#
# Cada grandeza tem duas faixas fechadas: dentro de "bom" é bom, fora de "bom"
# mas dentro de "atencao" é atenção, fora das duas é ruim.
#
# Lembrete ao revisar: a umidade do DHT11 tem precisão de ±5%, então limites
# muito estreitos dariam uma falsa sensação de exatidão.
LIMITES = {
    "temperatura": {"bom": (18.0, 26.0), "atencao": (16.0, 30.0)},
    "umidade": {"bom": (40.0, 60.0), "atencao": (30.0, 70.0)},
}
