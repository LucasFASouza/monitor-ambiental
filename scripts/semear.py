"""Preenche o banco com um histórico simulado.

Serve para trabalhar no dashboard sem esperar horas de coleta real. Nunca rode
isso no Raspberry com dados de verdade: os registros gerados são
indistinguíveis dos reais depois de gravados.

    python scripts/semear.py --horas 48
"""

import argparse
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402


def gerar(horas: int, intervalo: int) -> list[tuple[int, float, float]]:
    agora = int(time.time())
    total = (horas * 3600) // intervalo

    leituras = []

    for passo in range(total):
        ts = agora - (total - passo) * intervalo

        # Um ciclo diário suave, mais um pouco de ruído, para as curvas terem
        # alguma forma em vez de uma linha reta.
        fase = (ts % 86400) / 86400 * 2 * math.pi

        temperatura = 23.0 + 4.0 * math.sin(fase - 1.8) + random.uniform(-0.6, 0.6)
        umidade = 55.0 - 10.0 * math.sin(fase - 1.8) + random.uniform(-2.0, 2.0)

        leituras.append((ts, round(temperatura), round(umidade)))

    return leituras


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--horas", type=int, default=48)
    analisador.add_argument("--intervalo", type=int, default=config.INTERVALO_SEGUNDOS)
    argumentos = analisador.parse_args()

    database.criar_esquema()

    leituras = gerar(argumentos.horas, argumentos.intervalo)

    with database.conectar() as conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)",
            leituras,
        )

    print(f"{len(leituras)} leituras simuladas gravadas em {config.DB_PATH}")


if __name__ == "__main__":
    main()
