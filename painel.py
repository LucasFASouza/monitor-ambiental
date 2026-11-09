"""Monta a visão do dashboard: o que cada grandeza mostra e como se lê.

Fica separado de `app.py` porque é decisão de apresentação, não de rota, e
separado de `config.py` porque depende dos limites mas acrescenta a eles o
vocabulário que o público lê. O público primário são pessoas que trabalham no
ambiente e não conhecem LAeq nem a numeração das normas, então o estado é dito
em frase e não em selo.
"""

import json
import math
import time
from datetime import datetime, timezone

import avaliacao
import config
import database
import grafico

# Cores da régua de faixas. Vêm do material impresso da caderneta de saúde,
# onde a faixa de referência é parte do gráfico e não um semáforo de interface.
COR_FAIXA = {"bom": "#3f8f58", "atencao": "#c98a12", "ruim": "#a8392c"}

CONDICAO = {
    "bom": "dentro da faixa recomendada",
    "atencao": "acima da faixa recomendada",
    "ruim": "fora da faixa, em nível inadequado",
}

CONDICAO_BAIXA = {
    "atencao": "abaixo da faixa recomendada",
    "ruim": "muito abaixo da faixa recomendada",
}

PERIODOS = [(6, "6 horas"), (24, "24 horas"), (168, "7 dias"), (720, "30 dias")]


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")



def _bandas(grandeza: str):
    """As bandas da grandeza, do pior de baixo ao pior de cima.

    Devolve uma lista de (de, até, nível). Para ruído só o teto importa, então
    não há banda inferior.
    """
    bom_de, bom_ate = config.LIMITES[grandeza]["bom"]
    at_de, at_ate = config.LIMITES[grandeza]["atencao"]

    bandas = []

    if bom_de > at_de:
        bandas.append((at_de, bom_de, "atencao"))
    if at_de > 0:
        bandas.insert(0, (float("-inf"), at_de, "ruim"))

    bandas.append((bom_de, bom_ate, "bom"))

    if at_ate > bom_ate:
        bandas.append((bom_ate, at_ate, "atencao"))
    bandas.append((at_ate, float("inf"), "ruim"))

    return bandas


# Quanto cada nível vale, para achar o pior que a série tocou.
PESO = {"bom": 0, "atencao": 1, "ruim": 2}


def _janela(grandeza: str, valores):
    """Escolhe a faixa vertical a mostrar, conforme o pior nível alcançado.

    Dentro do verde, mostra verde e amarelo: a faixa vermelha ocuparia metade
    da altura sem nada acontecer nela. Tocou no amarelo, o vermelho entra, para
    que a distância até ele seja visível. A janela sempre contém os dados.
    """
    bandas = _bandas(grandeza)
    bom = next(b for b in bandas if b[2] == "bom")

    pior = "bom"
    for v in valores or []:
        for de, ate, nivel in bandas:
            if de <= v <= ate and PESO[nivel] > PESO[pior]:
                pior = nivel

    mostrar = {"bom", "atencao"} if pior == "bom" else {"bom", "atencao", "ruim"}

    limites = [bom[0], bom[1]]
    for de, ate, nivel in bandas:
        if nivel not in mostrar:
            continue
        if de != float("-inf"):
            limites.append(de)
        if ate != float("inf"):
            limites.append(ate)

    ymin, ymax = min(limites), max(limites)

    # O vermelho não tem fim; dá a ele a largura da banda de atenção vizinha.
    if "ruim" in mostrar:
        atencoes = [ate - de for de, ate, n in bandas
                    if n == "atencao" and float("-inf") < de and ate < float("inf")]
        folga = (sum(atencoes) / len(atencoes)) if atencoes else (ymax - ymin) * 0.2
        if any(n == "ruim" and ate != float("inf") for de, ate, n in bandas):
            ymin -= folga
        ymax += folga

    # Quando o piso da faixa boa é zero, ele é artificial: a grandeza só tem
    # teto. Mostrar de zero para cima deixaria metade do gráfico vazia, então
    # a janela começa perto do dado.
    if bom[0] <= 0 and valores:
        ymin = min(valores) - (ymax - min(valores)) * 0.12

    if valores:
        margem = (ymax - ymin) * 0.04
        ymin = min(ymin, min(valores) - margem)
        ymax = max(ymax, max(valores) + margem)

    return round(ymin, 1), round(ymax, 1)


def _faixas_visiveis(grandeza: str, ymin: float, ymax: float):
    """As bandas recortadas na janela, para a régua do eixo."""
    recortes = []

    for de, ate, nivel in _bandas(grandeza):
        inicio, fim = max(de, ymin), min(ate, ymax)
        if fim > inicio:
            recortes.append({"de": round(inicio, 2), "ate": round(fim, 2),
                             "cor": COR_FAIXA[nivel], "nivel": nivel})

    return recortes


def _faixas_do_eixo(grandeza: str, ymin: float, ymax: float):
    """Converte os limites de config em trechos coloridos para a régua do eixo."""
    bom_de, bom_ate = config.LIMITES[grandeza]["bom"]
    at_de, at_ate = config.LIMITES[grandeza]["atencao"]

    trechos = []

    if at_de > ymin:
        trechos.append((ymin, at_de, COR_FAIXA["ruim"]))
    if bom_de > at_de:
        trechos.append((at_de, bom_de, COR_FAIXA["atencao"]))

    trechos.append((max(bom_de, ymin), min(bom_ate, ymax), COR_FAIXA["bom"]))

    if at_ate > bom_ate:
        trechos.append((bom_ate, at_ate, COR_FAIXA["atencao"]))
    if ymax > at_ate:
        trechos.append((at_ate, ymax, COR_FAIXA["ruim"]))

    return [(de, ate, cor) for de, ate, cor in trechos if ate > de]


# Cada grandeza: rótulo, unidade, casas, escala do eixo e as réguas de limite,
# com a norma que as sustenta dita por extenso para quem não a conhece.
GRANDEZAS = {
    "temperatura": dict(
        nome="Temperatura",
        unidade="°C",
        casas=1,
        ymin=15.0,
        ymax=30.0,
        reguas=[(25.0, "25"), (18.0, "18")],
        explicacao="Acima de 25 °C o calor começa a atrapalhar quem trabalha "
                   "sentado. Abaixo de 18 °C o frio passa a fazer mal à saúde.",
        norma="Faixa do item 17.8.4.2 da NR-17, na redação da Portaria MTP "
              "423/2021. O piso de 18 °C coincide com o mínimo das Housing and "
              "health guidelines da OMS (2018), por caminho independente.",
    ),
    "umidade": dict(
        nome="Umidade relativa",
        unidade="%",
        casas=0,
        ymin=25.0,
        ymax=75.0,
        reguas=[(60.0, "60"), (40.0, "40")],
        explicacao="Abaixo de 40 % o ar resseca a garganta e os olhos. "
                   "Acima de 60 % começa a favorecer mofo.",
        norma="Não há norma brasileira vigente com faixa de umidade: a NR-17 "
              "perdeu esse número na revisão de 2021 e a RE 09/2003 da ANVISA "
              "foi revogada em 2024. Esta faixa é convergência de fontes, "
              "não norma.",
    ),
    "ruido": dict(
        nome="Ruído",
        unidade="dB(A)",
        casas=1,
        ymin=32.0,
        ymax=82.0,
        reguas=[(65.0, "65"), (45.0, "45")],
        explicacao="Até 45 dB(A) dá para conversar e se concentrar sem "
                   "esforço. Entre 45 e 65 já incomoda. Acima de 65 atrapalha "
                   "quem precisa de atenção.",
        norma="Os 45 dB(A) vêm da NBR 10152:2017 para escritório privativo. "
              "O teto de 65 dB(A) é literal do item 17.8.4.1.2 da NR-17, que "
              "o define como nível de ruído de fundo aceitável para conforto "
              "acústico, medido como nível contínuo equivalente ponderado em "
              "A — que é exatamente o que este monitor calcula.",
    ),
}


def _rotulos_de_tempo(desde: int, ate: int, horas: int):
    """Cinco marcas no eixo do tempo, a última sempre 'agora'."""
    marcas = []

    for i in range(5):
        fracao = i / 4
        instante = desde + (ate - desde) * fracao
        local = datetime.fromtimestamp(instante)

        if i == 4:
            rotulo = "agora"
        elif horas > 48:
            rotulo = local.strftime("%d/%m")
        else:
            rotulo = local.strftime("%Hh")

        marcas.append((fracao, rotulo))

    return marcas


def _marcas_por_ponto(desde: int, ate: int, horas: int, quantos: int):
    """Um rótulo de hora por ponto, para o eixo e para a dica do mouse."""
    formato = "%d/%m %Hh" if horas > 48 else "%Hh%M"

    return [
        datetime.fromtimestamp(desde + (ate - desde) * i / max(quantos - 1, 1)).strftime(formato)
        for i in range(quantos)
    ]


def duracao(segundos: int) -> str:
    """Duração em português curto. O servidor também precisa formatar: sem isso
    o primeiro desenho mostra "629 s" até o JavaScript arredondar."""
    if segundos < 90:
        return f"{segundos} s"
    if segundos < 5400:
        return f"{round(segundos / 60)} min"
    return f"{round(segundos / 3600)} h"


def _classificar(grandeza: str, valor: float) -> tuple[str, str]:
    """Nível e a frase que o descreve, distinguindo acima de abaixo."""
    nivel = avaliacao.classificar(grandeza, valor)

    if nivel == "bom":
        return nivel, CONDICAO["bom"]

    bom_de, _ = config.LIMITES[grandeza]["bom"]

    if valor < bom_de:
        return nivel, CONDICAO_BAIXA[nivel]

    return nivel, CONDICAO[nivel]


def montar(horas: int = 24) -> dict:
    """Tudo que o template precisa para desenhar a página."""
    horas = min(max(horas, 1), 24 * 90)

    ate = int(time.time())
    desde = ate - horas * 3600

    leitura = database.ultima_leitura()
    ruido = database.ultima_leitura_ruido()

    serie_ar = database.historico(desde, ate, max_pontos=600)
    serie_ruido = database.historico_ruido(desde, ate, max_pontos=600)

    rotulos = _rotulos_de_tempo(desde, ate, horas)

    atuais = {}
    if leitura:
        atuais["temperatura"] = leitura["temperatura"]
        atuais["umidade"] = leitura["umidade"]
    if ruido:
        atuais["ruido"] = ruido["laeq"]

    series = {
        "temperatura": [linha["temperatura"] for linha in serie_ar],
        "umidade": [linha["umidade"] for linha in serie_ar],
        "ruido": [linha["laeq"] for linha in serie_ruido],
    }

    blocos = []
    niveis = []

    for chave, d in GRANDEZAS.items():
        valor = atuais.get(chave)
        nivel, frase = _classificar(chave, valor) if valor is not None else (None, None)

        if nivel:
            niveis.append(nivel)

        janela_min, janela_max = _janela(chave, series[chave])

        # Os rótulos derivam da contagem real de baldes: `agregar` arredonda
        # para cima, então fixar 96 desalinharia o eixo dos dados.
        pontos = grafico.agregar(series[chave], 96)
        marcas = _marcas_por_ponto(desde, ate, horas, len(pontos))

        blocos.append({
            "chave": chave,
            "nome": d["nome"],
            "unidade": d["unidade"],
            "explicacao": d["explicacao"],
            "norma": d["norma"],
            # O cliente desenha com Chart.js: o servidor decide a semântica
            # (janela, faixas, limites) e o navegador cuida da interação, que
            # é o que o SVG estático não tinha.
            "grafico": {
                "rotulos": marcas,
                "pontos": [{"m": round(m, 2), "n": round(n, 2), "x": round(x, 2)}
                           for m, n, x in pontos],
                "ymin": janela_min,
                "ymax": janela_max,
                "passo": 5 if (janela_max - janela_min) <= 45 else 10,
                "unidade": d["unidade"],
                "faixas": _faixas_visiveis(chave, janela_min, janela_max),
                "reguas": [{"valor": v, "rotulo": r} for v, r in d["reguas"]
                           if janela_min <= v <= janela_max],
            },
            "valor": None if valor is None else f"{valor:.{d['casas']}f}".replace(".", ","),
            "nivel": nivel,
            "frase": frase,
        })

    geral = avaliacao.condicao_geral(*niveis) if niveis else None
    fora = [b for b in blocos if b["nivel"] and b["nivel"] != "bom"]

    idade = None if leitura is None else max(ate - leitura["ts"], 0)

    return {
        "dados_json": json.dumps(
            {b["chave"]: b["grafico"] for b in blocos}, ensure_ascii=False
        ),
        "blocos": blocos,
        "geral": geral,
        "fora": fora,
        "horas": horas,
        "periodos": PERIODOS,
        "idade_segundos": idade,
        "idade": None if idade is None else duracao(idade),
        "atualizado": idade is not None and idade <= config.INTERVALO_SEGUNDOS * 3,
        "data_hora": None if leitura is None else _iso(leitura["ts"]),
        "ruido_calibrado": database.offset_ruido() != database.OFFSET_DE_CATALOGO,
        "intervalo": config.INTERVALO_SEGUNDOS,
    }
