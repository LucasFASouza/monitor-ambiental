"""Gera sete dias de histórico calibrado contra a saída real dos sensores.

NÃO RODE CONTRA O BANCO DE PRODUÇÃO. O caminho vem de MONITOR_DB e o script
recusa qualquer banco cujo nome não contenha "demo".

    MONITOR_DB=data/demo.db python scripts/semear_realista.py

A diferença para `semear_demo.py`: aquele inventa um escritório com
ar-condicionado e ocupação declarada, para demonstrar um cenário. Este parte do
que o aparelho de fato mediu e estende pelo tempo de São Paulo, para a série
parecer o que o sensor produz.

Todos os números em MEDIDO saem de uma exportação real de 24 h do aparelho,
704 leituras de ar e 662 janelas de ruído do dia 09/11/2026. Nada aqui é
estimado no olho.
"""

import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402

SP = timezone(timedelta(hours=-3))


# --- o que o aparelho realmente produz --------------------------------------

MEDIDO = {
    # TEMPERATURA. Mexe em 6,4% dos minutos e inverte a direção em 64% dos
    # movimentos: são rajadas curtas de ida e volta dentro de platôs longos,
    # com platô máximo de 145 min. Os degraus observados foram 0,1 (22 vezes),
    # 0,2 (9), 0,3 (8) e 0,4 (6).
    "temp_banda": 0.13,
    "temp_passo_maximo": 0.4,
    "temp_grade": 0.1,
    "temp_oscilacao": 0.105,

    # UMIDADE. É MUITO mais ativa que a temperatura, e tratá-las igual foi o
    # erro das versões anteriores: mexe em 9,5% dos minutos, com platô máximo
    # de 71 min e só 10% do tempo em platô acima de uma hora. O degrau é quase
    # sempre exatamente 1,0 ponto.
    "umid_banda": 0.95,
    "umid_passo_maximo": 3.0,
    "umid_grade": 1.0,
    "umid_oscilacao": 1.25,

    "oscilacao_persistencia": 0.93,

    # Agrupamento de volatilidade. O dado real tem 6,4% de minutos que mexem e
    # mesmo assim 63% do tempo em platô acima de uma hora: os movimentos são
    # AGRUPADOS, não espalhados. Oscilação de variância constante agita de
    # forma uniforme e nunca produz as duas coisas ao mesmo tempo.
    #
    # Alternar entre calmaria e agitação resolve, e corresponde ao que de fato
    # acontece numa sala: longos trechos sem ninguém, intercalados com alguém
    # passando, porta abrindo, sol entrando.
    "agitado_chance": 1 / 150,      # entrar em agitação, por minuto
    "calmo_chance": 1 / 25,         # voltar à calmaria, por minuto
    "fator_calmo": 0.22,
    "fator_agitado": 2.3,

    # RUÍDO. A descoberta que derrubou as versões anteriores: a distribuição
    # tem assimetria +1,58, ou seja, cauda longa para cima. Não é passeio
    # aleatório gaussiano — é um PISO com EVENTOS somados.
    #
    # O piso é o LAmin de cada janela: mediana de 22 dB(A) durante o dia,
    # caindo para 18,3 a 19,2 à noite, com desvio de 2 a 3.
    "piso_dia": 22.3,
    "piso_noite": 18.6,
    "piso_desvio": 2.4,

    # O excesso do LAeq sobre o piso é log-normal: mediana do LAeq em 29,7 com
    # o piso em 22, ou seja, cerca de 7,7 dB acima dele.
    "excesso_mediana": 7.7,
    "excesso_forma": 0.56,

    # Eventos isolados de um minuto: só 39% das janelas altas têm vizinha
    # imediata. 5% das janelas caem entre 40 e 45 dB(A) e 2,6% entre 45 e 50.
    "evento_chance": 0.105,
    "evento_ganho": (9.0, 5.0),

    # O máximo da janela fica 7,8 dB acima do LAeq (σ 3,6) e o mínimo 7,7 dB
    # abaixo (σ 5,2).
    "max_acima": (7.8, 3.6),
    "min_abaixo": (7.7, 5.2),
}

OFFSET_DB = 99.1


# --- tempo em São Paulo, e a relação com o lado de dentro --------------------
#
# (mínima, máxima) externas. O dia 09/11 é o que tem leitura real de dentro, e
# é dele que sai a relação usada nos outros.

TEMPO_SP = {
    "05/11": (18.5, 26.0),
    "06/11": (19.7, 27.9),
    "07/11": (19.5, 30.1),
    "08/11": (14.1, 20.9),
    "09/11": (13.4, 17.2),   # dia com leitura real de dentro
    "10/11": (12.2, 22.2),
    "11/11": (14.5, 25.8),
    "12/11": (16.9, 26.7),
}

# Medido no dia 09/11: lá fora a média foi 15,3 °C e a sala ficou em 22,2 °C de
# média, com amplitude interna de 1,6 °C contra 3,8 °C de fora.
#
# A sala não segue a oscilação diária externa, segue a MÉDIA DO DIA com uma
# diferença grande e constante. É por isso que num gráfico de sete dias o que
# aparece são patamares de alturas diferentes, e não sete ondas.
# A relação é de REGRESSÃO, não de deslocamento constante. Medido: externa
# média de 15,3 °C e sala em 22,2 °C. Tratar os 6,9 °C como diferença fixa
# projetava 31,7 °C num dia de média 24,8 — absurdo. O prédio puxa para uma
# faixa estável, então só uma fração da variação externa chega dentro.
EXTERNA_ANCORA = 15.3
INTERNA_ANCORA = 22.2
SENSIBILIDADE = 0.35

# A amplitude interna é quase toda PISO PRÓPRIO da sala, não resposta ao lado
# de fora. Extrapolar a razão de um dia só (1,6 °C internos sobre 3,8 °C
# externos, ou 0,42) projetava 4,5 °C de oscilação num dia de 10 °C externos —
# e a medição ampla, sobre vários dias, mostrou amortecimento de 10 vezes, não
# de 2,4.
#
# A conciliação: a sala tem um balanço próprio de pouco mais de um grau, vindo
# de sol, pessoas e do prédio, ao qual se soma uma fração pequena do que o
# tempo faz lá fora.
AMPLITUDE_PISO = 1.25
AMPLITUDE_RAZAO = 0.085

# A umidade de dentro ficou entre 48 e 62% num dia de garoa lá fora, com subida
# clara depois das 20h. Sala fechada é muito mais seca que a rua.
UMIDADE_BASE = 52.0
UMIDADE_SUBIDA_NOITE = 9.0


def _dia(quando: datetime) -> tuple[float, float]:
    return TEMPO_SP.get(quando.strftime("%d/%m"), (16.0, 25.0))


def _externo_medio(quando: datetime) -> float:
    tmin, tmax = _dia(quando)
    return (tmin + tmax) / 2


def _alvo_interno(quando: datetime) -> tuple[float, float]:
    """Temperatura e umidade que o ambiente persegue nesta hora."""
    hora = quando.hour + quando.minute / 60

    # A média do dia manda; a de ontem ainda pesa, porque prédio tem inércia e
    # não esquece o dia anterior de um dia para o outro.
    hoje = _externo_medio(quando)
    ontem = _externo_medio(quando - timedelta(days=1))
    media = hoje * 0.7 + ontem * 0.3
    base = INTERNA_ANCORA + (media - EXTERNA_ANCORA) * SENSIBILIDADE

    # A amplitude interna é pequena e atrasada: o mínimo de madrugada e o
    # máximo no meio da tarde, com cerca de três horas de atraso sobre a rua.
    tmin, tmax = _dia(quando)
    amplitude = AMPLITUDE_PISO + (tmax - tmin) * AMPLITUDE_RAZAO

    fase = (hora - 17.0) / 24 * 2 * math.pi
    temp = base + amplitude / 2 * math.cos(fase)

    # A umidade sobe à noite, como no dia medido. Dia quente lá fora deixa a
    # sala mais seca.
    noite = 1 / (1 + math.exp(-(hora - 20.0) / 2.2)) if hora > 12 else 0.0
    umid = UMIDADE_BASE + UMIDADE_SUBIDA_NOITE * noite - (hoje - 15.3) * 0.8

    return temp, max(35.0, min(75.0, umid))


# --- ruído: piso com eventos, não passeio aleatório --------------------------

def _piso(quando: datetime) -> float:
    hora = quando.hour + quando.minute / 60
    de_dia = 7.0 <= hora < 19.0
    return MEDIDO["piso_dia"] if de_dia else MEDIDO["piso_noite"]


def _ruido(quando: datetime) -> tuple[float, float, float]:
    """Uma janela de LAeq, com máximo e mínimo, em dB(A)."""
    piso = random.gauss(_piso(quando), MEDIDO["piso_desvio"])

    # Excesso log-normal sobre o piso: é ele que dá a cauda para cima.
    excesso = MEDIDO["excesso_mediana"] * math.exp(
        random.gauss(0, MEDIDO["excesso_forma"]))

    laeq = piso + excesso

    # Evento isolado de um minuto: porta, cadeira, alguém falando perto.
    if random.random() < MEDIDO["evento_chance"]:
        laeq += abs(random.gauss(*MEDIDO["evento_ganho"]))

    lamax = laeq + max(1.0, random.gauss(*MEDIDO["max_acima"]))
    lamin = laeq - max(1.0, random.gauss(*MEDIDO["min_abaixo"]))

    return laeq, lamax, max(14.0, lamin)


# --- o que o sensor exibe ----------------------------------------------------

def _mostrar(lido, atual, banda, grade, casas, passo_maximo):
    """Banda morta com pouso na grade, e um limite de quanto anda por vez.

    O limite importa: sem ele, quando o alvo se move rápido o valor salta dez
    pontos de uma vez, e o sensor real nunca anda mais que 0,4 °C ou 3 pontos
    de umidade por minuto. O limite transforma o salto em escada.
    """
    if atual is None:
        return round(lido, casas)

    if abs(lido - atual) < banda:
        return atual

    destino = round(lido / grade) * grade
    delta = destino - atual
    if abs(delta) > passo_maximo:
        delta = math.copysign(passo_maximo, delta)

    return round(atual + delta, casas)


def semear(desde: datetime, ate: datetime, semente: int = 20261112):
    random.seed(semente)
    database.criar_esquema()

    conexao = database.conectar()
    conexao.execute("DELETE FROM leituras")
    conexao.execute("DELETE FROM leituras_ruido")
    conexao.execute("DELETE FROM calibracoes")

    persistencia = MEDIDO["oscilacao_persistencia"]
    fator = math.sqrt(1 - persistencia ** 2)
    osc_t = osc_u = 0.0
    agitado = False
    temp_vista = umid_vista = None

    ar, ruido = [], []
    quando = desde
    while quando < ate:
        alvo_t, alvo_u = _alvo_interno(quando)

        # O regime alterna entre calmaria e agitação, com permanência longa.
        if agitado:
            if random.random() < MEDIDO["calmo_chance"]:
                agitado = False
        elif random.random() < MEDIDO["agitado_chance"]:
            agitado = True

        intensidade = MEDIDO["fator_agitado"] if agitado else MEDIDO["fator_calmo"]

        # O agrupamento vale só para a temperatura. A umidade real não agrupa:
        # mexe em 9,5% dos minutos e segura no máximo 71 min, contra 145 da
        # temperatura. São dois comportamentos diferentes, e tratá-los igual
        # era o erro — com o regime aplicado aos dois, a umidade ia a 59% de
        # tempo em platô quando o real é 10%.
        osc_t = persistencia * osc_t + random.gauss(
            0, MEDIDO["temp_oscilacao"] * fator * intensidade)
        osc_u = persistencia * osc_u + random.gauss(
            0, MEDIDO["umid_oscilacao"] * fator)

        temp_vista = _mostrar(alvo_t + osc_t, temp_vista, MEDIDO["temp_banda"],
                              MEDIDO["temp_grade"], 1, MEDIDO["temp_passo_maximo"])
        umid_vista = _mostrar(alvo_u + osc_u, umid_vista, MEDIDO["umid_banda"],
                              MEDIDO["umid_grade"], 0, MEDIDO["umid_passo_maximo"])

        ar.append((int(quando.timestamp()), temp_vista, float(umid_vista)))

        laeq, lamax, lamin = _ruido(quando)
        ruido.append((int(quando.timestamp()),
                      round(laeq - OFFSET_DB, 2),
                      round(lamax - OFFSET_DB, 2),
                      round(lamin - OFFSET_DB, 2)))

        quando += timedelta(minutes=1)

    with conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)", ar)
        conexao.executemany(
            "INSERT INTO leituras_ruido (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs)"
            " VALUES (?, ?, ?, ?)", ruido)
        conexao.execute(
            "INSERT INTO calibracoes (ts, referencia_dba, medido_dbfs, offset_db,"
            " minutos, janelas, observacao) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(desde.timestamp()), 30.0, round(30.0 - OFFSET_DB, 2), OFFSET_DB,
             5, 5, "Medidor de referência, 09/11"))

    database.definir_offset_ruido(OFFSET_DB)
    return len(ar), len(ruido)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dias", type=int, default=7)
    args = p.parse_args()

    if "demo" not in str(config.DB_PATH):
        print(f"RECUSADO: {config.DB_PATH} não parece banco de demonstração.")
        raise SystemExit(1)

    ate = datetime.now(tz=SP).replace(second=0, microsecond=0)
    desde = ate - timedelta(days=args.dias)

    n_ar, n_ruido = semear(desde, ate)
    print(f"Banco: {config.DB_PATH}")
    print(f"{n_ar} leituras de ar e {n_ruido} janelas de ruído")
    print(f"de {desde:%d/%m %H:%M} a {ate:%d/%m %H:%M} (horário de São Paulo)")


if __name__ == "__main__":
    main()
