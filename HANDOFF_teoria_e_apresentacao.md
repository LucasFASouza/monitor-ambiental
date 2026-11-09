# Monitor ambiental — material para a parte teórica e a apresentação

Documento de passagem para quem vai escrever a fundamentação e montar a
apresentação. Resume o que o aparelho faz, com que tecnologia, o que foi
decidido e por quê, e onde cada número se apoia.

O foco é no que mudou **depois da entrada do microfone**, que é quando o projeto
deixou de ser um termo-higrômetro com histórico e virou um instrumento de três
grandezas com problema metrológico próprio.

---

## 1. O que é, em uma frase

Um monitor de temperatura, umidade e ruído para escritório, montado num
Raspberry Pi 3B+, que grava o histórico no próprio aparelho e mostra numa página
acessada pela rede local se as condições estão dentro do recomendado.

**Público primário:** as pessoas que trabalham na sala. Não conhecem LAeq nem a
numeração das normas. A pergunta que elas fazem é "está adequado agora?".

**Público secundário:** quem investiga quando algo aparece fora da faixa. A
pergunta é "há quanto tempo está assim?".

Hoje o banco tem **3.306 leituras de ar** e **371 janelas de ruído**.

---

## 2. Hardware

| Peça | Função | Como se liga |
|---|---|---|
| Raspberry Pi 3B+ | computador, banco e servidor | — |
| DHT11 | temperatura e umidade | 3,3 V, GND e dados no GPIO4 (pino 7) |
| INMP441 | microfone MEMS digital, I2S | VDD 3,3 V, GND, SCK no GPIO18, WS no GPIO19, SD no GPIO20, L/R em GND |

O `L/R` em GND escolhe o canal esquerdo. Não é alimentação: é entrada de
configuração.

Os dois sensores não disputam pino nenhum — o DHT11 usa GPIO4 e o I2S usa um
barramento separado.

---

## 3. A decisão do microfone

### Por que um microfone I2S, e não um sensor de ruído pronto

Os módulos baratos vendidos como "sensor de som" (KY-037, KY-038 e similares)
entregam **um nível de tensão ou um comparador liga-desliga**, não áudio. Com
eles não dá para calcular LAeq nem aplicar ponderação A, porque não há sinal
para analisar — só uma indicação grosseira de "tem som" ou "não tem".

O INMP441 é um microfone MEMS com saída digital I2S: entrega a forma de onda
amostrada. É isso que permite calcular um número comparável com norma. Custa na
mesma faixa dos módulos inúteis.

### Por que ruído não é uma leitura como as outras

Temperatura e umidade são medidas instantâneas: lê-se o sensor e tem-se o valor.
**Ruído é estatística.** O nível flutua a cada fração de segundo, e o que as
normas medem é a energia acumulada numa janela de tempo — o **LAeq**, nível
equivalente contínuo ponderado em A.

No aparelho isso significa:

- o microfone é amostrado continuamente a **48 kHz**;
- cada **janela de 60 segundos** vira um número só;
- a média entre janelas é **energética**, não aritmética: decibel é escala
  logarítmica, e somar decibéis como se fossem notas de prova dá resultado
  errado.

### Ponderação A

A curva de **ponderação A** imita a sensibilidade do ouvido humano, que escuta
muito pior nos graves. Está definida na **IEC 61672-1**. Todos os limites
normativos de ruído são em dB(A), então sem ela o número não é comparável com
norma nenhuma.

Implementada por FFT, não por filtro recursivo: em Python puro um filtro IIR não
dá conta de 48.000 amostras por segundo. A implementação foi conferida contra a
tabela de valores da própria norma, com diferença máxima de **0,13 dB**.

### A calibração: de dBFS para dB(A)

O microfone mede em **dBFS** — decibéis relativos ao fundo de escala do próprio
circuito. Para virar dB(A) é preciso somar um *offset* levantado contra um
medidor de referência. O valor de catálogo do INMP441 (120,0 dB) é ponto de
partida, não medição.

**A calibração foi feita.** O registro, com rastreabilidade completa:

| | |
|---|---|
| Referência mostrou | 30,0 dB(A) |
| Este monitor mediu | −69,1 dBFS |
| Offset gravado | **+99,1 dB** (catálogo era 120,0) |
| Janela comparada | 5 minutos, 5 leituras |
| Instrumento de referência | medidor de navegador (decibelmeter.org) |

A apresentação deve dizer **qual foi a referência**, porque isso define o grau
de confiança do número: um medidor de navegador não é instrumento com
certificado de calibração, e em níveis baixos ele esbarra no próprio piso de
ruído. A faixa de incerteza do valor absoluto é a do instrumento usado para
ancorá-lo. Refazer a comparação contra um decibelímetro Tipo 2 apertaria essa
incerteza, e o aparelho aceita recalibração a qualquer momento.

O campo de instrumento existe no formulário exatamente para que essa informação
não se perca — e foi ele que permitiu escrever este parágrafo.

### O que o microfone **não** resolve

Avaliação de insalubridade por ruído exige medidor com certificado de calibração
rastreável — **NR-15, Anexo 1**, que fixa 85 dB(A) para 8 horas de exposição.
Este aparelho não substitui isso. Os limites que ele usa são de **conforto**, não
de insalubridade.

---

## 4. A outra limitação de escopo: IBUTG

Durante o projeto ficou claro que, para higiene ocupacional de **calor**, o
equipamento também não serve. A avaliação é feita pelo **IBUTG** (Índice de Bulbo
Úmido Termômetro de Globo), que exige medir três componentes: bulbo seco, bulbo
úmido natural e **termômetro de globo**, este último para calor radiante.

O DHT11 mede só bulbo seco e umidade relativa. **Não mede calor radiante, então
não serve para IBUTG.** A metodologia de referência é a **NHO-06 da Fundacentro**.

Isso foi uma decisão de escopo consciente: o aparelho mede conforto, não
insalubridade.

---

## 5. Tecnologias

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.11 | biblioteca científica disponível e já presente no sistema |
| Leitura do DHT11 | driver de kernel do Linux (`dtoverlay=dht11`) | ver abaixo |
| Captura de áudio | `arecord` em subprocesso, áudio cru S32_LE | já vem com o sistema; evita compilar PortAudio no Pi |
| Processamento de sinal | NumPy (FFT) | ponderação A em tempo real |
| Banco | SQLite com WAL | arquivo único, sem servidor, leitura e escrita simultâneas |
| Servidor | Flask | o menor que resolve, para poucos clientes na rede local |
| Gráfico | Chart.js, servido pelo próprio aparelho | ver abaixo |
| Serviços | systemd, três unidades independentes | ver abaixo |

### Duas escolhas que merecem explicação na apresentação

**O DHT11 é lido pelo driver de kernel, não por biblioteca em Python.** Os pulsos
do sensor duram de 26 a 70 microssegundos. Contar isso em Python, num sistema
operacional que pode interromper o processo a qualquer momento, erra muito. O
kernel do Linux tem um driver pronto que faz a contagem com precisão de
interrupção e entrega o valor por arquivo de sistema. A troca eliminou a maior
parte das leituras inválidas.

**O gráfico é desenhado no navegador, com a biblioteca servida pelo próprio
aparelho.** Houve uma versão em SVG gerado no servidor, mais leve. Foi revertida:
numa série temporal, passar o mouse e ler o valor de um ponto é função, não
enfeite. Nada vem de CDN porque o monitor precisa funcionar sem internet.

### Três processos independentes

Coletor de ar, coletor de ruído e dashboard rodam separados, sob systemd, com
reinício automático. Se o dashboard cair, a coleta continua. Se um coletor
parar, o outro segue. Todos sobem sozinhos quando o aparelho é ligado.

---

## 6. Os limites e de onde vêm

Esta é a seção mais importante para a parte teórica, porque é onde o projeto se
sustenta ou não.

| Grandeza | Faixa recomendada | Fonte |
|---|---|---|
| Temperatura | 18 a 25 °C | **NR-17, item 17.8.4.2**, na redação da Portaria MTP 423/2021 |
| Umidade relativa | 40 a 60 % | convergência de **OSHA/ASHRAE 55** com a ANVISA revogada — ver abaixo |
| Ruído | até 45 dB(A), teto de 65 dB(A) | **NBR 10152:2017** (escritório privativo) e **NR-17, item 17.8.4.1.2** |

Notas:

- O piso de **18 °C** coincide com o mínimo das *Housing and health guidelines*
  da **OMS (2018)**, por caminho independente. Vale citar: duas fontes
  diferentes chegando ao mesmo número reforçam o argumento.
- Os **65 dB(A)** são literais da NR-17, que os define como nível de ruído de
  fundo aceitável para conforto acústico, medido como nível contínuo equivalente
  ponderado em A — exatamente o que o aparelho calcula.
- Os **45 dB(A)** da NBR 10152:2017 são o nível de conforto para escritório
  privativo, mais exigente que o teto da NR-17.

### A umidade: como a faixa foi definida

A umidade **não tem norma brasileira vigente com faixa numérica**, e a definição
foi feita por convergência de fontes — o que precisa ser apresentado como
escolha fundamentada, não como lacuna.

As fontes:

- **RE 09/2003 da ANVISA** indicava 40 a 65 % no verão. **Revogada em julho de
  2024** pela RDC 886/2024. Citar apenas como histórico.
- **OSHA** recomenda 20 a 60 %, sem caráter obrigatório, apoiada na
  **ASHRAE 55**.
- A **NR-17** manda controlar a umidade, mas perdeu o número na revisão de 2021.

A faixa adotada, **40 a 60 %**, é a que aparece de forma consistente nas fontes
como a que minimiza **ao mesmo tempo** proliferação biológica (que cresce com
umidade alta) e irritação de vias aéreas (que cresce com umidade baixa). É a
interseção da recomendação da OSHA com o piso da ANVISA revogada.

A margem de atenção, **30 a 70 %**, tem razão própria: abaixo de 30 % a
irritação de vias aéreas é documentada, e acima de 70 % o risco de mofo cresce
rápido.

**O que falta checar:** a substituta da RE 09/2003 é a **ABNT NBR 17037**, norma
paga, não consultada. Se o trabalho precisar citar norma vigente para umidade, é
ela. Enquanto isso, a honestidade é dizer "convergência de fontes" — que é o que
o aparelho escreve na própria tela — em vez de citar norma revogada como se
estivesse em vigor.

### Por que a faixa de umidade não é mais estreita

O DHT11 tem precisão de **±5 %** na umidade e resolução de **1 °C** na
temperatura. Limites mais apertados que a precisão do sensor dariam falsa
sensação de exatidão.

---

## 7. O fluxo de páginas

São três páginas, e a divisão entre elas segue um critério: **o que a pessoa
precisa agora fica no painel; o que o aparelho sabe sobre si mesmo fica na
subpágina.**

```
        ┌─────────────────────────────────────────┐
        │  /  — Painel                            │
        │                                         │
        │  As três grandezas: condição, valor     │
        │  e histórico. Filtro de período.        │
        └───────┬──────────────────────┬──────────┘
                │                      │
      "calibrar" no setor    "Informações do sistema"
          de ruído                 no rodapé
                │                      │
                ▼                      ▼
   ┌────────────────────┐   ┌────────────────────────┐
   │ /calibracao        │◄──│ /sistema               │
   │                    │   │                        │
   │ Ancorar o dB(A)    │   │ Estado da coleta,      │
   │ num medidor de     │   │ calibração, limites    │
   │ referência         │   │ do aparelho, exportar  │
   └────────────────────┘   └────────────────────────┘
```

### `/` — Painel

A resposta à pergunta "está adequado agora?".

Para cada uma das três grandezas: um ícone na cor do estado, o nome, **a
condição dita por extenso em português** ("Dentro da faixa recomendada", "Acima
da faixa recomendada"), o valor medido, e o gráfico do período.

Elementos que valem mencionar na apresentação:

- **A condição é texto antes de ser cor.** Cor nunca carrega significado
  sozinha — quem não distingue verde de vermelho lê a mesma informação.
- **Filtro de período:** 6 horas, 24 horas, 7 dias, 30 dias.
- **Ícone de informação** em cada gráfico, que abre a explicação do que a faixa
  significa e a norma que a sustenta.
- **No celular**, uma frase no topo resume o conjunto: "O ruído está acima da
  faixa recomendada. A temperatura e a umidade estão dentro." Existe porque em
  tela estreita a grandeza fora da faixa fica abaixo da dobra.
- **Leitura velha é degradada, não maquiada:** se a coleta parou, o ícone fica
  cinza, o valor apaga e a frase vira "Sem leitura há X". Cada grandeza tem a
  própria idade.
- **Botão de exportar** o período em CSV.

### `/sistema` — Informações do sistema

O que o aparelho sabe sobre si mesmo. Quatro seções:

1. **Coleta nas últimas 24 horas** — quantas leituras, quanto do esperado, e
   quantas interrupções. Serve para saber se o histórico é confiável.
2. **Calibração do ruído** — se já foi ancorada num medidor de referência, com a
   ficha de rastreabilidade da última calibração.
3. **O que este monitor não mede** — higiene ocupacional, IBUTG, e a precisão do
   DHT11. Declarado, não escondido.
4. **Exportar dados** — um arquivo por período.

### `/calibracao` — Calibrar o nível de ruído

Onde se ancora o dB(A). O procedimento: deixar um medidor de referência ao lado
do aparelho por alguns minutos, e informar o LAeq que ele acumulou e por quanto
tempo.

Duas decisões técnicas que valem na apresentação:

- **A comparação é feita sobre a mesma janela de tempo, nunca sobre um
  instante.** O ruído flutua a cada segundo; comparar duas leituras pontuais é
  comparar ruído com ruído. Se não houver leituras suficientes no período, a
  gravação é **recusada** em vez de produzir um offset instável.
- **O banco guarda o nível cru, em dBFS.** Recalibrar reinterpreta todo o
  histórico, sem reescrever nada. Sem isso, cada calibração criaria um degrau
  invisível no gráfico, com o passado numa escala e o futuro em outra.

---

## 8. Princípios de produto que guiaram as decisões

Úteis como fio condutor da apresentação:

1. **A pergunta é "está adequado?", não "qual o número".** A resposta vem em
   frase, em português, antes de qualquer cor ou valor.
2. **Todo limite exibido carrega sua fonte.** Limite sem norma vigente diz que
   não tem.
3. **O monitor relata o que não sabe.** Leitura perdida, buraco no histórico e
   nível não calibrado aparecem na tela. Num contexto ocupacional, um número
   errado com aparência de certo é pior que uma lacuna admitida.
4. **Exposição no tempo é a unidade de análise, não o instante.**
5. **Nunca sugerir que isto substitui instrumento com certificado de
   calibração.**

---

## 9. Escopo de acesso

O dashboard é **restrito à rede local do escritório**, por decisão de segurança
e escopo. Acessível por `http://monitorpi.local:5000` ou pelo IP do aparelho.

A razão técnica de não expor para fora: **a página não tem autenticação**, e as
rotas de calibração alteram como todo o histórico de ruído é lido. Uma URL
pública sem controle de acesso permitiria que qualquer pessoa recalibrasse o
monitor.

---

## 10. O que falta

**As três análises de histórico**, que respondem a segunda pergunta do produto,
"há quanto tempo está assim?":

- tempo de exposição por faixa;
- resumo diário de mínimo, máximo e média;
- registro de excursões — quando saiu da faixa e por quanto tempo.

Elas dependem de **deixar o sistema ligado acumulando dados**, que é o estado
atual do projeto. Hoje o banco tem 3.306 leituras de ar e 371 janelas de ruído.

Duas coisas que podem ser apertadas, mas não bloqueiam nada:

- **recalibrar o ruído** contra um decibelímetro Tipo 2, para reduzir a
  incerteza do valor absoluto (ver seção 3);
- **consultar a ABNT NBR 17037** se o trabalho precisar de norma vigente para
  umidade (ver seção 6).

## 11. Referências para citar

**Normas brasileiras**

- **NR-17 — Ergonomia**, na redação da Portaria MTP 423/2021. Itens 17.8.4.1.2
  (ruído de fundo, 65 dB(A)) e 17.8.4.2 (temperatura, 18 a 25 °C).
- **NR-15, Anexo 1** — limites de tolerância para ruído contínuo, 85 dB(A) para
  8 horas. Citada para delimitar o que o projeto **não** faz.
- **ABNT NBR 10152:2017** — níveis de pressão sonora em ambientes internos.
  45 dB(A) para escritório privativo.
- **ABNT NBR 17037** — substituta da RE 09/2003 da ANVISA. Não consultada,
  norma paga.
- **RE 09/2003 da ANVISA** — revogada em julho de 2024 pela RDC 886/2024. Citar
  apenas como histórico, nunca como vigente.
- **NHO-06 da Fundacentro** — metodologia de IBUTG. Citada para delimitar
  escopo.

**Normas internacionais**

- **IEC 61672-1** — ponderação A e classes de medidor de nível sonoro.

**Recomendações internacionais (não obrigatórias)**

- **OSHA** — faixa de umidade relativa de 20 a 60 % para ambiente de trabalho.
- **ASHRAE 55** — *Thermal Environmental Conditions for Human Occupancy*, base
  da recomendação da OSHA.

**Saúde pública**

- **OMS, WHO Housing and health guidelines (2018)** — mínimo de 18 °C para
  ambiente interno.

**Documentação técnica**

- Datasheet do **INMP441** (InvenSense) — fundo de escala e saída I2S.
- Datasheet do **DHT11** — faixas de operação e precisão.

---

## 12. Onde está cada coisa no código

Para quem precisar conferir uma afirmação:

| Arquivo | O que tem |
|---|---|
| `config.py` | todos os limites, **com a procedência de cada número em comentário** |
| `sensor_ruido.py` | ponderação A, LAeq, média energética, captura |
| `sensor.py` | leitura do DHT11 por driver de kernel |
| `painel.py` | o que cada grandeza mostra, como a condição é escrita, janela do gráfico |
| `database.py` | esquema, calibração, saúde da coleta |
| `PRODUCT.md` | público, princípios e limitações declaradas |
| `DESIGN.md` | decisões visuais e suas razões |
| `README.md` | ligação dos sensores, instalação, operação |
