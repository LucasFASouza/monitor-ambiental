"""Gera um histórico simulado de um escritório formal, para demonstração.

NÃO RODE ISTO CONTRA O BANCO DE PRODUÇÃO. Os registros gerados são
indistinguíveis dos reais depois de gravados. O caminho do banco vem de
MONITOR_DB, e o padrão deste script é `data/demo.db`, separado de propósito.

    MONITOR_DB=data/demo.db python scripts/semear_demo.py

O cenário: escritório com ar-condicionado automático das 6h às 19h em 22 °C,
pessoas chegando entre 8h e 10h, saindo e voltando do almoço entre 12h e 14h, e
indo embora entre 17h45 e 19h30 com o grosso por volta de 18h30. Terça e quinta
são os dias cheios; quarta é intermediária; segunda e sexta são os mais vazios.

O tempo externo é o de Mogi das Cruzes. Onde houve dado de estação ele foi
usado; onde não houve, está interpolado a partir da previsão do mês e dos dois
extremos nomeados. Ver TEMPO_EXTERNO.

A aleatoriedade NÃO é arbitrária: a textura estatística sai medida dos dados
reais coletados pelo aparelho, em `TEXTURA`. É o que faz a série parecer sensor
e não seno.
"""

import argparse
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402

SP = timezone(timedelta(hours=-3))


# --- textura medida nos dados reais -----------------------------------------
#
# Levantada sobre 5.913 leituras de ar e 2.970 janelas de ruído do aparelho em
# operação. Sem isto a série simulada vira uma curva lisa, que não se parece
# com sensor nenhum.

TEXTURA = {
    # O DHT11 não acompanha o ambiente continuamente: ele segura um valor e só
    # mexe quando a diferença fica grande o bastante. Medido no aparelho real,
    # 85% do tempo a temperatura está num platô de mais de uma hora, com platôs
    # de até 9,1 h; na umidade são 59% do tempo, com platôs de até 8,1 h.
    #
    # Por isso o valor exibido é uma banda morta sobre o modelo, e não um
    # sorteio a cada minuto. Sorteio produz uma curva lisa quantizada; banda
    # morta produz platôs longos, que é o que o sensor faz.
    "temp_limiar": 0.35,
    "temp_degrau": 0.2,
    "umid_limiar": 1.3,
    "umid_degrau": 1.0,
    # O LAeq de 60 s mexe de verdade: desvio padrão de 4,76 dB de um minuto
    # para o outro, e 6,73 dB no nível.
    "ruido_passo_desvio": 4.76,
    # O máximo da janela fica em média 7,6 dB acima do LAeq, e o mínimo 5,9 dB
    # abaixo. São as duas pontas do envelope que o gráfico desenha.
    "ruido_max_acima": (7.6, 3.4),
    "ruido_min_abaixo": (5.9, 4.8),
}

# Offset de calibração do aparelho real, para a demo nascer calibrada.
OFFSET_DB = 99.1


# --- tempo externo em Mogi das Cruzes ---------------------------------------
#
# (mínima, máxima, umidade mínima, umidade máxima, chuva)
#
# Dias com dado de estação do CIIAGRO (Mogi das Cruzes - Cocuera), em janelas
# de 07h a 07h: 02, 03 e 04/11. Os demais são interpolados a partir da previsão
# do mês (máxima média 24,2 °C, mínima média 16,2 °C) e dos dois extremos
# nomeados: 07/11 o dia mais quente, 10/11 o mais ameno. 11/11 segue o
# observado na capital, com garoa.

TEMPO_EXTERNO = {
    "02/11": (15.0, 25.0, 59, 99, False),   # estação
    "03/11": (16.0, 31.0, 31, 99, False),   # estação
    "04/11": (16.0, 29.0, 38, 97, False),   # estação, atenuado
    "05/11": (17.0, 28.0, 42, 95, False),   # interpolado
    "06/11": (18.0, 32.0, 35, 93, False),   # interpolado, subindo para o pico
    "07/11": (19.0, 35.0, 28, 90, False),   # dia mais quente do mês
    "08/11": (17.0, 27.0, 45, 96, True),    # interpolado, virada
    "09/11": (14.0, 22.0, 58, 98, True),    # interpolado, frente fria
    "10/11": (11.6, 21.0, 60, 99, False),   # dia mais ameno do mês
    "11/11": (15.0, 26.0, 48, 97, True),    # garoa, como na capital
}


# --- ocupação ----------------------------------------------------------------

# Quanto do escritório enche em cada dia da semana. Terça e quinta são os dias
# cheios porque menos gente fica em casa; quarta é intermediária; segunda e
# sexta são os mais vazios.
LOTACAO = {0: 0.42, 1: 1.00, 2: 0.62, 3: 1.00, 4: 0.36, 5: 0.02, 6: 0.0}

AR_LIGA, AR_DESLIGA, AR_ALVO = 6.0, 19.0, 22.0


def _ocupacao(hora: float, dia_da_semana: int) -> float:
    """Fração do escritório ocupada, de 0 a 1, na hora decimal informada."""
    teto = LOTACAO[dia_da_semana]
    if teto <= 0.02:
        return teto

    def rampa(x, inicio, fim):
        if x <= inicio:
            return 0.0
        if x >= fim:
            return 1.0
        return (x - inicio) / (fim - inicio)

    # Chegada: o grosso entre 8h e 9h30, retardatários até 10h.
    chegou = 0.85 * rampa(hora, 8.0, 9.5) + 0.15 * rampa(hora, 9.5, 10.0)

    # Almoço: sai entre 12h e 13h, volta entre 13h e 14h. No fundo do vale
    # sobra pouca gente, não ninguém.
    saiu = rampa(hora, 12.0, 13.0)
    voltou = rampa(hora, 13.0, 14.0)
    no_almoco = max(0.0, saiu - voltou) * 0.75

    # Saída: começa 17h45, o grosso às 18h30, os últimos às 19h30.
    foi = 0.2 * rampa(hora, 17.75, 18.5) + 0.65 * rampa(hora, 18.5, 18.75) \
        + 0.15 * rampa(hora, 18.75, 19.5)

    return max(0.0, teto * (chegou - no_almoco - foi))


# --- tempo externo, hora a hora ----------------------------------------------

def _externo(quando: datetime) -> tuple[float, float]:
    """Temperatura e umidade externas na hora informada."""
    dia = TEMPO_EXTERNO.get(quando.strftime("%d/%m"))
    if dia is None:
        dia = (16.0, 25.0, 50, 95, False)

    tmin, tmax, umin, umax, _chuva = dia
    hora = quando.hour + quando.minute / 60

    # Mínima pouco antes do nascer do sol, máxima no meio da tarde.
    fase = (hora - 15.0) / 24 * 2 * math.pi
    onda = (math.cos(fase) + 1) / 2          # 1 às 15h, 0 às 3h
    temp = tmin + (tmax - tmin) * onda

    # Umidade anda ao contrário da temperatura: alta de madrugada, baixa no
    # pico de calor.
    umid = umax - (umax - umin) * onda

    return temp, umid


# --- modelo do ambiente interno ----------------------------------------------

def _interno(quando: datetime, externo_t: float, externo_u: float,
             ocupacao: float, anterior: tuple[float, float] | None):
    """Temperatura e umidade dentro da sala.

    A sala NÃO segue o cosseno externo amortecido. Ela é controlada, e isso dá
    uma forma diferente:

    - com o ar ligado, a máquina segura o setpoint e a sala fica praticamente
      plana. O que a tira dos 22 °C é a carga térmica que o ar não dá conta de
      remover: gente e sol. Logo, a curva sobe em patamares conforme o
      escritório enche, não conforme o sol anda;
    - de madrugada o ar está desligado e a sala relaxa com constante de tempo
      de horas. Nos dados reais ela ficou em 21,0 °C parada por oito horas
      seguidas, com o lado de fora a 12 °C. Prédio tem massa.

    Modelar isso como seno amortecido do externo produz exatamente a senoide
    que não existe nos dados.
    """
    hora = quando.hour + quando.minute / 60
    ar_ligado = AR_LIGA <= hora < AR_DESLIGA and quando.weekday() < 5

    if anterior is None:
        return 22.5, 55.0

    temp, umid = anterior

    if ar_ligado:
        # Carga térmica que a máquina precisa vencer. Ela dá conta de uma
        # parte; o excedente é o que vira temperatura acima do setpoint.
        carga = 3.0 * ocupacao + max(0.0, externo_t - 27.0) * 0.30
        # O ar remove a maior parte da carga: um escritório formal cujo ar
        # deixa a sala subir 4 °C acima do setpoint tem ar quebrado. O que
        # sobra é 1 a 3 °C nos dias cheios e quentes, e nada nos vazios — é
        # essa sobra que separa terça de sexta no gráfico.
        folga = 1.2
        alvo = AR_ALVO + max(0.0, carga - folga)

        # Constante de tempo de ~25 min: o ar reage rápido, mas não instantâneo.
        temp += (alvo - temp) * 0.04

        # O ar desumidifica para um patamar próprio; as pessoas devolvem vapor.
        alvo_u = 44.0 + 11.0 * ocupacao + max(0.0, externo_u - 80.0) * 0.10
        umid += (alvo_u - umid) * 0.03
    else:
        # Relaxação lenta, com a massa do prédio segurando. O alvo fica perto
        # do setpoint, não perto do externo: é o que os dados mostram.
        alvo = 0.30 * externo_t + 0.70 * 21.3
        temp += (alvo - temp) * 0.0030

        alvo_u = 0.30 * externo_u + 0.70 * 56.0
        umid += (alvo_u - umid) * 0.0030

    return temp, max(30.0, min(80.0, umid))


def _ruido_dba(quando: datetime, ocupacao: float) -> float:
    """Nível de ruído de fundo esperado, em dB(A), antes do grão aleatório."""
    hora = quando.hour + quando.minute / 60
    ar_ligado = AR_LIGA <= hora < AR_DESLIGA and quando.weekday() < 5

    # Sala vazia e silenciosa de madrugada; com o ar ligado, a própria máquina
    # já põe um piso de ventilação.
    base = 41.0 if ar_ligado else 33.0

    # Gente conversando e teclando. A relação não é linear: dobrar o número de
    # pessoas não dobra o nível, soma uns 3 dB.
    if ocupacao > 0:
        base += 10 * math.log10(1 + 14 * ocupacao)

    # Hora do almoço no escritório é mais barulhenta por pessoa.
    if 12.0 <= hora < 14.0:
        base += 1.5

    return base


# --- grão: o que faz parecer sensor ------------------------------------------

def _mostrar(alvo, atual, limiar, degrau, casas):
    """O valor que o sensor exibe: banda morta sobre o modelo.

    Só mexe quando o ambiente se afastou mais que `limiar` do que está escrito,
    e aí anda um degrau. Com o modelo plano, o valor fica plano por horas — que
    é o que o sensor real faz. Com o modelo em rampa, vira escada.
    """
    if atual is None:
        return round(alvo, casas)

    delta = alvo - atual
    if abs(delta) < limiar:
        return atual

    return round(atual + math.copysign(degrau, delta), casas)


def semear(desde: datetime, ate: datetime, semente: int = 20261102) -> tuple[int, int]:
    random.seed(semente)
    database.criar_esquema()

    conexao = database.conectar()
    conexao.execute("DELETE FROM leituras")
    conexao.execute("DELETE FROM leituras_ruido")
    conexao.execute("DELETE FROM calibracoes")

    ar, ruido = [], []
    estado = None
    temp_vista = umid_vista = None
    laeq_anterior = None

    quando = desde
    while quando < ate:
        ext_t, ext_u = _externo(quando)
        ocup = _ocupacao(quando.hour + quando.minute / 60, quando.weekday())
        estado = _interno(quando, ext_t, ext_u, ocup, estado)

        temp_vista = _mostrar(estado[0], temp_vista,
                              TEXTURA["temp_limiar"], TEXTURA["temp_degrau"], 1)
        umid_vista = _mostrar(estado[1], umid_vista,
                              TEXTURA["umid_limiar"], TEXTURA["umid_degrau"], 0)

        ar.append((int(quando.timestamp()), temp_vista, float(umid_vista)))

        # Ruído: passeio aleatório em torno do nível esperado, com o desvio de
        # passo medido no aparelho real.
        alvo = _ruido_dba(quando, ocup)
        if laeq_anterior is None:
            laeq_anterior = alvo
        laeq = laeq_anterior + (alvo - laeq_anterior) * 0.22 + \
            random.gauss(0, TEXTURA["ruido_passo_desvio"] * 0.92)
        laeq = max(28.0, min(78.0, laeq))
        laeq_anterior = laeq

        acima = max(1.0, random.gauss(*TEXTURA["ruido_max_acima"]))
        abaixo = max(1.0, random.gauss(*TEXTURA["ruido_min_abaixo"]))

        ruido.append((
            int(quando.timestamp()),
            round(laeq - OFFSET_DB, 2),
            round(laeq + acima - OFFSET_DB, 2),
            round(laeq - abaixo - OFFSET_DB, 2),
        ))

        quando += timedelta(minutes=1)

    with conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)", ar)
        conexao.executemany(
            "INSERT INTO leituras_ruido (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs)"
            " VALUES (?, ?, ?, ?)", ruido)
        # A demo nasce calibrada, com ficha de rastreabilidade.
        conexao.execute(
            "INSERT INTO calibracoes (ts, referencia_dba, medido_dbfs, offset_db,"
            " minutos, janelas, observacao) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(desde.timestamp()), 48.0, 48.0 - OFFSET_DB, OFFSET_DB, 10, 10,
             "Decibelímetro Tipo 2, demonstração"),
        )

    database.definir_offset_ruido(OFFSET_DB)
    return len(ar), len(ruido)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--de", default="2026-11-02", help="primeiro dia, AAAA-MM-DD")
    p.add_argument("--ate", default=None, help="último instante; padrão é agora")
    args = p.parse_args()

    desde = datetime.fromisoformat(args.de).replace(tzinfo=SP)
    ate = (datetime.fromisoformat(args.ate).replace(tzinfo=SP) if args.ate
           else datetime.now(tz=SP).replace(second=0, microsecond=0))

    if "demo" not in str(config.DB_PATH):
        print(f"RECUSADO: {config.DB_PATH} não parece banco de demonstração.")
        print("Rode com MONITOR_DB=data/demo.db para não escrever em dado real.")
        raise SystemExit(1)

    n_ar, n_ruido = semear(desde, ate)
    print(f"Banco: {config.DB_PATH}")
    print(f"{n_ar} leituras de ar e {n_ruido} janelas de ruído")
    print(f"de {desde:%d/%m %H:%M} a {ate:%d/%m %H:%M} (horário de São Paulo)")


if __name__ == "__main__":
    main()
