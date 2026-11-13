"""Mantém o banco de demonstração respirando, um minuto por vez.

NÃO RODE CONTRA O BANCO DE PRODUÇÃO. O caminho vem de MONITOR_DB e o script
recusa qualquer banco cujo nome não contenha "demo".

    MONITOR_DB=data/demo.db python scripts/demo_ao_vivo.py

O semeador gera sete dias até o instante em que foi chamado, e para ali. Três
minutos depois o painel já diz "A coleta parou", porque é isso que ele tem de
dizer quando a leitura mais nova tem mais de três intervalos de idade — a
regra existe para que um número velho nunca passe por atual. Não é defeito do
painel; é o banco que parou mesmo.

Então em vez de afrouxar a regra, este script faz a coleta não parar: continua
a mesma série, com o mesmo gerador e o mesmo estado, gravando a leitura do
minuto quando o minuto chega. O que o painel mostra passa a ser verdade sobre
o banco que ele está lendo.

Continuar é diferente de semear de novo: reexecutar o semeador sortearia a
semana inteira outra vez e o gráfico daria um salto a cada minuto. Aqui o
histórico fica onde está e só cresce pela ponta.

Se ficar um tempo fora do ar — máquina suspensa, terminal fechado —, ao voltar
preenche o buraco minuto a minuto antes de retomar o ritmo, para não deixar
uma falha na série que a demonstração não tem como explicar.
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from semear_realista import (  # noqa: E402
    CHAVE_RECUO, CSV_PADRAO, SECAGEM_AR, SP, TEMPERATURA_MAXIMA,
    Gerador, carregar, sortear_picos,
)

# Os picos de conversa são sorteados com semente fixa para sobreviverem a um
# reinício: sem isso, parar e voltar poderia mudar os picos de hoje, e um
# gráfico que muda o passado é um gráfico em que não se confia.
SEMENTE_PICOS = 20261112


def recuo_guardado() -> float:
    """O recuo de temperatura que o semeador aplicou à semana inteira."""
    with database.conectar() as conexao:
        linha = conexao.execute(
            "SELECT valor FROM configuracao WHERE chave = ?", (CHAVE_RECUO,)
        ).fetchone()

    return float(linha["valor"]) if linha else 0.0


def ultimo_minuto() -> datetime | None:
    with database.conectar() as conexao:
        linha = conexao.execute("SELECT MAX(ts) AS ts FROM leituras").fetchone()

    if not linha or linha["ts"] is None:
        return None

    return datetime.fromtimestamp(linha["ts"], tz=SP)


def continuar(csv_real: Path, verboso: bool = True) -> None:
    ar_real, ruido_real = carregar(csv_real)

    recuo = recuo_guardado()
    ultimo = ultimo_minuto()
    if ultimo is None:
        print("RECUSADO: o banco está vazio. Rode scripts/semear_realista.py antes.")
        raise SystemExit(1)

    partida = database.ultima_leitura()
    # Desfaz os ajustes de apresentação para o gerador retomar na grandeza em
    # que ele trabalha. São dois deslocamentos de valor fixo, então a volta é
    # exata.
    temp = round(partida["temperatura"] + recuo, 1)
    umid = round(partida["umidade"] + SECAGEM_AR, 1)

    random.seed(SEMENTE_PICOS)
    picos = sortear_picos(ultimo - timedelta(days=1),
                          ultimo + timedelta(days=30))
    random.seed()

    g = Gerador(ar_real, ruido_real, picos, temp=temp, umid=umid)

    print(f"Banco: {config.DB_PATH}")
    print(f"Retomando de {ultimo:%d/%m %H:%M} em {temp} °C e {umid} %"
          f" (recuo de {recuo} °C)")

    quando = ultimo + timedelta(minutes=1)
    atrasado = 0

    while True:
        agora = datetime.now(tz=SP)

        if quando > agora:
            # Dorme até o minuto virar. Meio segundo de folga para o relógio
            # já ter passado da marca quando acordar.
            time.sleep(max((quando - agora).total_seconds() + 0.5, 0.5))
            continue

        temp, umid, laeq, lamax, lamin = g.minuto(quando)

        # O mesmo teto e a mesma secagem que o semeador aplicou. O teto é o
        # ar-condicionado da ficção; sem ele, a deriva lenta acabaria furando
        # os 24 °C declarados.
        temp = min(round(temp - recuo, 1), TEMPERATURA_MAXIMA)
        umid = round(umid - SECAGEM_AR, 1)

        ts = int(quando.timestamp())
        database.gravar(temp, umid, ts=ts)
        database.gravar_ruido(laeq, lamax, lamin, ts=ts)

        vencido = (agora - quando).total_seconds() > 90
        if vencido:
            atrasado += 1
        else:
            if atrasado and verboso:
                print(f"  {atrasado} minuto(s) de buraco preenchidos")
            atrasado = 0
            if verboso:
                print(f"{quando:%d/%m %H:%M}  {temp} °C  {umid} %  "
                      f"{laeq + database.offset_ruido():.1f} dB(A)")

        quando += timedelta(minutes=1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=CSV_PADRAO)
    p.add_argument("--silencioso", action="store_true")
    args = p.parse_args()

    if "demo" not in str(config.DB_PATH):
        print(f"RECUSADO: {config.DB_PATH} não parece banco de demonstração.")
        raise SystemExit(1)

    if not args.csv.exists():
        print(f"RECUSADO: não achei o arquivo real em {args.csv}")
        raise SystemExit(1)

    try:
        continuar(args.csv, verboso=not args.silencioso)
    except KeyboardInterrupt:
        print("\nParado.")


if __name__ == "__main__":
    main()
