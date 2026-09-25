# Monitor Ambiental

Monitor de temperatura e umidade com DHT11 num Raspberry Pi: coleta contínua,
histórico em SQLite e um dashboard web acessível pela rede local.

```text
DHT11 → Raspberry Pi → Python → SQLite → Flask → Chart.js → dashboard
```

## Como está organizado

| Arquivo | Papel |
| --- | --- |
| `config.py` | Todos os ajustes, sobrescrevíveis por variável de ambiente |
| `sensor.py` | Leitura do DHT11, com uma implementação simulada equivalente |
| `database.py` | Esquema e consultas do SQLite |
| `collector.py` | Processo que lê o sensor e grava, em intervalos regulares |
| `app.py` | Flask: as APIs e a página |
| `avaliacao.py` | Classificação em Bom, Atenção e Ruim |
| `teste_dht.py` | Teste isolado do sensor, sem banco e sem Flask |
| `deploy/` | Units de systemd para o coletor e o dashboard |
| `scripts/` | Atualizar o Chart.js e semear histórico simulado |

O coletor e o dashboard são dois processos independentes. Se o Flask cair, a
coleta continua. Se o coletor parar, o dashboard mostra os dados que existem e
avisa que estão velhos, em vez de exibir um número antigo como se fosse atual.

## Rodar sem o Raspberry

Tudo, menos a leitura física do sensor, roda em qualquer máquina. É para isso
que existe o sensor simulado.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Gere um histórico de dois dias e suba o dashboard:

```bash
python scripts/semear.py --horas 48
python app.py
```

Abra <http://localhost:5000>. Para ver a coleta funcionando ao vivo:

```bash
MONITOR_SENSOR=simulado MONITOR_INTERVALO=5 python collector.py
```

## Rodar no Raspberry Pi

```bash
git clone <url-do-repositorio> ~/monitor-ambiental
cd ~/monitor-ambiental

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

Antes de qualquer outra coisa, confirme o sensor:

```bash
python teste_dht.py
```

Com leituras saindo, suba os dois processos:

```bash
python collector.py    # num terminal
python app.py          # noutro
```

O dashboard fica em `http://<ip-do-raspberry>:5000`, acessível de qualquer
aparelho na mesma rede.

Para deixar rodando sozinho depois de reiniciar, veja os arquivos em `deploy/`.

### Ligação do sensor

```text
DHT11              Raspberry Pi
VCC / +   →        3,3 V
DATA / S  →        GPIO4 / BCM4
GND / -   →        GND
```

Módulo de 3 pinos, que já traz o resistor de pull-up embutido.

## Ajustes

Tudo tem padrão razoável; sobrescreva por variável de ambiente quando precisar.

| Variável | Padrão | O que faz |
| --- | --- | --- |
| `MONITOR_SENSOR` | `dht11` | `dht11` ou `simulado` |
| `MONITOR_INTERVALO` | `60` | Segundos entre gravações |
| `MONITOR_PINO` | `D4` | Pino de dados, numeração BCM |
| `MONITOR_DB` | `data/monitor.db` | Caminho do banco |
| `MONITOR_PORTA` | `5000` | Porta do Flask |
| `MONITOR_TENTATIVAS` | `5` | Tentativas de leitura por ciclo |

O padrão de `MONITOR_SENSOR` é o sensor real de propósito. Se a biblioteca do
GPIO falhar no Pi, queremos um erro visível, não dados simulados entrando no
banco em silêncio.

## APIs

| Rota | Devolve |
| --- | --- |
| `GET /api/latest` | Última leitura, idade em segundos e classificação |
| `GET /api/history?horas=24&pontos=500` | Série do período, reduzida a no máximo `pontos` |
| `GET /api/limites` | Os limites de classificação em uso |

As datas saem em ISO 8601 UTC; o navegador converte para a hora local.

`/api/history` agrupa por faixa de tempo e tira a média de cada faixa. Coletando
de minuto em minuto, uma semana daria mais de dez mil pontos — peso à toa para
trafegar e desenhar, sem mudar a forma da curva.

## Banco

```sql
CREATE TABLE leituras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,  -- epoch UTC, em segundos
    temperatura REAL    NOT NULL,  -- graus Celsius
    umidade     REAL    NOT NULL   -- percentual de umidade relativa
);
```

O instante é guardado como epoch em vez de texto: uma fonte única de verdade,
agrupamento por faixa de tempo vira divisão inteira em SQL, e nenhuma dúvida de
fuso horário. Para ler na mão:

```sql
SELECT datetime(ts, 'unixepoch', 'localtime'), temperatura, umidade
  FROM leituras ORDER BY ts DESC LIMIT 10;
```

O banco usa WAL, então o Flask lê enquanto o coletor grava sem um travar o
outro.

## Classificação

Os limites ficam em `config.py`, em `LIMITES`:

| Grandeza | Bom | Atenção | Ruim |
| --- | --- | --- | --- |
| Temperatura | 18 a 26 °C | 16 a 30 °C | fora disso |
| Umidade | 40 a 60 % | 30 a 70 % | fora disso |

A condição geral é sempre a pior das duas.

**Estes limites são provisórios.** São um ponto de partida de conforto de
ambiente interno, não uma norma aplicada, e precisam ser definidos e
fundamentados. Vale lembrar, ao revisar: a umidade do DHT11 tem precisão de
±5%, então limites muito estreitos dariam uma falsa sensação de exatidão.

## Sobre o DHT11

Leituras inválidas são rotina, não defeito: 30% a 50% de falhas é o
comportamento normal do sensor. Por isso cada ciclo do coletor tenta algumas
vezes antes de desistir, e só registra aviso quando o ciclo inteiro falha.

O sensor também não aceita leituras a menos de 2 segundos de distância, o que
define o piso de `MONITOR_INTERVALO`. A resolução é de 1 °C e 1%, então não
espere casas decimais.

## Adiante

Acesso remoto por Tailscale, depois que o protótipo local estiver estável. O
banco e os dados continuam no Raspberry.

O Chart.js vem versionado em `static/vendor/`, servido pelo próprio Raspberry:
o dashboard continua funcionando numa rede local sem internet. Para trocar de
versão, edite e rode `scripts/buscar_vendor.sh`.

O `app.py` sobe o servidor de desenvolvimento do Flask, o que é adequado para um
protótipo na rede local. Se o dashboard virar algo permanente, trocar por
`waitress` é uma linha.
