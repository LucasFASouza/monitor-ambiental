# Monitor Ambiental

Monitor de temperatura, umidade e ruído num Raspberry Pi: coleta contínua,
histórico em SQLite e um dashboard web acessível pela rede local.

```text
DHT11    ┐
         ├→ Raspberry Pi → SQLite → Flask → navegador
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
| `painel.py` | Monta a visão da página: o que cada grandeza mostra e como se lê |
| `avaliacao.py` | Classificação em Bom, Atenção e Ruim |
| `teste_dht.py` | Teste isolado do sensor, sem banco e sem Flask |
| `templates/` | As três páginas: painel, sistema e calibração |
| `deploy/` | Units de systemd para os dois coletores e o dashboard |
| `scripts/` | Semear histórico simulado: `semear.py` para trabalhar sem o Raspberry, `semear_demo.py` para a demonstração de escritório |

São três processos independentes: o coletor de ar, o coletor de ruído e o
dashboard. Se o Flask cair, a coleta continua. Se um coletor parar, o outro
segue, e o dashboard mostra os dados que existem avisando que estão velhos, em
vez de exibir um número antigo como se fosse atual.

## Publicar uma cópia estática

Uma cópia somente leitura do painel, para acesso fora da rede local sem expor o
aparelho. Não é permissão, é construção: são arquivos, não há servidor, e não
existe rota de calibração para proteger porque não existe rota.

```bash
python scripts/publicar.py --saida publicado   # gera
scripts/publicar.sh                            # gera e publica no gh-pages
```

O renderizador usa o cliente de teste do Flask e trata o HTML: tira a entrada
de calibração e o botão de exportar, que num arquivo estático não levam a lugar
nenhum, tira o ciclo de atualização que buscaria `/api/painel`, reescreve os
caminhos para relativos e carimba a data de geração. Publica 24 horas, 7 dias e
a página de sistema, com 278 KB no total — dos quais 204 são o Chart.js, que o
navegador guarda em cache.

Cada remoção é feita por marcador exato e conferida. Se um template mudar de
forma, o script falha em vez de publicar uma página quebrada em silêncio.

No aparelho, `deploy/monitor-publicar.timer` dispara a cada 30 minutos. O
branch publicado tem sempre um commit só, por push forçado: a cada 30 minutos,
guardar histórico seriam dezenas de megabytes por mês. O histórico dos dados
está no banco; isto é uma vitrine.

Precisa de chave de deploy com escrita no GitHub e do remoto por SSH — com
HTTPS o push pede senha e o timer trava. Teste à mão antes de habilitar.

## Demonstração calibrada contra o sensor real

`scripts/semear_realista.py` gera sete dias cujos números saem de uma exportação
real de 24 h do aparelho — 704 leituras de ar e 662 janelas de ruído — estendida
pelo tempo de São Paulo. O dia 09/11 tem leitura real de dentro e de fora ao
mesmo tempo, e é dele que sai a relação entre os dois.

```bash
MONITOR_DB=data/demo.db python scripts/semear_realista.py
MONITOR_DB=data/demo.db MONITOR_PORTA=5088 python app.py
```

O que foi medido e aplicado está em `MEDIDO`, no topo do script.

## Demonstração

Um histórico simulado de escritório formal, para mostrar o produto sem depender
de coleta real: ar-condicionado das 6h às 19h em 22 °C, chegada entre 8h e 10h,
almoço entre 12h e 14h, saída por volta das 18h30. Terça e quinta cheios,
quarta intermediária, segunda e sexta vazios; fim de semana sem ar.

```bash
MONITOR_DB=data/demo.db python scripts/semear_demo.py
MONITOR_DB=data/demo.db MONITOR_PORTA=5088 python app.py
```

Banco e porta separados de propósito. O script se recusa a rodar se o caminho
do banco não contiver "demo", porque os registros gerados são indistinguíveis
dos reais depois de gravados.

O tempo externo é o de Mogi das Cruzes, e a aleatoriedade não é arbitrária: a
textura estatística — quanto o sensor segura o valor, de quanto são os degraus,
qual o desvio do passo do LAeq — sai medida dos dados reais do aparelho. Ver
`TEXTURA` no script.

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

O `enable` é o que faz tudo subir sozinho quando o aparelho é ligado. Com
`Restart=always` e `RestartSec=10`, serviço que falhe na largada tenta de novo
indefinidamente — o coletor de ruído pode precisar disso, porque a placa I2S
nem sempre está enumerada quando o `arecord` é chamado, e o `After=sound.target`
do systemd não garante essa espera.

Depois do primeiro boot com os três instalados, vale conferir que foi assim:

```bash
journalctl -b -u monitor-coletor -u monitor-coletor-ruido -u monitor-dashboard | head -20
systemctl show monitor-coletor-ruido -p NRestarts --value
```

### Atualizar depois

Trocar o código não basta: os serviços seguem rodando o que carregaram no
início. Depois de um `git pull`, reinicie o que mudou.

```bash
cd ~/monitor-ambiental && git pull && sudo systemctl restart monitor-coletor monitor-coletor-ruido monitor-dashboard
```

Sem o `restart`, o sintoma é confuso: o arquivo novo está no disco, mas a API
responde como antes — inclusive 404 em rota recém-criada.

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
O offset de calibração do ruído **não é variável de ambiente**: vive no banco,
na tabela `configuracao`, e é gravado pela página de calibração. Ver a seção de
calibração adiante.

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
| `GET /api/painel` | Todo o view model da página, para atualizar sem recarregar |
| `GET /api/calibracao` | Estado da calibração do ruído |
| `POST /api/calibracao` | Grava uma calibração; recusa janela insuficiente com 409 |
| `GET /exportar.csv?horas=24` | Ar e ruído no mesmo arquivo, uma linha por minuto |

E três páginas:

| Rota | Função |
| --- | --- |
| `GET /` | Painel: condição, valor e histórico das três grandezas |
| `GET /sistema` | Saúde da coleta, calibração, limites do aparelho e exportação |
| `GET /calibracao` | Ancorar o dB(A) num medidor de referência |

As datas saem em ISO 8601 UTC; o navegador converte para a hora local.

O painel se atualiza buscando `/api/painel`, não recarregando o documento:
recarregar descartava o scroll, reanunciava a página inteira para leitor de tela
e fechava qualquer painel de informação aberto.

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

Os limites ficam em `config.py`, em `LIMITES`, com a fonte de cada número
documentada ali.

| Grandeza | Bom | Atenção | Ruim | Origem do "Bom" |
| --- | --- | --- | --- | --- |
| Temperatura | 18 a 25 °C | 16 a 28 °C | fora disso | NR-17, item 17.8.4.2 |
| Umidade | 40 a 60 % | 30 a 70 % | fora disso | convergência de fontes |
| Ruído | até 45 dB(A) | até 65 dB(A) | acima disso | NBR 10152:2017 |

A condição geral é sempre a pior das três. Se não houver medição de ruído
recente, ela considera só temperatura e umidade.

A faixa **Bom** vem de norma vigente onde existe uma. A faixa **Atenção** é uma
margem escolhida a partir das fontes, não um valor normativo: serve para
separar "fora do recomendado" de "ruim mesmo".

### De onde vem cada número

**Temperatura.** A NR-17, no item 17.8.4.2 (redação da Portaria MTP 423/2021),
estabelece "faixa de temperatura do ar entre 18 e 25 °C para ambientes
climatizados". É norma de segurança do trabalho em vigor. O piso de 18 °C bate,
por caminho independente, com o mínimo das *Housing and health guidelines* da
OMS (2018), onde a justificativa é mortalidade por frio e não conforto.

**Ruído.** O teto de 65 dB(A) da faixa Atenção é literal da NR-17, item
17.8.4.1.2: "o nível de ruído de fundo aceitável para efeito de conforto
acústico será de até 65 dB(A), nível de pressão sonora contínuo equivalente
ponderado em A e no circuito de resposta Slow (S)". É exatamente a grandeza que
este monitor calcula, o LAeq. O limite de 45 dB(A) para Bom vem da NBR
10152:2017, que indica cerca de 40 dB(A) como valor de projeto para escritório
privativo e admite tolerância de até 5 dB.

Nada disso é limite de insalubridade. Exposição ocupacional ao ruído é a NR-15
Anexo 1, com 85 dB(A) para 8 horas, e exige medidor Tipo 1 ou 2 com certificado
de calibração.

**Umidade é o ponto fraco.** Não há número normativo vigente que tenha sido
verificado em fonte oficial aberta:

- a NR-17 perdeu o número de umidade na revisão de 2021 — o item 17.8.4.2 manda
  controlar a umidade, mas não diz qual faixa;
- a RE 09/2003 da ANVISA, que indicava 40 a 65 % no verão, foi revogada em
  julho de 2024 pela RDC 886/2024;
- o que a substituiu é a ABNT NBR 17037, norma paga, não consultada aqui;
- a recomendação da OSHA (20 a 60 %) não tem caráter obrigatório nem é
  brasileira.

A faixa de 40 a 60 % é a que aparece de forma consistente nessas fontes como a
que minimiza tanto proliferação biológica quanto irritação respiratória, mas
ela é convergência, não norma. Se este projeto for usado para fundamentar
alguma coisa, é aqui que falta checagem.

E vale lembrar ao revisar: a umidade do DHT11 tem precisão de ±5%, então
limites mais estreitos que isso dariam uma falsa sensação de exatidão.

## Sobre o gráfico

O gráfico é desenhado pelo Chart.js no cliente, com a biblioteca servida pelo
próprio aparelho — nada de CDN, porque o monitor funciona sem internet. A
semântica é decidida no servidor e mandada pronta em JSON: janela do eixo,
faixas, limites e agregação. Houve uma versão em SVG gerado no servidor, mais
leve, mas ela não tinha o que importa numa série temporal: passar o mouse e ler
o valor de um ponto. Sem JavaScript, cada gráfico vira um resumo em texto.

Quatro decisões de legibilidade, cada uma corrigindo um erro concreto:

**Eixo Y fixo nas faixas de classificação, nunca autoescalado nos dados.**
Autoescala transforma 0,9 °C de variação num penhasco e esconde que a sala
está estável.

**A série é a média de baldes, com o mínimo e o máximo do balde atrás, como
envelope.** Amostra crua em 288 pontos vira faixa peluda; a média sozinha
apagaria o pico, que em ruído é a informação.

**As faixas aparecem numa régua no próprio eixo**, e não preenchendo a área de
plotagem. Preenchimento tinge tudo e mata a leitura da série.

**O limite normativo é régua anotada numa calha à direita**, em tom de
anotação. Rótulo dentro da área colide com a série, e vermelho ali mente,
porque 18 e 25 °C são os limites do que é bom.

O eixo Y não imprime valor nenhum: a escala é dada pela régua de faixas e pelos
rótulos das linhas de referência, cada um com a sua unidade. A coluna de números
repetia a unidade a cada marca e afastava a régua da curva que ela qualifica.

As linhas do vermelho — 16 e 28 °C, 30 e 70 % — só aparecem quando a faixa
vermelha está em vista. Fora disso elas coincidem com os limites da janela e
seriam desenhadas em cima da moldura.

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
relativo ao fundo de escala digital; virar dB SPL exige somar um offset. O valor
inicial, 120, sai da sensibilidade de catálogo do INMP441 (-26 dBFS para
94 dB SPL), mas cada módulo varia — e catálogo não é medição.

A calibração é feita pela página `/calibracao`: deixa-se um medidor de
referência no mesmo ponto por alguns minutos e informa-se o LAeq que ele
acumulou e por quanto tempo. A comparação é sobre a **mesma janela de tempo**,
nunca sobre um instante, porque o ruído flutua a cada segundo e comparar duas
leituras pontuais é comparar ruído com ruído. Sem leituras suficientes no
período, a gravação é recusada em vez de produzir um offset instável.

**O banco guarda o nível cru, em dBFS.** Recalibrar reinterpreta todo o
histórico sem reescrever nada. Sem isso, cada calibração criaria um degrau
invisível no gráfico, com o passado numa escala e o futuro em outra.

Enquanto não houver calibração, o dashboard avisa na seção de ruído e o campo
`calibrado` da API vem `false`. A variação relativa, essa é confiável desde o
primeiro minuto.

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

**Três análises de histórico** que respondem a segunda pergunta do produto, "há
quanto tempo está assim?": tempo de exposição por faixa, resumo diário de
mínimo, máximo e média, e registro de excursões — quando saiu da faixa e por
quanto tempo. Dependem de deixar o sistema ligado acumulando dados, que é o
estado atual do projeto.

Duas coisas que podem ser apertadas, mas não bloqueiam nada: **recalibrar o
ruído** contra um decibelímetro Tipo 2, já que a calibração em vigor foi feita
contra um medidor de navegador, e **consultar a ABNT NBR 17037** se for preciso
citar norma vigente para umidade.

**Acesso só pela rede local**, por decisão de segurança e escopo. A página não
tem autenticação e as rotas de calibração alteram como todo o histórico de ruído
é lido, então expor para fora exigiria controle de acesso antes. Quem precisar
olhar de outra rede, o caminho seria um túnel (Tailscale ou Cloudflare), não
redirecionamento de porta.

O `app.py` sobe o servidor de desenvolvimento do Flask, o que é adequado para um
protótipo na rede local. Se o dashboard virar algo permanente, trocar por
`waitress` é uma linha.

## Para a parte teórica e a apresentação

Ver [HANDOFF_teoria_e_apresentacao.md](HANDOFF_teoria_e_apresentacao.md):
resumo do que foi feito, decisões com a razão de cada uma, o fluxo de páginas e
as referências normativas prontas para citar.
