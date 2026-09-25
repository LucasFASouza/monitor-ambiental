"""Acesso ao banco SQLite.

Guardamos o instante como epoch UTC em segundos (coluna `ts`) em vez de texto.
Isso mantém uma fonte única de verdade, deixa o agrupamento por faixa de tempo
ser uma divisão inteira em SQL, e evita qualquer confusão de fuso. A conversão
para data e hora local acontece só na ponta, no navegador.

Para olhar o banco na mão:

    SELECT datetime(ts, 'unixepoch', 'localtime'), temperatura, umidade
      FROM leituras ORDER BY ts DESC LIMIT 10;
"""

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
"""


def conectar() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(config.DB_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row

    # WAL permite que o coletor grave enquanto o Flask lê, sem um travar o
    # outro. São dois processos no mesmo arquivo, então isso não é opcional.
    conexao.execute("PRAGMA journal_mode = WAL")
    conexao.execute("PRAGMA synchronous = NORMAL")

    return conexao


def criar_esquema() -> None:
    with conectar() as conexao:
        conexao.executescript(ESQUEMA)


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


def total_leituras() -> int:
    with conectar() as conexao:
        return conexao.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]


if __name__ == "__main__":
    criar_esquema()
    print(f"Banco pronto em {config.DB_PATH}")
    print(f"Leituras armazenadas: {total_leituras()}")
