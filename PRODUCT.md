# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primários: pessoas que trabalham no ambiente monitorado — funcionários de um
escritório — consultando para saber se as condições estão adequadas. Não são
especialistas: não conhecem LAeq, IBUTG nem a numeração das normas.

Secundário: quem investiga quando o ambiente aparece desenquadrado, precisando
de histórico, exposição acumulada e identificação de padrões. Pode ser a mesma
pessoa em outro momento.

## Product Purpose

Dizer, para quem está no ambiente, se as condições de temperatura, umidade e
ruído estão adequadas agora; e guardar histórico suficiente para que alguém
investigue quando não estiverem.

Sucesso é alguém abrir, entender a situação em segundos sem explicação prévia,
e — quando algo está fora — conseguir responder há quanto tempo e com que
frequência.

## Positioning

Compara a medição com limites de norma brasileira vigente e mostra de onde cada
limite vem. Um termômetro diz o número; este monitor diz se o número está
dentro do recomendado e por quê.

## Operating Context

Raspberry Pi 3B+ instalado no próprio ambiente, servindo na rede local. Acesso
pelo navegador, sem instalação e sem conta. Consulta primária no computador,
com modo secundário adaptado para celular.

Coleta contínua e autônoma: dois processos independentes gravam em SQLite, o
dashboard apenas lê. A placa pode reiniciar; a coleta volta sozinha.

## Capabilities and Constraints

Mede temperatura e umidade (DHT11, por driver de kernel do Linux) e nível de
ruído em LAeq ponderado em A (INMP441 por I2S). Histórico em SQLite no próprio
aparelho, com APIs de leitura e página servida por Flask.

Limitações que o produto precisa comunicar, não esconder:

- o DHT11 tem resolução de 1 °C e precisão de ±5% na umidade, e falha em parte
  das leituras por característica do próprio sensor;
- o nível de ruído ainda não foi calibrado contra medidor de referência, então
  o valor absoluto é indicativo e só a variação é confiável;
- não é instrumento de higiene ocupacional: avaliação de insalubridade exige
  medidor com certificado de calibração, e este aparelho não substitui isso;
- não mede calor radiante, então não serve para IBUTG.

Funciona sem internet. O Chart.js é servido pelo próprio aparelho.

## Brand Commitments

Nenhuma identidade visual estabelecida. Interface e conteúdo em português do
Brasil.

## Evidence on Hand

Dados reais de sensor desde setembro de 2026, no banco em `data/monitor.db`.
Não há base de usuários, depoimento, benchmark ou implantação em cliente —
trabalho futuro não deve inventar nenhum.

Os limites de classificação têm fonte documentada em `config.py`: NR-17 item
17.8.4.2 para temperatura, NR-17 item 17.8.4.1.2 e NBR 10152:2017 para ruído.
A faixa de umidade é convergência de fontes, sem norma vigente verificada.

## Product Principles

1. A pergunta "está adequado agora?" vem antes de tudo e precisa ser
   respondida sem vocabulário técnico. A precisão serve essa resposta; nunca
   a substitui.
2. Todo limite exibido carrega sua fonte. Limite sem norma vigente diz que não
   tem.
3. O monitor relata o que não sabe. Leitura perdida, buraco no histórico e
   nível não calibrado aparecem — num contexto ocupacional, um número errado
   com aparência de certo é pior que uma lacuna admitida.
4. Exposição no tempo é a unidade de análise, não o instante. O instante
   atende a olhada; a duração atende a investigação.
5. Nunca sugerir que isto substitui instrumento com certificado de calibração.

## Accessibility & Inclusion

Público não especialista lendo em contexto de trabalho: o significado não pode
depender só de cor, e o texto precisa ser legível sem ampliar a página.
Referência WCAG 2.1 AA, medida no render em 2026-11-09: os oito pares de texto
da página passam, com mínimo de 4,75:1 (rótulo e abas inativas do filtro sobre
o campo teal). O anel de foco é 5,73:1 sobre o campo. O significado nunca
depende só de cor — a condição de cada grandeza é dita por extenso em frase.

Essa conformidade é verificada, não presumida: uma versão anterior deste
arquivo afirmava mínimo de 4,65:1 enquanto três pares falhavam de fato
(4,41:1 no título da capa, 3,78:1 no rótulo do filtro, 2,84:1 na linha das
normas) e o anel de foco era 1,00:1, invisível. Toda mudança de paleta precisa
ser remedida no render, não deduzida dos tokens.
