---
version: 1
slug: "templates-index-html"
primary_target: "templates/index.html"
related_targets: ["static/style.css","static/dashboard.js"]
---

Escopo: o dashboard do monitor ambiental, rota `/`, servido por Flask no
Raspberry Pi na rede local. Modo do visitante: Operate.

Público: pessoas que trabalham no ambiente monitorado, sem formação técnica,
respondendo "está adequado agora?". Secundário: quem investiga quando algo
aparece fora da faixa e precisa de histórico e exposição. Tarefa primária é a
leitura de estado; a secundária é a investigação, e as duas vivem na mesma
dobra. Conteúdo real: leituras de DHT11 e INMP441 no SQLite do próprio
aparelho. Restrições: Pi 3B+, sem internet, Chart.js servido localmente,
desktop primário e celular secundário.

## Direction contract

THESIS: o gráfico com as faixas marcadas no eixo é o produto, e o status de
cada grandeza é uma frase que qualquer pessoa lê sem glossário. Recusa o
arranjo padrão da categoria: faixa de cartões de indicador com número grande e
rótulo pequeno, gráficos espremidos embaixo como enfeite.

OWN-WORLD: a Caderneta de Saúde da Criança, da qual vem a cor saturada
institucional e a faixa de percentil impressa — não o papel creme, que é o
default já gasto. Cabeçalho em campo saturado de teal institucional carregando
região inteira, não acento espalhado. Ground branco de impresso. Régua de
faixas verde, amarelo e vermelho como material impresso na escala, não como
semáforo de interface. Pilha do sistema, registro de UI, numerais tabulares.
Sem cartão, sem selo, sem rótulo em caixa alta acima de número.

STORY: a pessoa abre, lê numa frase que o ruído está acima da faixa e as
demais dentro, vê no gráfico quanto variou e quando saiu, e entende que o
número de ruído ainda não é confiável em valor absoluto. Se quiser, troca o
período e tudo se remapeia.

FIRST VIEWPORT: campo de cabeçalho saturado com o nome, o local e a idade da
leitura. Abaixo, a frase de condição geral, em corpo de leitura, nomeando o
que está fora. Depois as três grandezas em coluna única, cada uma com nome,
frase de condição por extenso, valor, referência normativa e, à direita, o
gráfico de 24 h com régua de faixas no eixo, números na escala e limites
anotados na calha. Pé com calibração, perdas de leitura e origem dos limites.
O seletor de período fica no cabeçalho e remapeia todas as leituras da página.

FORM: Caderneta, posição 1 da minha lista ordenada, escolhida pelo usuário
sobre a atribuição do sorteio. SEED REFERENCE: seed:b999c1ad661d0c30

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
