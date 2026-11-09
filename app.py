"""Servidor Flask: APIs de leitura e a página do dashboard.

    python app.py

Sobe em 0.0.0.0 para ficar acessível pelos outros aparelhos da rede local.
"""

import time
from datetime import datetime, timezone

import csv
import io

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

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


@app.get("/api/painel")
def api_painel():
    """O mesmo view model da página, para atualizá-la sem recarregar.

    O recarregamento de página a cada minuto descartava o scroll, reanunciava o
    documento inteiro para leitor de tela e fechava qualquer painel de
    informação aberto. Aqui vem só o que muda, com os textos já resolvidos no
    servidor para não duplicar português no cliente.
    """
    visao = painel.montar(_inteiro("horas", 24, 1, 24 * 90))

    campos = ("chave", "valor", "unidade", "nivel", "atualizado", "idade",
              "estado_texto", "estado_classe", "marca_classe", "valor_classe",
              "resumo_serie")

    return jsonify({
        "resumo": visao["resumo"],
        "geral": visao["geral"],
        "idade": visao["idade"],
        "idade_segundos": visao["idade_segundos"],
        "atualizado": visao["atualizado"],
        "ruido_calibrado": visao["ruido_calibrado"],
        "blocos": [{c: b[c] for c in campos} for b in visao["blocos"]],
        "graficos": {b["chave"]: b["grafico"] for b in visao["blocos"]},
    })


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


@app.get("/exportar.csv")
def exportar_csv():
    """Baixa o período inteiro num arquivo só, com os dois sensores.

    Os dois coletores gravam a cada 60 s, mas em instantes diferentes dentro do
    minuto, então as linhas são agrupadas por minuto. Onde faltou leitura de um
    dos sensores a célula fica vazia: é uma lacuna visível, melhor que um valor
    repetido ou interpolado que ninguém pediu.

    O ruído leva o dBFS cru e o offset ao lado do dB(A). Com eles, quem
    recalibrar depois reinterpreta esta exportação sem repetir a medição.
    """
    horas = _inteiro("horas", padrao=24, minimo=1, maximo=24 * 365)

    ate = int(time.time())
    desde = ate - horas * 3600
    offset = database.offset_ruido()

    with database.conectar() as conexao:
        linhas = conexao.execute(
            """
            SELECT minuto,
                   MAX(temperatura)  AS temperatura,
                   MAX(umidade)      AS umidade,
                   MAX(laeq_dbfs)    AS laeq_dbfs,
                   MAX(lamax_dbfs)   AS lamax_dbfs,
                   MAX(lamin_dbfs)   AS lamin_dbfs
              FROM (
                SELECT ts / 60 AS minuto, temperatura, umidade,
                       NULL AS laeq_dbfs, NULL AS lamax_dbfs, NULL AS lamin_dbfs
                  FROM leituras WHERE ts BETWEEN ? AND ?
                UNION ALL
                SELECT ts / 60, NULL, NULL, laeq_dbfs, lamax_dbfs, lamin_dbfs
                  FROM leituras_ruido WHERE ts BETWEEN ? AND ?
              )
          GROUP BY minuto
          ORDER BY minuto
            """,
            (desde, ate, desde, ate),
        ).fetchall()

    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow([
        "data_hora_local", "data_hora_utc", "temperatura_c", "umidade_pct",
        "ruido_laeq_dba", "ruido_lamax_dba", "ruido_lamin_dba",
        "ruido_laeq_dbfs_cru", "ruido_offset_db",
    ])

    def db(valor):
        return "" if valor is None else round(valor + offset, 1)

    for linha in linhas:
        ts = linha["minuto"] * 60
        escritor.writerow([
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            _iso(ts),
            "" if linha["temperatura"] is None else linha["temperatura"],
            "" if linha["umidade"] is None else linha["umidade"],
            db(linha["laeq_dbfs"]),
            db(linha["lamax_dbfs"]),
            db(linha["lamin_dbfs"]),
            "" if linha["laeq_dbfs"] is None else round(linha["laeq_dbfs"], 2),
            "" if linha["laeq_dbfs"] is None else offset,
        ])

    carimbo = datetime.fromtimestamp(ate).strftime("%Y-%m-%d-%H%M")
    nome = f"monitor-ambiental-{horas}h-{carimbo}.csv"

    return Response(
        saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _virgula(valor) -> str:
    """Decimal com vírgula, como o resto da interface escreve número."""
    return str(valor).replace(".", ",")


@app.get("/sistema")
def pagina_sistema():
    """O que o aparelho sabe sobre si mesmo: coleta, calibração e limites.

    Material de sistema, não de leitura: sai do rodapé do painel, que virara
    861 caracteres de prosa cinza sem cabeçalho, e ganha endereço próprio.
    """
    ate = int(time.time())
    desde = ate - 24 * 3600

    saude = database.saude_da_coleta(
        desde, ate, config.INTERVALO_SEGUNDOS, config.RUIDO_JANELA_SEGUNDOS
    )
    offset = database.offset_ruido()
    ultima = database.ultima_calibracao()

    return render_template("sistema.html", sistema={
        "saude": {
            "ar": painel.resumo_sensor(saude["ar"]),
            "ruido": painel.resumo_sensor(saude["ruido"]),
        },
        "calibrado": offset != database.OFFSET_DE_CATALOGO,
        "offset": _virgula(f"{offset:+.2f}" if offset != database.OFFSET_DE_CATALOGO
                           else f"{offset:.1f}"),
        "ultima": None if ultima is None else {
            "referencia_dba": _virgula(ultima["referencia_dba"]),
            "medido_dbfs": _virgula(ultima["medido_dbfs"]),
            "minutos": ultima["minutos"],
            "quando": datetime.fromtimestamp(ultima["ts"]).strftime("%d/%m/%Y às %Hh%M"),
            "observacao": ultima["observacao"],
        },
        "periodos": painel.PERIODOS,
    })


@app.get("/calibracao")
def pagina_calibracao():
    return render_template("calibracao.html", estado=api_calibracao_ler().get_json())


@app.post("/calibracao")
def pagina_calibracao_gravar():
    """Mesma lógica da API, respondendo em página para quem não usa JavaScript."""
    corpo = {
        "referencia_dba": request.form.get("referencia_dba"),
        "minutos": request.form.get("minutos"),
        "observacao": request.form.get("observacao"),
    }

    with app.test_request_context("/api/calibracao", json=corpo):
        resposta = api_calibracao_gravar()

    dados = resposta[0].get_json() if isinstance(resposta, tuple) else resposta.get_json()
    codigo = resposta[1] if isinstance(resposta, tuple) else 200

    if codigo == 200:
        return redirect(url_for("pagina_calibracao", ok=1))

    return render_template(
        "calibracao.html",
        estado=api_calibracao_ler().get_json(),
        erro=dados.get("mensagem"),
        enviado=corpo,
    ), codigo


@app.get("/api/limites")
def api_limites():
    """Limites de classificação, para o dashboard desenhar as faixas."""
    return jsonify(config.LIMITES)


if __name__ == "__main__":
    database.criar_esquema()
    app.run(host="0.0.0.0", port=config.PORTA, debug=False)
