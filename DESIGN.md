---
name: Monitor Ambiental
description: Painel de temperatura, umidade e ruído que diz a quem trabalha no ambiente se as condições estão adequadas.
colors:
  capa: "#0d6a66"
  capa-fundo: "#0a5753"
  capa-texto: "#eaf4f3"
  capa-fraco: "#c8e3e0"
  capa-vivo: "#8fd9a8"
  capa-parado: "#ffd166"
  papel: "#ffffff"
  ambiente: "#f4f6f6"
  tinta: "#17202a"
  meio: "#5f6a74"
  fraco: "#8b949d"
  regua: "#dde2e5"
  bom: "#2f6b45"
  atencao: "#8a5e08"
  ruim: "#8f3023"
  limite: "#8a6a20"
  faixa-bom: "#3f8f58"
  faixa-atencao: "#c98a12"
  faixa-ruim: "#a8392c"
typography:
  situacao:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 400
    lineHeight: 1.5
  titulo:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "-0.012em"
  grandeza:
    fontSize: "1.125rem"
    fontWeight: 600
  valor:
    fontSize: "2.125rem"
    fontWeight: 600
    letterSpacing: "-0.025em"
    lineHeight: 1.05
  corpo:
    fontSize: "1rem"
    lineHeight: 1.6
  apoio:
    fontSize: "0.875rem"
    lineHeight: 1.6
rounded:
  nenhum: "0px"
spacing:
  e1: "4px"
  e2: "8px"
  e3: "12px"
  e4: "16px"
  e5: "24px"
  e6: "32px"
  e7: "48px"
  e8: "64px"
components:
  capa:
    backgroundColor: "{colors.capa}"
    textColor: "{colors.capa-texto}"
    padding: "24px 32px 0"
  periodo-item:
    textColor: "{colors.meio}"
    padding: "8px 12px"
    minHeight: "44px"
  periodo-item-ativo:
    backgroundColor: "{colors.capa}"
    textColor: "{colors.capa-texto}"
    fontWeight: 600
  marca:
    size: "48px"
    strokeWidth: "1.9px"
    stroke: "estado"
  grandeza:
    borderTop: "1px solid {colors.regua}"
    padding: "32px 0"
  grafico-regua-faixa:
    width: "9px"
  grafico-limite:
    stroke: "{colors.limite}"
    strokeWidth: "1px"
  grafico-serie:
    stroke: "{colors.tinta}"
    strokeWidth: "1.9px"
  grafico-envelope:
    fill: "rgba(23,32,42,.17)"
---

## Overview

Instrumento de leitura, não painel de marketing. O público primário são pessoas
que trabalham no ambiente monitorado e não conhecem LAeq nem a numeração das
normas; o secundário investiga quando algo aparece fora da faixa. A tela
responde "está adequado agora?" em uma frase, e guarda o histórico para a
segunda pergunta.

O mundo vem da Caderneta de Saúde da Criança: cor institucional saturada
ocupando região inteira, e a faixa de referência impressa no próprio gráfico.
Não o papel creme com serifa, que é onde todo projeto deste tipo aterrissa.

O gráfico é o produto. Tudo o mais existe para enquadrá-lo.

## Colors

### Primary

`capa` #0d6a66 é um teal institucional que carrega o cabeçalho inteiro como
campo, não como acento. `capa-fundo` #0a5753 é o tom mais fundo para estados
pressionados dentro do campo.

### Neutral

`ambiente` #f4f6f6 é o fundo da página, `papel` #ffffff a superfície elevada
(hoje usada só onde um gráfico precisa de contraste próprio). `tinta` #17202a é
a cor do texto e `meio` #5f6a74 o texto de apoio — **são os dois únicos cinzas
de texto**. `fraco` #767f88 é só para marca e glifo, nunca para texto: na forma
anterior (#8b949d) ele media 2,84:1 sobre `ambiente` e falhava AA em todo lugar
onde foi usado como texto. `regua` #dde2e5 são as divisórias de um pixel.

Dentro do campo teal há dois tons de marca, não de texto: `capa-vivo` #8fd9a8
no ponto de coleta viva e `capa-parado` #ffd166 no de coleta parada. As cores
de estado da página não servem ali — `bom` sobre `capa` é 1,01:1.

Nenhum deles tem matiz quente. Creme é proibido aqui por decisão de direção.

### Named Rules

Estado tem duas famílias, e elas não se misturam.

As cores de **texto** de estado — `bom`, `atencao`, `ruim` — existem para a
frase que descreve a condição e passam WCAG AA sobre `ambiente`, com margem
mínima de 5,25:1.

As cores de **faixa** — `faixa-bom`, `faixa-atencao`, `faixa-ruim` — existem
só na régua do eixo do gráfico, onde são material impresso e não texto. São
mais saturadas de propósito: ali a função é marcar zona numa escala, não ser
lida.

`limite` #8a6a20 é a cor da régua de limite normativo e dos seus rótulos. É
ocre, em tom de anotação: vermelho ali mentiria, porque 18 e 25 °C são os
limites do que é **bom**.

Cor nunca é o único portador de significado. Toda condição também é dita por
extenso em texto.

## Typography

Pilha do sistema, registro de UI. Numerais tabulares em toda a página
(`font-variant-numeric: tabular-nums`), porque dígito precisa alinhar com
dígito num instrumento de medição.

### Hierarchy

Quatro degraus acima do corpo, e só quatro: a frase de situação e o título em
1,25rem; o valor medido em 2,125rem; o nome da grandeza em 1,125rem; o apoio em
0,875rem. Com o corpo em 1rem, a página inteira cabe em cinco tamanhos.

O título de uma subpágina ocupa o degrau de 2,125rem, o mesmo do valor medido.
Em 1,25rem ele ficava a 2px do cabeçalho de seção: numa página sem medição
nenhuma, como a /sistema, isso deixa a hierarquia plana.

**Dois pesos, e só dois:** 600 no título da capa, no nome da grandeza, no valor
medido e na aba ativa do filtro; 400 em todo o resto, inclusive na frase de
situação. Ela é maior que o nome da grandeza e mais leve — a resposta é o que
se lê primeiro, e peso em tudo não é hierarquia, é só barulho.

Nenhum rótulo em caixa alta acima de um número. O nome da grandeza é um
título de verdade e carrega o próprio peso.

## Layout

Coluna de conteúdo de 1120px no máximo, com 32px de margem lateral.

Cada grandeza é uma faixa horizontal de duas colunas: 290px de leitura à
esquerda, o gráfico ocupando o resto. Separadas por régua de um pixel, não por
caixa.

Mais espaço acima de um título do que abaixo dele.

Toda medida de espaço sai da escada `e1..e8`, em múltiplos de 4px. Se um valor
não está nela, está errado: foi o dimensionamento no olho, 18 de 23 medidas
fora de escala, que deu à primeira versão a cara de amadora.

### Bloco de leitura

Uma margem esquerda só. Marca, nome, frase, valor e explicação começam todos no
mesmo x. A versão anterior punha a marca num ladrilho de 42px dentro do fluxo
de texto, e nome e frase saíam 55px à direita do valor e da explicação — duas
margens esquerdas no mesmo bloco, nas três grandezas e nos três breakpoints.

A marca é glifo solto na cor do estado, sem caixa. Um quadrado saturado com
glifo vazado é o selo que esta direção proíbe: codificava estado, já dito na
frase, e categoria, já dita no título, sem acrescentar nada, e era o objeto
mais pesado da composição.

Abaixo de 760px a grandeza vira coluna única e o gráfico desce para baixo do
texto. Lado a lado em 375px espremeria os dois até nenhum ser legível.

## Elevation & Depth

Não há elevação. Nenhuma sombra, nenhum cartão, nenhum raio de canto. A
separação é feita por régua de um pixel e por espaço. O único plano que existe
é o campo saturado do cabeçalho, e ele se distingue por cor, não por altura.

## Shapes

Raio zero em tudo. Cantos vivos.

A única forma recorrente é a régua: de um pixel para divisória, de nove pixels
de largura para a régua de faixas do eixo.

## Components

### Navigation

O cabeçalho não tem navegação, e não carrega controle: a página é uma só, e ele
é só identidade e frescor da leitura. O campo teal fecha embaixo em todas as
páginas.

O filtro de período vive no conteúdo, imediatamente acima dos gráficos que ele
reescala — e imediatamente acima do aviso de cobertura, que fala do período
escolhido nele. Dentro do campo, a mesma fila lia como barra de navegação de um
site. São links com 44px de altura mínima, o ativo em campo teal sólido, os
demais em `meio` sobre o fundo da página, precedidos de um relógio e da palavra
"Mostrando".

Links, não `<select>`: o campo de formulário submetia na primeira seta do
teclado, então quem navega por teclado andava uma opção por carregamento de
página e perdia o foco em cada uma.

### Subpáginas

A /sistema e a /calibracao usam a mesma faixa de duas colunas da grandeza:
290px de título e resumo à esquerda, conteúdo à direita, régua de um pixel
entre seções. Não é decoração: empilhar tudo numa margem só, sem divisória
entre quatro seções, fazia as subpáginas lerem como outro produto.

O título da página abre em 2,125rem e um lede em 1rem; dentro das seções, o
resumo da esquerda e todo o corpo da direita ficam em 0,875rem. Listas começam
na margem do conteúdo, nunca indentadas além dela.

Campo de formulário é dimensionado pelo que cabe nele: 112px para um LAeq de
quatro caracteres, não a largura do contêiner. Fileira de opções paralelas tem
largura igual — dimensionar cada botão pelo texto deixava 94, 102, 104 e 112px
lado a lado, lendo como desalinho.

Contagem de coleta é medição, não nota de rodapé: o número em 1,25rem com o
rótulo embaixo, não 14px cinza no meio da prosa.

### Gráfico

O componente central. Construído em `grafico.py`, no servidor.

Anatomia, de fora para dentro: régua de faixas colorida no eixo Y; marcas
numéricas da escala à esquerda dela, pulando valores que caem em cima de um
limite; régua de limite normativo atravessando a área, com o valor rotulado
numa calha reservada à direita; eixo do tempo embaixo com cinco marcas, a
última sempre "agora"; envelope de mínimo e máximo por balde; a média por cima
de tudo; e um ponto marcando a leitura atual.

Eixo Y **fixo nas faixas de classificação**, nunca autoescalado nos dados.

Verde e amarelo aparecem sempre; o vermelho só entra quando a série chegou
nele. Aberto por antecipação, ele ocupava metade da altura sem nada acontecer
ali, e enquadrava igual quem só raspou o amarelo e quem entrou fundo no
vermelho. Sem o vermelho, a janela não passa das bordas do amarelo — qualquer
valor fora delas já seria vermelho, então o dado cabe por definição.

Dois renders por grandeza, largo e estreito, trocados por media query: o SVG
encolhe proporcionalmente, e um desenho de 660px chega a 7px de fonte num
celular de 375.

## Do's and Don'ts

**Faça** o estado ser dito em frase, em português, antes de qualquer cor.

**Faça** todo limite exibido carregar a norma que o sustenta. Limite sem norma
vigente diz que não tem.

**Faça** o monitor relatar o que não sabe: leitura perdida, buraco no
histórico, nível não calibrado.

**Não** use cartão. Nem para agrupar, nem para destacar, nem em volta do
gráfico. A régua e o espaço fazem esse trabalho.

**Não** ponha rótulo em caixa alta acima de um número.

**Não** autoescale o eixo Y nos dados. Variação de 0,9 °C vira penhasco e a
estabilidade some.

**Não** preencha a área de plotagem com as faixas. Preenchimento tinge tudo e
mata a leitura da série.

**Não** use creme, bege ou papel envelhecido. É o lugar onde este tipo de
projeto aterrissa por padrão, e a direção escolhida o recusa.

**Não** sugira que isto substitui instrumento com certificado de calibração.
