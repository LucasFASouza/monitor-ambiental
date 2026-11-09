"""Servidor Flask: APIs de leitura e a página do dashboard.

    python app.py

Sobe em 0.0.0.0 para ficar acessível pelos outros aparelhos da rede local.
"""

import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

import avaliacao
import config
import database
import painel

app = Flask(__name__)


def _iso(ts: int) -> str:
    """Epoch UTC para ISO 8601. O navegador converte para a hora local."""
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _inteiro(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    try:
        valor = int(request.args.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao

    return min(max(valor, minimo), maximo)


@app.get("/")
def pagina():
    # A página é montada inteira no servidor, gráficos incluídos: são poucos
    # clientes na rede local, e assim ela funciona sem JavaScript.
    return render_template("index.html", visao=painel.montar(_inteiro("horas", 24, 1, 24 * 90)))


def _bloco_ruido() -> dict | None:
    """Última medição de ruído, ou None se o coletor nunca rodou."""
    leitura = database.ultima_leitura_ruido()

    if leitura is None:
        return None

    idade = max(int(time.time()) - leitura["ts"], 0)

    return {
        "leitura": {
            "data_hora": _iso(leitura["ts"]),
            "laeq": leitura["laeq"],
            "lamax": leitura["lamax"],
            "lamin": leitura["lamin"],
            "idade_segundos": idade,
        },
        "avaliacao": avaliacao.avaliar_ruido(leitura["laeq"]),
        "atualizado": idade <= config.RUIDO_JANELA_SEGUNDOS * 3,
        "janela_segundos": config.RUIDO_JANELA_SEGUNDOS,
        "calibrado": database.offset_ruido() != database.OFFSET_DE_CATALOGO,
    }


@app.get("/api/latest")
def api_latest():
    leitura = database.ultima_leitura()

    if leitura is None:
        return jsonify(
            {
                "leitura": None,
                "avaliacao": None,
                "atualizado": False,
                "intervalo_segundos": config.INTERVALO_SEGUNDOS,
            }
        )

    idade = max(int(time.time()) - leitura["ts"], 0)

    # Três intervalos sem nada novo é sinal de que o coletor parou. O
    # dashboard usa isso para avisar em vez de exibir um dado velho como se
    # fosse atual.
    atualizado = idade <= config.INTERVALO_SEGUNDOS * 3

    classificacao = avaliacao.avaliar(leitura["temperatura"], leitura["umidade"])
    ruido = _bloco_ruido()

    # A condição geral é a pior entre tudo que está sendo medido. Se há ruído
    # recente, ele entra: um cartão chamado "condição geral" que ignorasse
    # 80 dB(A) estaria mentindo.
    if ruido is not None and ruido["atualizado"]:
        classificacao["geral"] = avaliacao.condicao_geral(
            classificacao["geral"], ruido["avaliacao"]
        )

    return jsonify(
        {
            "leitura": {
                "data_hora": _iso(leitura["ts"]),
                "temperatura": leitura["temperatura"],
                "umidade": leitura["umidade"],
                "idade_segundos": idade,
            },
            "avaliacao": classificacao,
            "atualizado": atualizado,
            "intervalo_segundos": config.INTERVALO_SEGUNDOS,
            "ruido": ruido,
        }
    )


@app.get("/api/history")
def api_history():
    horas = _inteiro("horas", padrao=24, minimo=1, maximo=24 * 90)
    pontos = _inteiro("pontos", padrao=500, minimo=10, maximo=5000)

    ate = int(time.time())
    desde = ate - horas * 3600

    leituras = database.historico(desde, ate, max_pontos=pontos)

    return jsonify(
        {
            "horas": horas,
            "leituras": [
                {
                    "data_hora": _iso(linha["ts"]),
                    "temperatura": linha["temperatura"],
                    "umidade": linha["umidade"],
                }
                for linha in leituras
            ],
        }
    )


@app.get("/api/ruido/history")
def api_ruido_history():
    horas = _inteiro("horas", padrao=24, minimo=1, maximo=24 * 90)
    pontos = _inteiro("pontos", padrao=500, minimo=10, maximo=5000)

    ate = int(time.time())
    desde = ate - horas * 3600

    leituras = database.historico_ruido(desde, ate, max_pontos=pontos)

    return jsonify(
        {
            "horas": horas,
            "leituras": [
                {
                    "data_hora": _iso(linha["ts"]),
                    "laeq": linha["laeq"],
                    "lamax": linha["lamax"],
                    "lamin": linha["lamin"],
                }
                for linha in leituras
            ],
        }
    )


@app.get("/api/calibracao")
def api_calibracao_ler():
    """Estado da calibração do ruído."""
    ultima = database.ultima_calibracao()
    offset = database.offset_ruido()

    return jsonify({
        "offset_db": offset,
        "calibrado": offset != database.OFFSET_DE_CATALOGO,
        "offset_de_catalogo": database.OFFSET_DE_CATALOGO,
        "ultima": None if ultima is None else {
            "data_hora": _iso(ultima["ts"]),
            "referencia_dba": ultima["referencia_dba"],
            "medido_dbfs": ultima["medido_dbfs"],
            "offset_db": ultima["offset_db"],
            "minutos": ultima["minutos"],
            "janelas": ultima["janelas"],
            "observacao": ultima["observacao"],
        },
    })


@app.post("/api/calibracao")
def api_calibracao_gravar():
    """Calibra o ruído comparando uma janela de tempo com um medidor externo.

    O corpo traz o LAeq que o medidor de referência mostrou e por quantos
    minutos ele ficou ao lado. O offset sai da diferença entre esse valor e o
    que este monitor mediu na MESMA janela — nunca de um instante, porque o
    nível flutua a cada segundo e um ponto contra outro compara ruído com
    ruído.
    """
    corpo = request.get_json(silent=True) or {}

    try:
        referencia = float(corpo["referencia_dba"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "erro": "referencia_dba_invalida",
            "mensagem": "Informe em `referencia_dba` o LAeq que o medidor de "
                        "referência mostrou, em dB(A).",
        }), 400

    try:
        minutos = int(corpo.get("minutos", 5))
    except (TypeError, ValueError):
        minutos = 5

    minutos = min(max(minutos, 1), 120)

    if not 20.0 <= referencia <= 130.0:
        return jsonify({
            "erro": "referencia_fora_de_faixa",
            "mensagem": f"{referencia} dB(A) está fora do que um medidor "
                        "mediria num ambiente de trabalho (20 a 130).",
        }), 400

    ate = int(time.time())
    desde = ate - minutos * 60
    medido, janelas = database.nivel_cru_do_periodo(desde, ate)

    # Sem janelas suficientes a média não representa o período: calibrar com
    # uma ou duas leituras devolveria um offset tão instável quanto o chute.
    minimo = max(minutos * 60 // config.RUIDO_JANELA_SEGUNDOS // 2, 3)

    if medido is None or janelas < minimo:
        return jsonify({
            "erro": "janelas_insuficientes",
            "mensagem": f"Só há {janelas} leitura(s) de ruído nos últimos "
                        f"{minutos} min, e seriam necessárias ao menos {minimo}. "
                        "O coletor de ruído está rodando?",
            "janelas": janelas,
            "minimo": minimo,
        }), 409

    offset = database.registrar_calibracao(
        referencia_dba=referencia,
        medido_dbfs=medido,
        minutos=minutos,
        janelas=janelas,
        observacao=(corpo.get("observacao") or None),
    )

    return jsonify({
        "offset_db": offset,
        "medido_dbfs": round(medido, 2),
        "referencia_dba": referencia,
        "minutos": minutos,
        "janelas": janelas,
        "anterior": database.OFFSET_DE_CATALOGO,
        "mensagem": f"Calibrado em {offset:+.2f} dB a partir de {janelas} "
                    f"janelas dos últimos {minutos} min. Todo o histórico "
                    "passa a ser lido com este offset.",
    })


@app.get("/api/limites")
def api_limites():
    """Limites de classificação, para o dashboard desenhar as faixas."""
    return jsonify(config.LIMITES)


if __name__ == "__main__":
    database.criar_esquema()
    app.run(host="0.0.0.0", port=config.PORTA, debug=False)
