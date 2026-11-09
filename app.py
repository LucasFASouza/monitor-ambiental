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


# Offset de catálogo do INMP441. Enquanto for este, o nível em dB(A) não foi
# calibrado contra referência nenhuma, e o dashboard precisa dizer isso.
OFFSET_SEM_CALIBRACAO = 120.0


@app.get("/")
def pagina():
    return render_template(
        "index.html",
        intervalo=config.INTERVALO_SEGUNDOS,
        janela_ruido=config.RUIDO_JANELA_SEGUNDOS,
    )


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
        "calibrado": config.RUIDO_OFFSET_DB != OFFSET_SEM_CALIBRACAO,
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


@app.get("/api/limites")
def api_limites():
    """Limites de classificação, para o dashboard desenhar as faixas."""
    return jsonify(config.LIMITES)


if __name__ == "__main__":
    database.criar_esquema()
    app.run(host="0.0.0.0", port=config.PORTA, debug=False)
