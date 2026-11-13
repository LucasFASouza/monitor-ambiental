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

# O mesmo ar-condicionado que segura a temperatura condensa água na serpentina
# e devolve a sala mais seca. Pontos de umidade a descontar.
SECAGEM_AR = 7.0

# Gente chegando, saindo para o almoço e indo embora, falando alto perto do
# sensor. São isolados e não acontecem todo dia, que é como conversa funciona.
PICOS_HORAS = (9.0, 12.0, 18.0)
PICO_CHANCE = 0.55            # chance de haver pico naquele horário, por dia
PICO_DISPERSAO = 25           # minutos de folga em torno do horário
PICO_DURACAO = (1, 3)         # minutos
PICO_NIVEL = (60.0, 74.0)     # LAeq do pico, em dB(A): a maioria cruza os 65
                              # da NR-17, que é o ponto da demonstração. Grupo
                              # conversando alto a um ou dois metros do sensor
                              # fica nessa casa; abaixo de 60 a fala não se
                              # destaca do escritório trabalhando.

# O arquivo real tem poucas janelas muito altas, e sorteá-las com reposição ao
# longo de sete dias fazia o MESMO valor aparecer dez vezes — nada denuncia
# mais uma série montada. As altas saem do balde e passam a vir dos picos
# agendados, que é onde elas fazem sentido.
TETO_DO_BALDE = 50.0

# E cada janela transplantada ganha um empurrãozinho, para duas cópias da mesma
# janela não saírem iguais ao décimo de decibel.
JITTER_JANELA = 0.8

# O offset da calibração de 09/11. O banco guarda dBFS cru e a leitura soma o
# offset, então o gerador faz o caminho inverso antes de gravar.
OFFSET_DBFS = 99.1

# Onde fica o recuo da temperatura, para a continuação ao vivo aplicar o mesmo
# que o semeador aplicou. Sem isso, o primeiro minuto ao vivo daria um degrau
# do tamanho do recuo.
CHAVE_RECUO = "demo_recuo_temp"


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
    dentro = [r for r in ruido if r[1] <= TETO_DO_BALDE]
    return {
        "alto": [r for r in dentro if 12 <= r[0].hour < 18],
        "medio": [r for r in dentro if 18 <= r[0].hour < 20],
        "baixo": [r for r in dentro if r[0].hour >= 20],
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


def sortear_picos(desde: datetime, ate: datetime) -> dict:
    """Minutos em que alguém falou alto perto do sensor.

    Só em dia útil, só em alguns dias, e curtos: um pico que dura meia hora não
    é conversa, é obra.
    """
    picos = {}
    dia = desde.replace(hour=0, minute=0)

    while dia < ate + timedelta(days=1):
        if dia.weekday() < 5:
            for hora in PICOS_HORAS:
                if random.random() > PICO_CHANCE:
                    continue

                inicio = dia + timedelta(
                    hours=hora, minutes=random.randint(-PICO_DISPERSAO, PICO_DISPERSAO))
                nivel = random.uniform(*PICO_NIVEL)

                for k in range(random.randint(*PICO_DURACAO)):
                    # O pico decai ao longo dos minutos: a conversa se afasta.
                    picos[inicio + timedelta(minutes=k)] = nivel - k * random.uniform(2, 5)

        dia += timedelta(days=1)

    return picos


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


class Gerador:
    """O passo de um minuto, com o estado que ele carrega de um para o outro.

    É classe porque tem dois usuários: o semeador, que roda sete dias de uma
    vez, e a continuação ao vivo, que roda um minuto por vez e precisa retomar
    de onde o minuto anterior parou. Era um laço só, dentro de `semear`;
    duplicá-lo daria duas séries com texturas diferentes no mesmo banco, que é
    exatamente o tipo de costura que se vê no gráfico.
    """

    def __init__(self, ar_real, ruido_real, picos, temp=None, umid=None):
        self.passos = passos_reais(ar_real)
        self.baldes = baldes_de_ruido(ruido_real)
        self.media_baixo = (sum(r[1] for r in self.baldes["baixo"])
                            / len(self.baldes["baixo"]))

        self.reais_ar = {q: (t, u) for q, t, u in ar_real}
        self.reais_ruido = {q: (a, b, c) for q, a, b, c in ruido_real}
        self.picos = picos

        self.temp, self.umid = temp, umid

        # O puxão para a linha de base se acumula aqui e só vira movimento
        # quando alcança um degrau inteiro. Aplicado direto no valor, ele
        # somava um pouquinho a cada minuto e o arredondamento transformava
        # isso em degraus que o sensor nunca deu: a umidade passava a mexer em
        # 18% dos minutos contra 9,5% reais, e as reversões caíam pela metade.
        self.erro_t = self.erro_u = 0.0

        self.i_passo = random.randrange(len(self.passos))
        self.restante, self.sinal = 0, 1

        self.usados_ar = self.usados_ruido = 0

    def _ar(self, quando: datetime):
        base_t, base_u = base_do_dia(quando)

        if quando in self.reais_ar:
            self.temp, self.umid = self.reais_ar[quando]
            self.usados_ar += 1
            return self.temp, self.umid

        if self.temp is None:
            self.temp, self.umid = base_t, base_u

        # Blocos contíguos de passos reais: dentro do bloco, segue o que o
        # sensor fez; ao fim dele, sorteia outro ponto de partida.
        if self.restante <= 0:
            self.i_passo = random.randrange(len(self.passos))
            self.restante = random.randint(40, 180)
            # Espelhar o bloco, meio a meio. Os passos reais têm deriva
            # líquida — o arquivo é de um dia em que a sala caiu de 23,4 para
            # 21,8 °C — e reaplicá-los sempre na mesma direção faz a série
            # afundar. Invertendo metade dos blocos, a deriva esperada vira
            # zero e a textura fica intacta: são os mesmos degraus, as mesmas
            # rajadas, as mesmas reversões.
            self.sinal = random.choice((1, -1))

        dt, du = self.passos[self.i_passo]
        dt, du = self.sinal * dt, self.sinal * du
        self.i_passo = (self.i_passo + 1) % len(self.passos)
        self.restante -= 1

        self.temp = round(self.temp + dt, 1)
        self.umid = round(self.umid + du, 1)

        # Correção de deriva, em degraus do mesmo tamanho que os reais. A
        # temperatura precisa de puxão MUITO mais fraco que a umidade: ela
        # fica parada por horas, e uma correção que alcança um degrau a cada
        # 25 min quebra todos os platôs.
        self.erro_t += (base_t - self.temp) * 0.0018
        if abs(self.erro_t) >= 0.1:
            passo = 0.1 if self.erro_t > 0 else -0.1
            self.temp, self.erro_t = round(self.temp + passo, 1), self.erro_t - passo

        self.erro_u += (base_u - self.umid) * 0.004
        if abs(self.erro_u) >= 1.0:
            passo = 1.0 if self.erro_u > 0 else -1.0
            self.umid, self.erro_u = round(self.umid + passo, 1), self.erro_u - passo

        return self.temp, self.umid

    def _ruido(self, quando: datetime):
        if quando in self.reais_ruido:
            r = self.reais_ruido[quando]
            laeq, lamax, lamin = misturar(
                (quando, r[0], r[1], r[2]), atividade(quando), self.media_baixo)
            self.usados_ruido += 1
        else:
            a = atividade(quando)
            janela = random.choice(self.baldes[balde_da_hora(a)])
            laeq, lamax, lamin = misturar(janela, a, self.media_baixo)

            empurrao = random.gauss(0, JITTER_JANELA)
            laeq, lamax, lamin = laeq + empurrao, lamax + empurrao, lamin + empurrao

        if quando in self.picos:
            laeq = self.picos[quando]
            # Fala tem pico alto sobre a média: o máximo da janela sobe junto.
            lamax = laeq + random.uniform(5.0, 11.0)
            lamin = laeq - random.uniform(14.0, 22.0)

        return laeq, lamax, lamin

    def minuto(self, quando: datetime):
        """Temperatura e umidade em grandeza, ruído já em dBFS para gravar."""
        temp, umid = self._ar(quando)
        laeq, lamax, lamin = self._ruido(quando)

        return (temp, umid,
                round(laeq - OFFSET_DBFS, 2),
                round(lamax - OFFSET_DBFS, 2),
                round(max(lamin, 12.0) - OFFSET_DBFS, 2))


def semear(csv_real: Path, dias: int, semente: int = 20261112):
    random.seed(semente)

    ar_real, ruido_real = carregar(csv_real)

    print(f"Arquivo real: {len(ar_real)} leituras de ar, {len(ruido_real)} janelas "
          f"de ruído, de {ar_real[0][0]:%d/%m %H:%M} a {ar_real[-1][0]:%d/%m %H:%M}")

    database.criar_esquema()
    conexao = database.conectar()
    conexao.execute("DELETE FROM leituras")
    conexao.execute("DELETE FROM leituras_ruido")
    conexao.execute("DELETE FROM calibracoes")

    ate = datetime.now(tz=SP).replace(second=0, microsecond=0)
    desde = ate - timedelta(days=dias)

    g = Gerador(ar_real, ruido_real, sortear_picos(desde, ate))
    print(f"  baldes de ruído: alto {len(g.baldes['alto'])}, "
          f"médio {len(g.baldes['medio'])}, baixo {len(g.baldes['baixo'])}")

    ar, ruido = [], []
    quando = desde
    while quando < ate:
        temp, umid, laeq, lamax, lamin = g.minuto(quando)
        ts = int(quando.timestamp())
        ar.append((ts, temp, umid))
        ruido.append((ts, laeq, lamax, lamin))
        quando += timedelta(minutes=1)

    # Teto da temperatura: desloca a série inteira, não comprime, para não
    # achatar a textura transplantada. O recuo fica guardado porque a
    # continuação ao vivo precisa aplicar exatamente o mesmo — senão o
    # primeiro minuto depois do semeador daria um degrau do tamanho dele.
    pico = max(x[1] for x in ar)
    recuo = round(max(0.0, pico - TEMPERATURA_MAXIMA), 1)
    ar = [(ts, round(t - recuo, 1), round(u - SECAGEM_AR, 1)) for ts, t, u in ar]

    with conexao:
        conexao.executemany(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)", ar)
        conexao.executemany(
            "INSERT INTO leituras_ruido (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs)"
            " VALUES (?, ?, ?, ?)", ruido)
        conexao.execute(
            "INSERT INTO calibracoes (ts, referencia_dba, medido_dbfs, offset_db,"
            " minutos, janelas, observacao) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(desde.timestamp()), 30.0, -69.1, OFFSET_DBFS, 5, 5,
             "Medidor de referência, 09/11"))
        conexao.execute(
            "INSERT INTO configuracao (chave, valor, atualizado_em)"
            " VALUES (?, ?, ?) ON CONFLICT(chave) DO UPDATE SET"
            " valor = excluded.valor, atualizado_em = excluded.atualizado_em",
            (CHAVE_RECUO, str(recuo), int(ate.timestamp())))

    database.definir_offset_ruido(OFFSET_DBFS)
    return len(ar), g.usados_ar, g.usados_ruido, desde, ate


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
