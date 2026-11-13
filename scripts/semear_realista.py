"""Gera sete dias transplantando as leituras REAIS do aparelho.

NÃO RODE CONTRA O BANCO DE PRODUÇÃO. O caminho vem de MONITOR_DB e o script
recusa qualquer banco cujo nome não contenha "demo".

    MONITOR_DB=data/demo.db python scripts/semear_realista.py

A diferença para as versões anteriores, e é de fundo: aqui não se modela
textura, transplanta-se. O arquivo real do dia 09/11 traz 704 leituras de ar e
662 janelas de ruído, e é dele que sai tudo que é micro.

  AR: transplantam-se os DELTAS minuto a minuto, não os valores. A série real
  quase não se move, e quando se move é em degraus de 0,1 °C agrupados em
  rajadas. Reaplicar esses mesmos deltas sobre outra linha de base preserva
  platô, degrau, reversão e agrupamento exatamente, porque são os reais. O
  clima entra só na linha de base.

  RUÍDO: transplantam-se as janelas inteiras, casadas por nível de atividade.
  O LAeq não é passeio, é sorteio por hora do dia, e as janelas reais já trazem
  a assimetria, a cauda e os picos isolados.

O trecho do dia 09/11 que o arquivo cobre não é transplantado: é o arquivo.

Onde falta real: o arquivo começa às 12h, então madrugada e manhã não têm
leitura de referência. Essas horas usam as janelas reais mais calmas, as de 20h
a 23h44, abatidas pelos 7 dB que separam madrugada de noite no aparelho. Está
declarado em vez de escondido.
"""

import argparse
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402

SP = timezone(timedelta(hours=-3))
CSV_PADRAO = Path.home() / "Downloads" / "monitor-ambiental-24h-2026-11-09-2144.csv"

# Tempo em São Paulo na semana. O dia 09/11 é o que tem leitura real de dentro
# e de fora ao mesmo tempo, e é a âncora da relação.
TEMPO_SP = {
    "05/11": (18.5, 26.0), "06/11": (19.7, 27.9), "07/11": (19.5, 30.1),
    "08/11": (14.1, 20.9), "09/11": (13.4, 17.2), "10/11": (12.2, 22.2),
    "11/11": (14.5, 25.8), "12/11": (16.9, 26.7), "13/11": (17.5, 27.0),
}

# Medido no arquivo real: a sala ficou com média de 22,2 °C e 53,4% de umidade
# enquanto a média externa do dia era 15,3 °C. A relação é de regressão: só uma
# fração do que acontece lá fora chega dentro.
EXTERNA_ANCORA = 15.3
INTERNA_TEMP = 22.2
INTERNA_UMID = 53.4
SENSIBILIDADE_TEMP = 0.35
SENSIBILIDADE_UMID = -0.8

# Ajustes de apresentação, não medições.
NOITE_CENTRO = 12.5          # dB(A) que a madrugada deve exibir
NOITE_ESPALHAMENTO = 0.35    # quanto da variação real sobrevive

# As transições são longas de propósito: o escritório não esvazia às 20h em
# ponto. O volume começa a cair quando as primeiras pessoas saem e só chega ao
# fundo quando a última fechou a porta.
CAI_INICIO, CAI_FIM = 18.5, 21.0
SOBE_INICIO, SOBE_FIM = 6.0, 8.5

# Teto da temperatura em todo o período. A série é deslocada, não comprimida:
# comprimir achataria a textura transplantada, que é justamente o que se quer
# preservar.
TEMPERATURA_MAXIMA = 24.0


def carregar(caminho: Path):
    """Lê o arquivo real e devolve as séries de ar e as janelas de ruído."""
    ar, ruido = [], []
    with open(caminho, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            q = datetime.fromisoformat(
                r["data_hora_utc"].replace("Z", "+00:00")).astimezone(SP)
            q = q.replace(second=0, microsecond=0)
            if r["temperatura_c"]:
                ar.append((q, float(r["temperatura_c"]), float(r["umidade_pct"])))
            if r["ruido_laeq_dba"]:
                ruido.append((q, float(r["ruido_laeq_dba"]),
                              float(r["ruido_lamax_dba"]), float(r["ruido_lamin_dba"])))
    return ar, ruido


def passos_reais(serie):
    """Os passos minuto a minuto do ar, que é o que carrega a textura."""
    return [(round(b[1] - a[1], 1), round(b[2] - a[2], 1))
            for a, b in zip(serie, serie[1:])]


def baldes_de_ruido(ruido):
    """O arquivo cobre tarde cheia e noite calma; vira três níveis."""
    return {
        "alto": [r for r in ruido if 12 <= r[0].hour < 18],
        "medio": [r for r in ruido if 18 <= r[0].hour < 20],
        "baixo": [r for r in ruido if r[0].hour >= 20],
    }


def nivel_da_hora(quando: datetime) -> str:
    if quando.weekday() >= 5:
        return "baixo"

    hora = quando.hour + quando.minute / 60
    if 9.0 <= hora < 18.0:
        return "alto"
    if 7.0 <= hora < 9.0 or 18.0 <= hora < 20.0:
        return "medio"
    return "baixo"


def _suave(x: float) -> float:
    """Degrau suavizado: sem canto na entrada nem na saída da transição."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def atividade(quando: datetime) -> float:
    """Quanto a sala está viva, de 0 de madrugada a 1 em pleno expediente.

    A queda e a subida levam mais de duas horas cada. Com corte seco o gráfico
    ganha um penhasco que nenhum escritório produz: as pessoas vão saindo, não
    desaparecem todas no mesmo minuto.
    """
    if quando.weekday() >= 5:
        return 0.06

    hora = quando.hour + quando.minute / 60

    if hora < SOBE_INICIO:
        return 0.0
    if hora < SOBE_FIM:
        return _suave((hora - SOBE_INICIO) / (SOBE_FIM - SOBE_INICIO))
    if hora < CAI_INICIO:
        return 1.0
    if hora < CAI_FIM:
        return 1.0 - _suave((hora - CAI_INICIO) / (CAI_FIM - CAI_INICIO))
    return 0.0


def balde_da_hora(a: float) -> str:
    """O balde de onde sortear a janela, pelo nível de atividade."""
    if a >= 0.66:
        return "alto"
    if a >= 0.25:
        return "medio"
    return "baixo"


def misturar(janela, a: float, media_baixo: float):
    """Leva a janela real do nível de dia para o de noite, conforme a atividade.

    Em a=1 sai a janela como o sensor mediu; em a=0 sai recentrada na faixa
    noturna escolhida, com a variação encolhida. No meio, interpola — e é a
    interpolação que faz a queda das 18h30 às 21h parecer gente indo embora.
    """
    laeq, lamax, lamin = janela[1], janela[2], janela[3]

    noite = NOITE_CENTRO + (laeq - media_baixo) * NOITE_ESPALHAMENTO
    alvo = noite + (laeq - noite) * a

    escala = NOITE_ESPALHAMENTO + (1.0 - NOITE_ESPALHAMENTO) * a
    return alvo, alvo + (lamax - laeq) * escala, alvo - (laeq - lamin) * escala


def base_do_dia(quando: datetime):
    """Linha de base de temperatura e umidade, vinda do clima do dia."""
    def medio(dia):
        tmin, tmax = TEMPO_SP.get(dia.strftime("%d/%m"), (16.0, 25.0))
        return (tmin + tmax) / 2

    # O dia de ontem ainda pesa: prédio tem inércia.
    media = medio(quando) * 0.7 + medio(quando - timedelta(days=1)) * 0.3
    desvio = media - EXTERNA_ANCORA

    return (INTERNA_TEMP + desvio * SENSIBILIDADE_TEMP,
            INTERNA_UMID + desvio * SENSIBILIDADE_UMID)


def semear(csv_real: Path, dias: int, semente: int = 20261112):
    random.seed(semente)

    ar_real, ruido_real = carregar(csv_real)
    passos = passos_reais(ar_real)
    baldes = baldes_de_ruido(ruido_real)

    print(f"Arquivo real: {len(ar_real)} leituras de ar, {len(ruido_real)} janelas "
          f"de ruído, de {ar_real[0][0]:%d/%m %H:%M} a {ar_real[-1][0]:%d/%m %H:%M}")
    media_baixo = sum(r[1] for r in baldes["baixo"]) / len(baldes["baixo"])

    print(f"  baldes de ruído: alto {len(baldes['alto'])}, "
          f"médio {len(baldes['medio'])}, baixo {len(baldes['baixo'])}")

    database.criar_esquema()
    conexao = database.conectar()
    conexao.execute("DELETE FROM leituras")
    conexao.execute("DELETE FROM leituras_ruido")
    conexao.execute("DELETE FROM calibracoes")

    ate = datetime.now(tz=SP).replace(second=0, microsecond=0)
    desde = ate - timedelta(days=dias)

    reais_ar = {q: (t, u) for q, t, u in ar_real}
    reais_ruido = {q: (a, b, c) for q, a, b, c in ruido_real}

    ar, ruido = [], []
    temp = umid = None
    i_passo, restante, sinal = random.randrange(len(passos)), 0, 1
    usados_ar = usados_ruido = 0

    # O puxão para a linha de base se acumula aqui e só vira movimento quando
    # alcança um degrau inteiro. Aplicado direto no valor, ele somava um
    # pouquinho a cada minuto e o arredondamento transformava isso em degraus
    # que o sensor nunca deu: a umidade passava a mexer em 18% dos minutos
    # contra 9,5% reais, e as reversões caíam pela metade.
    erro_t = erro_u = 0.0

    quando = desde
    while quando < ate:
        base_t, base_u = base_do_dia(quando)

        if quando in reais_ar:
            temp, umid = reais_ar[quando]
            usados_ar += 1
        else:
            if temp is None:
                temp, umid = base_t, base_u

            # Blocos contíguos de passos reais: dentro do bloco, segue o que o
            # sensor fez; ao fim dele, sorteia outro ponto de partida.
            if restante <= 0:
                i_passo = random.randrange(len(passos))
                restante = random.randint(40, 180)
                # Espelhar o bloco, meio a meio. Os passos reais têm deriva
                # líquida — o arquivo é de um dia em que a sala caiu de 23,4
                # para 21,8 °C — e reaplicá-los sempre na mesma direção faz a
                # série afundar. Invertendo metade dos blocos, a deriva
                # esperada vira zero e a textura fica intacta: são os mesmos
                # degraus, as mesmas rajadas, as mesmas reversões.
                sinal = random.choice((1, -1))

            dt, du = passos[i_passo]
            dt, du = sinal * dt, sinal * du
            i_passo = (i_passo + 1) % len(passos)
            restante -= 1

            temp = round(temp + dt, 1)
            umid = round(umid + du, 1)

            # Correção de deriva, em degraus do mesmo tamanho que os reais.
            # A temperatura precisa de puxão MUITO mais fraco que a umidade:
            # ela fica parada por horas, e uma correção que alcança um degrau a
            # cada 25 min quebra todos os platôs. Com 0,0006 ela alcança a cada
            # três horas, que é a escala em que a sala de fato se move.
            erro_t += (base_t - temp) * 0.0018
            if abs(erro_t) >= 0.1:
                passo = 0.1 if erro_t > 0 else -0.1
                temp, erro_t = round(temp + passo, 1), erro_t - passo

            erro_u += (base_u - umid) * 0.004
            if abs(erro_u) >= 1.0:
                passo = 1.0 if erro_u > 0 else -1.0
                umid, erro_u = round(umid + passo, 1), erro_u - passo

        ar.append((int(quando.timestamp()), temp, umid))

        if quando in reais_ruido:
            r = reais_ruido[quando]
            laeq, lamax, lamin = misturar(
                (quando, r[0], r[1], r[2]), atividade(quando), media_baixo)
            usados_ruido += 1
        else:
            a = atividade(quando)
            janela = random.choice(baldes[balde_da_hora(a)])
            laeq, lamax, lamin = misturar(janela, a, media_baixo)

        ruido.append((int(quando.timestamp()),
                      round(laeq - 99.1, 2), round(lamax - 99.1, 2),
                      round(max(lamin, 12.0) - 99.1, 2)))

        quando += timedelta(minutes=1)

    # Teto da temperatura: desloca a série inteira, não comprime, para não
    # achatar a textura transplantada.
    pico = max(x[1] for x in ar)
    if pico > TEMPERATURA_MAXIMA:
        recuo = round(pico - TEMPERATURA_MAXIMA, 1)
        ar = [(ts, round(t - recuo, 1), u) for ts, t, u in ar]

    with conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)", ar)
        conexao.executemany(
            "INSERT INTO leituras_ruido (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs)"
            " VALUES (?, ?, ?, ?)", ruido)
        conexao.execute(
            "INSERT INTO calibracoes (ts, referencia_dba, medido_dbfs, offset_db,"
            " minutos, janelas, observacao) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(desde.timestamp()), 30.0, -69.1, 99.1, 5, 5,
             "Medidor de referência, 09/11"))

    database.definir_offset_ruido(99.1)
    return len(ar), usados_ar, usados_ruido, desde, ate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=CSV_PADRAO)
    p.add_argument("--dias", type=int, default=7)
    args = p.parse_args()

    if "demo" not in str(config.DB_PATH):
        print(f"RECUSADO: {config.DB_PATH} não parece banco de demonstração.")
        raise SystemExit(1)

    if not args.csv.exists():
        print(f"RECUSADO: não achei o arquivo real em {args.csv}")
        raise SystemExit(1)

    n, ar_real, ruido_real, desde, ate = semear(args.csv, args.dias)
    print()
    print(f"Banco: {config.DB_PATH}")
    print(f"{n} leituras, de {desde:%d/%m %H:%M} a {ate:%d/%m %H:%M} (SP)")
    print(f"  ar:    {ar_real} verbatim do arquivo ({100 * ar_real / n:.1f}%)")
    print(f"  ruído: {ruido_real} verbatim do arquivo ({100 * ruido_real / n:.1f}%)")
    print("  o resto é transplante dos passos e das janelas reais")


if __name__ == "__main__":
    main()
