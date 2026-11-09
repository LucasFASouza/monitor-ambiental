"""Monta a visão do dashboard: o que cada grandeza mostra e como se lê.

Fica separado de `app.py` porque é decisão de apresentação, não de rota, e
separado de `config.py` porque depende dos limites mas acrescenta a eles o
vocabulário que o público lê. O público primário são pessoas que trabalham no
ambiente e não conhecem LAeq nem a numeração das normas, então o estado é dito
em frase e não em selo.
"""

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
        reguas=[(25.0, "25 °C"), (18.0, "18 °C")],
        referencia="A NR-17 recomenda de 18 a 25 °C em ambiente climatizado.",
    ),
    "umidade": dict(
        nome="Umidade relativa",
        unidade="%",
        casas=0,
        ymin=25.0,
        ymax=75.0,
        reguas=[(60.0, "60 %"), (40.0, "40 %")],
        referencia="De 40 a 60 % por convergência de fontes: não há norma "
                   "brasileira vigente que indique faixa.",
    ),
    "ruido": dict(
        nome="Ruído",
        unidade="dB(A)",
        casas=1,
        ymin=32.0,
        ymax=82.0,
        reguas=[(65.0, "65 dB(A)"), (45.0, "45 dB(A)")],
        referencia="A NBR 10152 indica até 45 dB(A) para escritório; 65 dB(A) "
                   "é o teto de conforto da NR-17.",
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

        blocos.append({
            "chave": chave,
            "nome": d["nome"],
            "unidade": d["unidade"],
            "referencia": d["referencia"],
            "valor": None if valor is None else f"{valor:.{d['casas']}f}".replace(".", ","),
            "nivel": nivel,
            "frase": frase,
            # Dois renders, um por largura. O SVG encolhe proporcionalmente,
            # então um desenho feito para 660 px vira fonte de 7 px num celular
            # de 375 — ilegível justamente onde a leitura precisa funcionar.
            "svg": grafico.desenhar(
                series[chave], d["ymin"], d["ymax"], d["reguas"], rotulos,
                _faixas_do_eixo(chave, d["ymin"], d["ymax"]),
            ),
            "svg_estreito": grafico.desenhar(
                series[chave], d["ymin"], d["ymax"], d["reguas"],
                rotulos[::2], _faixas_do_eixo(chave, d["ymin"], d["ymax"]),
                largura=352, altura=176, calha=62, margem_y=26, fonte=11.5,
                pontos=56,
            ),
        })

    geral = avaliacao.condicao_geral(*niveis) if niveis else None
    fora = [b for b in blocos if b["nivel"] and b["nivel"] != "bom"]

    idade = None if leitura is None else max(ate - leitura["ts"], 0)

    return {
        "blocos": blocos,
        "geral": geral,
        "fora": fora,
        "horas": horas,
        "periodos": PERIODOS,
        "idade_segundos": idade,
        "atualizado": idade is not None and idade <= config.INTERVALO_SEGUNDOS * 3,
        "data_hora": None if leitura is None else _iso(leitura["ts"]),
        "ruido_calibrado": config.RUIDO_OFFSET_DB != 120.0,
        "intervalo": config.INTERVALO_SEGUNDOS,
    }
