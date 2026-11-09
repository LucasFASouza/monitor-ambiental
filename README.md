# Monitor Ambiental

Monitor de temperatura, umidade e ruído num Raspberry Pi: coleta contínua,
histórico em SQLite e um dashboard web acessível pela rede local.

```text
DHT11    ┐
         ├→ Raspberry Pi → SQLite → Flask → Chart.js → dashboard
INMP441  ┘
```

## Como está organizado

| Arquivo | Papel |
| --- | --- |
| `config.py` | Todos os ajustes, sobrescrevíveis por variável de ambiente |
| `sensor.py` | Leitura do DHT11, com implementações intercambiáveis |
| `sensor_ruido.py` | Captura do microfone I2S e cálculo de nível em dB(A) |
| `collector_ruido.py` | Processo que mede o ruído e grava um LAeq por janela |
| `database.py` | Esquema e consultas do SQLite |
| `collector.py` | Processo que lê o sensor e grava, em intervalos regulares |
| `app.py` | Flask: as APIs e a página |
| `avaliacao.py` | Classificação em Bom, Atenção e Ruim |
| `teste_dht.py` | Teste isolado do sensor, sem banco e sem Flask |
| `deploy/` | Units de systemd para o coletor e o dashboard |
| `scripts/` | Atualizar o Chart.js e semear histórico simulado |

São três processos independentes: o coletor de ar, o coletor de ruído e o
dashboard. Se o Flask cair, a coleta continua. Se um coletor parar, o outro
segue, e o dashboard mostra os dados que existem avisando que estão velhos, em
vez de exibir um número antigo como se fosse atual.

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

### 1. Habilitar o hardware

Acrescente ao final do `/boot/firmware/config.txt` (ou `/boot/config.txt` em
sistemas mais antigos):

```text
[all]
dtoverlay=dht11,gpiopin=4
dtoverlay=googlevoicehat-soundcard
```

E garanta que esta linha esteja **sem** o `#` na frente:

```text
dtparam=i2s=on
```

O `gpiopin` é o número BCM e precisa bater com `MONITOR_PINO`. O overlay
`googlevoicehat-soundcard` é o que cria o dispositivo de captura I2S para o
microfone. Reinicie a placa depois de editar.

Para conferir que os dois subiram:

```bash
cat /sys/bus/iio/devices/iio:device0/in_temp_input   # ex: 23400
arecord -l                                            # deve listar sndrpigooglevoi
```

### 2. Instalar

```bash
git clone <url-do-repositorio> ~/monitor-ambiental
cd ~/monitor-ambiental

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

O `--system-site-packages` aproveita o numpy que já vem no Raspberry Pi OS, em
vez de compilar outro.

### 3. Conferir os sensores

```bash
python teste_dht.py
```

```bash
arecord -D plughw:CARD=sndrpigooglevoi,DEV=0 -c2 -r48000 -f S32_LE -V stereo -d 10 /tmp/teste.wav
```

No segundo, fale perto do microfone: as barras de um dos canais têm que se
mexer. O outro canal fica mudo, e isso é esperado — você tem um microfone só
num barramento estéreo.

### 4. Subir

```bash
python collector.py         # num terminal
python collector_ruido.py   # noutro
python app.py               # noutro
```

O dashboard fica em `http://<ip-do-raspberry>:5000`, acessível de qualquer
aparelho na mesma rede.

Para deixar rodando sozinho depois de reiniciar:

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-coletor monitor-coletor-ruido monitor-dashboard
```

### Ligação

```text
DHT11              Raspberry Pi          INMP441         Raspberry Pi

VCC / +   →        pino 1  (3,3 V)       VDD    →        pino 17  (3,3 V)
GND / -   →        pino 6  (GND)         GND    →        pino 34  (GND)
DATA / S  →        pino 7  (GPIO4)       SCK    →        pino 12  (GPIO18)
                                         WS     →        pino 35  (GPIO19)
                                         SD     →        pino 38  (GPIO20)
                                         L/R    →        pino 39  (GND)
```

O DHT11 é o módulo de 3 pinos, que já traz o resistor de pull-up embutido.

No INMP441, o `L/R` em GND escolhe o canal esquerdo (`MONITOR_RUIDO_CANAL=0`);
em 3,3 V seria o direito. Não é alimentação, é uma entrada de configuração,
então pode ir em qualquer GND livre.

Os dois sensores não disputam pino nenhum: o DHT11 fica no GPIO4 e o I2S usa
GPIO18, 19 e 20.

## Ajustes

Tudo tem padrão razoável; sobrescreva por variável de ambiente quando precisar.

| Variável | Padrão | O que faz |
| --- | --- | --- |
| `MONITOR_SENSOR` | `dht11` | `dht11`, `dht11-blinka` ou `simulado` |
| `MONITOR_INTERVALO` | `60` | Segundos entre gravações |
| `MONITOR_PINO` | `4` | Pino de dados, numeração BCM |
| `MONITOR_DB` | `data/monitor.db` | Caminho do banco |
| `MONITOR_PORTA` | `5000` | Porta do Flask |
| `MONITOR_TENTATIVAS` | `5` | Tentativas de leitura por ciclo |
| `MONITOR_RUIDO_DISPOSITIVO` | `plughw:CARD=sndrpigooglevoi,DEV=0` | Dispositivo ALSA do microfone |
| `MONITOR_RUIDO_CANAL` | `0` | Canal com microfone: 0 esquerdo, 1 direito |
| `MONITOR_RUIDO_JANELA` | `60` | Segundos de áudio por LAeq gravado |
| `MONITOR_RUIDO_OFFSET` | `120.0` | Offset de calibração, em dB |

O padrão de `MONITOR_SENSOR` é o sensor real de propósito. Se o driver não
estiver carregado no Pi, queremos um erro visível, não dados simulados
entrando no banco em silêncio.

As três implementações:

| Valor | Como lê |
| --- | --- |
| `dht11` | Driver de kernel do Linux, via sysfs. É o recomendado |
| `dht11-blinka` | Biblioteca da Adafruit, contando pulsos em Python |
| `simulado` | Valores gerados, sem hardware |

## APIs

| Rota | Devolve |
| --- | --- |
| `GET /api/latest` | Última leitura de ar e de ruído, idade e classificação |
| `GET /api/history?horas=24&pontos=500` | Série de ar do período, reduzida a no máximo `pontos` |
| `GET /api/ruido/history?horas=24&pontos=500` | Série de ruído, com LAeq, máximo e mínimo |
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

CREATE TABLE leituras_ruido (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    INTEGER NOT NULL,  -- epoch UTC, fim da janela de integração
    laeq  REAL    NOT NULL,  -- nível equivalente da janela, dB(A)
    lamax REAL    NOT NULL,  -- maior nível de 1 s na janela, dB(A)
    lamin REAL    NOT NULL   -- menor nível de 1 s na janela, dB(A)
);
```

Ruído tem tabela própria porque a cadência e o significado são outros: uma
linha por janela de integração, não uma por leitura instantânea.

A redução do histórico de ruído usa um agregado próprio, `media_energetica`,
registrado no SQLite em `database.py`. `AVG()` sobre decibel daria resultado
errado — a escala é logarítmica, então 40 dB e 80 dB não têm média 60, têm
quase 80.

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
| Ruído | até 50 dB(A) | até 65 dB(A) | acima disso |

A condição geral é sempre a pior das três. Se não houver medição de ruído
recente, ela considera só temperatura e umidade.

Os limites de ruído são de **conforto**, não de insalubridade: a NBR 10152
recomenda entre 35 e 45 dB(A) para escritório. O limite ocupacional da NR-15
Anexo 1 é outro assunto, 85 dB(A) para 8 horas, e exige decibelímetro
calibrado.

**Estes limites são provisórios.** São um ponto de partida de conforto de
ambiente interno, não uma norma aplicada, e precisam ser definidos e
fundamentados. Vale lembrar, ao revisar: a umidade do DHT11 tem precisão de
±5%, então limites muito estreitos dariam uma falsa sensação de exatidão.

## Sobre o ruído

### Por que é uma estatística, não uma leitura

Temperatura se lê uma vez por minuto e cada valor vale por si. Ruído não
funciona assim: o microfone é amostrado a 48 kHz sem interrupção, e cada janela
de tempo vira um número só, o **LAeq** — nível equivalente contínuo ponderado
em A. É assim que toda norma de ruído mede, porque é a energia acumulada que
importa, não o valor de um instante.

Por isso o coletor de ruído é um processo à parte, com cadência própria. A
própria taxa do áudio serve de relógio: cada bloco lido é exatamente um segundo
de som, então a janela fecha contando blocos, sem depender do agendador.

Cada janela grava três números:

| Campo | O que é |
| --- | --- |
| `laeq` | Nível equivalente da janela: a energia média |
| `lamax` | O maior nível de 1 s dentro da janela |
| `lamin` | O menor nível de 1 s dentro da janela |

O máximo existe porque a média esconde picos. Uma janela com LAeq de 50 dB(A) e
máximo de 80 dB(A) é um ambiente calmo com eventos altos, o que é bem diferente
de um ambiente constante a 50.

### Ponderação A

Os limites normativos são todos em dB(A), que aplica uma curva imitando a
sensibilidade do ouvido — o grave é descontado, a faixa da fala é realçada. Sem
ela o número não é comparável com norma nenhuma.

A curva é aplicada no domínio da frequência, por FFT, e não por filtro IIR. O
motivo é prático: um filtro IIR é sequencial, amostra por amostra, e em Python
isso não acompanha 48 mil amostras por segundo num Raspberry Pi 3. Como aqui só
interessa o nível, e não o sinal filtrado, as duas abordagens dão o mesmo
resultado.

A implementação é conferida contra a tabela da IEC 61672-1 de 31,5 Hz a 16 kHz.

### Calibração

**O valor absoluto não vale nada até ser calibrado.** O nível medido é em dBFS,
relativo ao fundo de escala digital; virar dB SPL exige somar um offset. O
padrão de `MONITOR_RUIDO_OFFSET` sai da sensibilidade de catálogo do INMP441
(-26 dBFS para 94 dB SPL, ou seja, 120), mas cada módulo varia.

Para calibrar de verdade é preciso comparar com um medidor de referência no
mesmo ambiente e ajustar o offset pela diferença. Enquanto isso não for feito, o
dashboard exibe um aviso e o campo `calibrado` da API vem `false`. A variação
relativa, essa é confiável desde o primeiro minuto.

E vale repetir: **isto não é um decibelímetro**. A NR-15 Anexo 1, para ruído
ocupacional, e a NBR 10151, para ruído em comunidades, exigem instrumento Tipo 1
ou 2 com certificado de calibração. Este monitor acompanha tendência, não
sustenta laudo.

## Sobre o DHT11

### Por que o driver de kernel

Os pulsos do DHT11 duram de 26 a 70 microssegundos. Contar isso em Python, no
espaço do usuário, depende de o agendador do Linux não roubar o processador no
meio da medição, e ele rouba: o Linux não é um sistema de tempo real. No
Raspberry Pi 4 e anteriores o caminho da Adafruit passa raspando, com muitas
falhas; no Raspberry Pi 5 não funciona de jeito nenhum, porque o controlador de
GPIO mudou para o chip RP1.

O driver de kernel mede os pulsos por interrupção, com carimbo de tempo feito
pelo próprio kernel, e não sofre disso. Ele já vem no Raspberry Pi OS e não
exige biblioteca Python nenhuma.

Sintoma típico de quem está no caminho errado: `DHT sensor not found, check
wiring` de forma consistente, mesmo com a ligação correta. A mensagem culpa a
fiação, mas o que houve foi que nenhum pulso chegou a ser visto.

### Falhas de leitura

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
