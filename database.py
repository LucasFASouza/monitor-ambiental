"""Acesso ao banco SQLite.

Guardamos o instante como epoch UTC em segundos (coluna `ts`) em vez de texto.
Isso mantém uma fonte única de verdade, deixa o agrupamento por faixa de tempo
ser uma divisão inteira em SQL, e evita qualquer confusão de fuso. A conversão
para data e hora local acontece só na ponta, no navegador.

Para olhar o banco na mão:

    SELECT datetime(ts, 'unixepoch', 'localtime'), temperatura, umidade
      FROM leituras ORDER BY ts DESC LIMIT 10;
"""

import math
import sqlite3
import time

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leituras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,  -- epoch UTC, em segundos
    temperatura REAL    NOT NULL,  -- graus Celsius
    umidade     REAL    NOT NULL   -- percentual de umidade relativa
);

CREATE INDEX IF NOT EXISTS idx_leituras_ts ON leituras (ts);

CREATE TABLE IF NOT EXISTS leituras_ruido (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,  -- epoch UTC, fim da janela de integração
    -- Cru, relativo ao fundo de escala digital. O offset de calibração é
    -- aplicado na leitura, nunca na gravação: assim recalibrar reinterpreta o
    -- histórico inteiro em vez de criar um degrau invisível nele.
    laeq_dbfs  REAL    NOT NULL,
    lamax_dbfs REAL    NOT NULL,
    lamin_dbfs REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leituras_ruido_ts ON leituras_ruido (ts);

CREATE TABLE IF NOT EXISTS calibracoes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             INTEGER NOT NULL,  -- quando a calibração foi registrada
    referencia_dba REAL    NOT NULL,  -- o que o medidor de referência mostrou
    medido_dbfs    REAL    NOT NULL,  -- o que este monitor mediu na mesma janela
    offset_db      REAL    NOT NULL,  -- a diferença, que vira o offset
    minutos        INTEGER NOT NULL,  -- duração da janela comparada
    janelas        INTEGER NOT NULL,  -- quantas leituras entraram na conta
    observacao     TEXT
);

CREATE TABLE IF NOT EXISTS configuracao (
    chave         TEXT PRIMARY KEY,
    valor         TEXT NOT NULL,
    atualizado_em INTEGER NOT NULL
);
"""

# O offset de calibração do ruído vive no banco, não só no ambiente, porque o
# dashboard precisa poder alterá-lo e o histórico precisa continuar coerente.
CHAVE_OFFSET = "ruido_offset_db"

# Valor de catálogo do INMP441: -26 dBFS para 94 dB SPL. Não é calibração.
OFFSET_DE_CATALOGO = 120.0


class MediaEnergetica:
    """Agregado de SQL que faz a média de decibéis pela energia.

    Existe porque AVG() sobre decibel dá resultado errado: a escala é
    logarítmica, então 40 dB e 80 dB não têm média 60 dB, têm quase 80. Como o
    histórico é reduzido agrupando faixas de tempo, a redução precisa somar
    energia, não aritmética.
    """

    def __init__(self):
        self._soma = 0.0
        self._quantidade = 0

    def step(self, valor):
        if valor is None:
            return

        self._soma += 10.0 ** (valor / 10.0)
        self._quantidade += 1

    def finalize(self):
        if self._quantidade == 0:
            return None

        return round(10.0 * math.log10(self._soma / self._quantidade), 1)


def conectar() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(config.DB_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row

    # WAL permite que o coletor grave enquanto o Flask lê, sem um travar o
    # outro. São dois processos no mesmo arquivo, então isso não é opcional.
    conexao.execute("PRAGMA journal_mode = WAL")
    conexao.execute("PRAGMA synchronous = NORMAL")

    conexao.create_aggregate("media_energetica", 1, MediaEnergetica)

    return conexao


def criar_esquema() -> None:
    with conectar() as conexao:
        conexao.executescript(ESQUEMA)
        _migrar(conexao)


def _colunas(conexao, tabela: str) -> set[str]:
    return {linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}


def _migrar(conexao) -> None:
    """Passa o ruído de dB(A) calibrado para dBFS cru.

    Guardar o valor já calibrado parece inofensivo até a primeira
    recalibração: a partir dela o histórico mistura dois offsets no mesmo
    gráfico, sem nada indicando isso. Guardando o dBFS cru e aplicando o
    offset na leitura, recalibrar reinterpreta o passado inteiro de uma vez,
    que é o comportamento correto.

    A conversão usa o offset que estava em vigor quando as linhas foram
    gravadas, registrado na própria configuração.
    """
    colunas = _colunas(conexao, "leituras_ruido")

    if "laeq_dbfs" in colunas:
        return

    for coluna in ("laeq_dbfs", "lamax_dbfs", "lamin_dbfs"):
        conexao.execute(f"ALTER TABLE leituras_ruido ADD COLUMN {coluna} REAL")

    anterior = conexao.execute(
        "SELECT valor FROM configuracao WHERE chave = ?", (CHAVE_OFFSET,)
    ).fetchone()
    offset = float(anterior["valor"]) if anterior else OFFSET_DE_CATALOGO

    conexao.execute(
        "UPDATE leituras_ruido SET laeq_dbfs = laeq - ?, "
        "lamax_dbfs = lamax - ?, lamin_dbfs = lamin - ? "
        "WHERE laeq_dbfs IS NULL",
        (offset, offset, offset),
    )

    if anterior is None:
        conexao.execute(
            "INSERT INTO configuracao (chave, valor, atualizado_em) VALUES (?, ?, ?)",
            (CHAVE_OFFSET, str(OFFSET_DE_CATALOGO), int(time.time())),
        )

    # As colunas calibradas saem: nulas para linha nova e congeladas para linha
    # antiga, elas seriam uma segunda verdade esperando para divergir.
    for coluna in ("laeq", "lamax", "lamin"):
        if coluna in colunas:
            conexao.execute(f"ALTER TABLE leituras_ruido DROP COLUMN {coluna}")


def offset_ruido() -> float:
    """O offset de calibração em vigor, em dB."""
    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT valor FROM configuracao WHERE chave = ?", (CHAVE_OFFSET,)
        ).fetchone()

    return float(linha["valor"]) if linha else OFFSET_DE_CATALOGO


def definir_offset_ruido(valor: float) -> None:
    """Grava um novo offset. O histórico inteiro passa a ser lido com ele."""
    with conectar() as conexao:
        conexao.execute(
            "INSERT INTO configuracao (chave, valor, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
            "atualizado_em = excluded.atualizado_em",
            (CHAVE_OFFSET, str(float(valor)), int(time.time())),
        )


def gravar(temperatura: float, umidade: float, ts: int | None = None) -> None:
    if ts is None:
        ts = int(time.time())

    with conectar() as conexao:
        conexao.execute(
            "INSERT INTO leituras (ts, temperatura, umidade) VALUES (?, ?, ?)",
            (ts, temperatura, umidade),
        )


def ultima_leitura() -> dict | None:
    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT ts, temperatura, umidade FROM leituras"
            " ORDER BY ts DESC LIMIT 1"
        ).fetchone()

    return dict(linha) if linha else None


def historico(desde: int, ate: int, max_pontos: int = 500) -> list[dict]:
    """Leituras entre dois instantes, reduzidas a no máximo `max_pontos`.

    Coletando de minuto em minuto, uma semana daria mais de dez mil pontos:
    peso à toa para trafegar e desenhar. Agrupamos por faixa de tempo e
    tiramos a média de cada faixa, o que preserva a forma da curva.
    """
    intervalo = max(ate - desde, 1)

    # Divisão para cima, e sobre `max_pontos - 1`: as faixas são fatias do
    # eixo do tempo, não do trecho pedido, então o recorte quase sempre pega
    # uma faixa parcial em cada ponta. Arredondar para baixo devolveria mais
    # pontos do que o teto pedido.
    faixa = max(-(-intervalo // max(max_pontos - 1, 1)), 1)

    with conectar() as conexao:
        linhas = conexao.execute(
            """
            SELECT CAST(AVG(ts) AS INTEGER)  AS ts,
                   ROUND(AVG(temperatura), 1) AS temperatura,
                   ROUND(AVG(umidade), 1)     AS umidade
              FROM leituras
             WHERE ts BETWEEN ? AND ?
          GROUP BY ts / ?
          ORDER BY ts
            """,
            (desde, ate, faixa),
        ).fetchall()

    return [dict(linha) for linha in linhas]


def gravar_ruido(
    laeq_dbfs: float, lamax_dbfs: float, lamin_dbfs: float, ts: int | None = None
) -> None:
    """Grava a janela em dBFS cru, sem offset de calibração."""
    if ts is None:
        ts = int(time.time())

    with conectar() as conexao:
        conexao.execute(
            "INSERT INTO leituras_ruido (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs)"
            " VALUES (?, ?, ?, ?)",
            (ts, laeq_dbfs, lamax_dbfs, lamin_dbfs),
        )


def ultima_leitura_ruido(offset: float | None = None) -> dict | None:
    """Última janela, já em dB(A) pelo offset em vigor."""
    if offset is None:
        offset = offset_ruido()

    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT ts,"
            " ROUND(laeq_dbfs + ?, 1)  AS laeq,"
            " ROUND(lamax_dbfs + ?, 1) AS lamax,"
            " ROUND(lamin_dbfs + ?, 1) AS lamin"
            " FROM leituras_ruido ORDER BY ts DESC LIMIT 1",
            (offset, offset, offset),
        ).fetchone()

    return dict(linha) if linha else None


def historico_ruido(
    desde: int, ate: int, max_pontos: int = 500, offset: float | None = None
) -> list[dict]:
    """Como `historico`, mas somando energia ao reduzir os pontos.

    O máximo e o mínimo de cada faixa são o maior e o menor de verdade do
    período, não médias: é isso que mostra os picos que a média esconde.
    """
    if offset is None:
        offset = offset_ruido()

    intervalo = max(ate - desde, 1)
    faixa = max(-(-intervalo // max(max_pontos - 1, 1)), 1)

    with conectar() as conexao:
        linhas = conexao.execute(
            """
            SELECT CAST(AVG(ts) AS INTEGER)            AS ts,
                   media_energetica(laeq_dbfs) + ?      AS laeq,
                   ROUND(MAX(lamax_dbfs) + ?, 1)        AS lamax,
                   ROUND(MIN(lamin_dbfs) + ?, 1)        AS lamin
              FROM leituras_ruido
             WHERE ts BETWEEN ? AND ?
          GROUP BY ts / ?
          ORDER BY ts
            """,
            (offset, offset, offset, desde, ate, faixa),
        ).fetchall()

    return [dict(linha) for linha in linhas]


def nivel_cru_do_periodo(desde: int, ate: int) -> tuple[float | None, int]:
    """Média energética do dBFS cru no período, e quantas janelas entraram.

    É isso que se compara com o medidor de referência: a mesma janela de tempo,
    não um instante. Nível de ruído flutua a cada segundo, então comparar
    leituras pontuais compara ruído com ruído.
    """
    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT media_energetica(laeq_dbfs) AS media, COUNT(*) AS n"
            " FROM leituras_ruido WHERE ts BETWEEN ? AND ?",
            (desde, ate),
        ).fetchone()

    return (linha["media"], linha["n"]) if linha else (None, 0)


def registrar_calibracao(
    referencia_dba: float,
    medido_dbfs: float,
    minutos: int,
    janelas: int,
    observacao: str | None = None,
) -> float:
    """Grava uma calibração e passa a usar o offset dela. Devolve o offset."""
    # Os dois arredondados: antes só o offset era, e o medido entrava cru.
    # Um float como -51.099999999999994 chegava inteiro na ficha.
    medido_dbfs = round(medido_dbfs, 2)
    offset = round(referencia_dba - medido_dbfs, 2)

    with conectar() as conexao:
        conexao.execute(
            "INSERT INTO calibracoes"
            " (ts, referencia_dba, medido_dbfs, offset_db, minutos, janelas, observacao)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), referencia_dba, medido_dbfs, offset,
             minutos, janelas, observacao),
        )

    definir_offset_ruido(offset)
    return offset


def ultima_calibracao() -> dict | None:
    with conectar() as conexao:
        linha = conexao.execute(
            "SELECT * FROM calibracoes ORDER BY ts DESC LIMIT 1"
        ).fetchone()

    return dict(linha) if linha else None


def saude_da_coleta(
    desde: int, ate: int, intervalo: int, janela_ruido: int
) -> dict:
    """Quanto do período tem dado, e quão completo é dentro disso.

    A conta ingênua — leituras presentes sobre leituras esperadas no período
    inteiro — engana: se o coletor subiu há quatro horas, um recorte de 24 h
    aparece como 16% de completude quando na verdade está completo no trecho em
    que existiu. Aqui as duas coisas são medidas separadamente:

    `cobertura` é o trecho do período que tem dado, da primeira à última
    leitura. `completude` é quanto desse trecho está preenchido.

    Um buraco é um salto entre leituras consecutivas maior que o triplo do
    intervalo esperado: uma falha isolada do DHT11 não é buraco, é o sensor
    sendo o que é.
    """

    def de_tabela(tabela: str, passo: int) -> dict:
        with conectar() as conexao:
            limites = conexao.execute(
                f"SELECT MIN(ts) AS primeiro, MAX(ts) AS ultimo, COUNT(*) AS n"
                f" FROM {tabela} WHERE ts BETWEEN ? AND ?",
                (desde, ate),
            ).fetchone()

            buracos = conexao.execute(
                f"""
                SELECT COUNT(*) AS quantos, COALESCE(SUM(salto), 0) AS perdido
                  FROM (
                    SELECT ts - LAG(ts) OVER (ORDER BY ts) AS salto
                      FROM {tabela} WHERE ts BETWEEN ? AND ?
                  )
                 WHERE salto > ?
                """,
                (desde, ate, passo * 3),
            ).fetchone()

        n = limites["n"] or 0

        if n == 0:
            return {"leituras": 0, "cobertura_segundos": 0, "completude": None,
                    "buracos": 0, "perdido_segundos": 0,
                    "primeiro": None, "ultimo": None}

        cobertura = max((limites["ultimo"] - limites["primeiro"]), 0)
        esperadas = max(cobertura // passo + 1, 1)

        return {
            "leituras": n,
            "cobertura_segundos": cobertura,
            "completude": min(round(n / esperadas, 4), 1.0),
            "buracos": buracos["quantos"] or 0,
            "perdido_segundos": int(buracos["perdido"] or 0),
            "primeiro": limites["primeiro"],
            "ultimo": limites["ultimo"],
        }

    ar = de_tabela("leituras", intervalo)
    ruido = de_tabela("leituras_ruido", janela_ruido)

    pedido = max(ate - desde, 1)
    coberto = max(ar["cobertura_segundos"], ruido["cobertura_segundos"])

    return {
        "ar": ar,
        "ruido": ruido,
        "periodo_segundos": pedido,
        "coberto_segundos": coberto,
        # Quanto do recorte pedido realmente tem dado. É isto que diz se o
        # gráfico de 24 h está mostrando 24 h ou quatro.
        "fracao_coberta": round(coberto / pedido, 4),
    }


def total_leituras_ruido() -> int:
    with conectar() as conexao:
        return conexao.execute("SELECT COUNT(*) FROM leituras_ruido").fetchone()[0]


def total_leituras() -> int:
    with conectar() as conexao:
        return conexao.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]


if __name__ == "__main__":
    criar_esquema()
    print(f"Banco pronto em {config.DB_PATH}")
    print(f"Leituras de ar armazenadas:    {total_leituras()}")
    print(f"Leituras de ruído armazenadas: {total_leituras_ruido()}")
