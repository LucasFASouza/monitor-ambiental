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


def gerar_ruido(horas: int, janela: int) -> list[tuple[int, float, float, float]]:
    """Histórico de ruído com ciclo de dia e noite, mais alguns picos."""
    agora = int(time.time())
    total = (horas * 3600) // janela

    leituras = []

    for passo in range(total):
        ts = agora - (total - passo) * janela
        hora_do_dia = (ts % 86400) / 3600

        # Silencioso de madrugada, mais alto no meio do dia.
        base = 38.0 if hora_do_dia < 6 or hora_do_dia > 22 else 50.0
        laeq = base + random.uniform(-3.0, 3.0)

        # De vez em quando um evento alto, que é o que separa o LAeq do máximo.
        pico = laeq + (random.uniform(15.0, 30.0) if random.random() < 0.08 else random.uniform(3.0, 8.0))

        leituras.append((ts, round(laeq, 1), round(pico, 1), round(laeq - random.uniform(2.0, 6.0), 1)))

    return leituras


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--horas", type=int, default=48)
    analisador.add_argument("--intervalo", type=int, default=config.INTERVALO_SEGUNDOS)
    argumentos = analisador.parse_args()

    database.criar_esquema()

    leituras = gerar(argumentos.horas, argumentos.intervalo)
    ruido = gerar_ruido(argumentos.horas, config.RUIDO_JANELA_SEGUNDOS)

    with database.conectar() as conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)",
            leituras,
        )
        conexao.executemany(
            "INSERT INTO leituras_ruido (ts, laeq, lamax, lamin)"
            " VALUES (?, ?, ?, ?)",
            ruido,
        )

    print(f"{len(leituras)} leituras de ar simuladas em {config.DB_PATH}")
    print(f"{len(ruido)} janelas de ruído simuladas")


if __name__ == "__main__":
    main()
