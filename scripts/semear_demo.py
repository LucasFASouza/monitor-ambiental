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
    # 96,3% dos passos minuto a minuto do DHT11 são exatamente zero: o sensor
    # segura o valor e se move em degraus. Os degraus observados foram 0,1 a
    # 1,1 °C, com desvio padrão de passo de 0,049.
    "temp_passo_parado": 0.963,
    "temp_degraus": [0.1, 0.1, 0.1, 0.2, 0.2, 0.3, 0.4, 0.5, 0.8],
    # 95,2% de passos zero, e os degraus são meio ponto ou pontos inteiros.
    "umid_passo_parado": 0.952,
    "umid_degraus": [0.5, 1.0, 1.0, 1.0, 2.0, 3.0],
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

    Fora do horário do ar-condicionado a sala deriva na direção do externo,
    bem amortecida — nos dados reais, oscilações externas de 10 a 14 °C viraram
    0,8 a 1,6 °C lá dentro, cerca de dez vezes menos.

    Com o ar ligado, a sala é puxada para o setpoint. Mas o ar tem limite: com
    o escritório cheio e calor lá fora, a carga térmica das pessoas e dos
    equipamentos ganha da máquina e a sala sobe acima dos 22 °C.
    """
    hora = quando.hour + quando.minute / 60
    # O ar é de dia útil: num escritório formal ninguém climatiza sala vazia no
    # sábado. É por isso que o fim de semana quente assa lá dentro.
    ar_ligado = AR_LIGA <= hora < AR_DESLIGA and quando.weekday() < 5

    if anterior is None:
        return (AR_ALVO if ar_ligado else externo_t * 0.35 + 21.0,
                max(35.0, min(75.0, externo_u * 0.45 + 28.0)))

    temp, umid = anterior

    # Carga térmica: cada pessoa aquece, e o sol de fora empurra junto. O
    # acoplamento é forte o bastante para a terça cheia se separar da sexta
    # vazia, que é justamente o que a demonstração precisa mostrar.
    ganho_pessoas = 4.2 * ocupacao
    ganho_externo = max(0.0, externo_t - AR_ALVO) * 0.16

    if ar_ligado:
        # O ar persegue o alvo, mas só compensa parte da carga: com a sala
        # cheia e calor lá fora, a máquina perde e a sala sobe dos 22 °C.
        alvo = AR_ALVO + (ganho_pessoas + ganho_externo) * 0.52
        temp += (alvo - temp) * 0.06
    else:
        # Sem ar, a sala caminha para o externo amortecido pela massa do
        # prédio. O alvo tem de ficar ABAIXO do setpoint quando está frio lá
        # fora, senão a madrugada sai mais quente que a tarde.
        alvo = 21.0 + (externo_t - 20.0) * 0.28 + ganho_pessoas * 0.45
        temp += (alvo - temp) * 0.015

    # O ar-condicionado desumidifica; as pessoas umidificam de volta.
    if ar_ligado:
        alvo_u = externo_u * 0.28 + 30.0 - 6.0 + 9.0 * ocupacao
        umid += (alvo_u - umid) * 0.05
    else:
        alvo_u = externo_u * 0.42 + 26.0
        umid += (alvo_u - umid) * 0.012

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

def _degrau(valor_alvo, valor_atual, parado, degraus, casas):
    """Segura o valor e muda em degraus, como o DHT11 faz de verdade."""
    if random.random() < parado:
        return valor_atual

    delta = valor_alvo - valor_atual
    if abs(delta) < 0.05:
        return valor_atual

    degrau = random.choice(degraus)
    passo = math.copysign(min(degrau, abs(delta)), delta)
    return round(valor_atual + passo, casas)


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

        if temp_vista is None:
            temp_vista, umid_vista = round(estado[0], 1), round(estado[1])

        temp_vista = _degrau(estado[0], temp_vista,
                             TEXTURA["temp_passo_parado"], TEXTURA["temp_degraus"], 1)
        umid_vista = _degrau(estado[1], umid_vista,
                             TEXTURA["umid_passo_parado"], TEXTURA["umid_degraus"], 0)

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
