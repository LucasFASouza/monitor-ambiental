"""Teste direto do DHT11, sem banco e sem Flask.

É o primeiro passo no Raspberry: confirmar que a ligação física está certa e
que o sensor responde. Se este script funciona, o resto do projeto funciona.

    python teste_dht.py

Leituras inválidas no meio do caminho são normais no DHT11.
"""

import time

import board
import adafruit_dht

sensor = adafruit_dht.DHT11(
    board.D4,
    use_pulseio=False
)

print("Iniciando leitura do DHT11...")

try:
    while True:
        try:
            temperatura = sensor.temperature
            umidade = sensor.humidity

            print(
                f"Temperatura: {temperatura} °C | "
                f"Umidade: {umidade} %"
            )

        except RuntimeError as erro:
            print(f"Leitura inválida: {erro}")

        time.sleep(3)

finally:
    sensor.exit()
