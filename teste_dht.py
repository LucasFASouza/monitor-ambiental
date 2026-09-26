"""Teste do sensor, sem banco e sem Flask.

É o primeiro passo no Raspberry: confirmar que a ligação física está certa e
que o sensor responde. Se este script funciona, o resto do projeto funciona.

    python teste_dht.py

Usa a mesma implementação que o coletor vai usar, definida por MONITOR_SENSOR,
para que o teste valide o caminho real e não um caminho parecido.

Leituras inválidas no meio são normais: o DHT11 erra bastante, e 30% a 50% de
falhas é comportamento do sensor, não defeito da ligação. O que importa é a
conta no fim.
"""

import time

import config
import sensor as sensor_modulo

INTERVALO = 3


def main() -> None:
    print(f"Sensor: {config.SENSOR}  |  GPIO{config.PINO_BCM}")

    try:
        sensor = sensor_modulo.criar_sensor()
    except sensor_modulo.SensorIndisponivel as erro:
        print(f"\nSensor indisponível:\n\n  {erro}\n")
        raise SystemExit(1)

    print("Lendo. Ctrl+C para parar.\n")

    validas = 0
    invalidas = 0

    try:
        while True:
            try:
                temperatura, umidade = sensor.ler()
                validas += 1
                print(f"Temperatura: {temperatura:5.1f} °C | Umidade: {umidade:5.1f} %")
            except sensor_modulo.LeituraInvalida as erro:
                invalidas += 1
                print(f"Leitura inválida: {erro}")

            time.sleep(INTERVALO)

    except KeyboardInterrupt:
        print()
    finally:
        sensor.fechar()

        total = validas + invalidas
        if total:
            print(
                f"\n{validas} de {total} leituras válidas"
                f" ({validas / total:.0%})."
            )


if __name__ == "__main__":
    main()
