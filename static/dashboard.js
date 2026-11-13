/* Desenho dos gráficos e o pouco de comportamento que depende do tempo passar.
 *
 * O servidor decide a semântica — janela do eixo, faixas, limites, agregação —
 * e manda pronta no JSON. Aqui só se desenha e se cuida da interação, que é
 * justamente o que faltava quando o gráfico era SVG estático: passar o mouse e
 * ler o valor de um ponto é função numa série temporal, não enfeite.
 */

(() => {
  "use strict";

  /* Mutável de propósito: a página se atualiza sem recarregar, e os callbacks
     da dica do mouse leem daqui. Fechados sobre o objeto da carga, mostrariam
     para sempre os valores da primeira renderização. */
  const DADOS = JSON.parse(document.getElementById("dados").textContent);
  const estilo = getComputedStyle(document.documentElement);
  const cor = (n) => estilo.getPropertyValue(n).trim();
  const fonte = getComputedStyle(document.body).fontFamily;

  /* A régua de faixas vive na calha à esquerda da área de plotagem, não dentro
     dela: preenchimento tinge tudo e mata a leitura da série. */
  const reguaDeFaixas = {
    id: "faixas",
    beforeDatasetsDraw(gr) {
      const faixas = gr.options.plugins.faixas?.lista;
      if (!faixas) return;

      // A regua mora na folga da esquerda, antes do espaco que o Chart.js
      // reserva para os rotulos do eixo. Desenha-la perto de chartArea.left
      // cobria esses rotulos e cortava a unidade.
      const { ctx, scales } = gr;
      const largura = 9;
      const x = 0;

      ctx.save();
      for (const f of faixas) {
        const topo = scales.y.getPixelForValue(f.ate);
        const base = scales.y.getPixelForValue(f.de);
        ctx.fillStyle = f.cor;
        ctx.fillRect(x, topo, largura, Math.max(base - topo, 0));
      }
      ctx.restore();
    },
  };

  /* Cada limite normativo atravessa a área e se rotula na calha à direita,
     com a unidade. Dentro da área o rótulo colidiria com a série; sem a
     unidade sobravam dois inteiros nus. Com o eixo Y sem valores, esta calha é
     o único lugar onde a escala é nomeada. */
  const reguasDeLimite = {
    id: "limites",
    afterDatasetsDraw(gr) {
      const reguas = gr.options.plugins.limites?.lista;
      if (!reguas) return;

      const { ctx, chartArea: area, scales } = gr;
      const tinta = cor("--limite");

      ctx.save();
      ctx.font = `13px ${fonte}`;
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      ctx.strokeStyle = tinta;
      ctx.lineWidth = 1;

      for (const r of reguas) {
        const y = scales.y.getPixelForValue(r.valor);
        ctx.beginPath();
        ctx.moveTo(area.left, y);
        ctx.lineTo(area.right, y);
        ctx.stroke();
      }

      /* A linha sempre aparece; o rótulo pode ser pulado. Dois rótulos a menos
         de 16px um do outro se sobrepõem, e na temperatura as bordas do
         recomendado e do vermelho ficam a 2 °C — cerca de 22px. Desenha por
         prioridade, para que o limite do recomendado nunca perca o rótulo
         para o do vermelho. */
      ctx.fillStyle = tinta;
      const postos = [];
      const porPrioridade = [...reguas].sort((a, b) => a.prioridade - b.prioridade);

      for (const r of porPrioridade) {
        const y = scales.y.getPixelForValue(r.valor);
        if (postos.some((outro) => Math.abs(outro - y) < 16)) continue;
        ctx.fillText(r.rotulo, area.right + 10, y);
        postos.push(y);
      }

      ctx.restore();
    },
  };

  /* A calha precisa caber o rótulo mais largo, que muda por grandeza:
     "25 °C" e "65 dB(A)" não medem o mesmo. */
  /* O eixo X é tempo, não posição. Formatar aqui e não por biblioteca de data
     evita vendorizar um adaptador só para escrever "18h27". */
  const doisDigitos = (n) => String(n).padStart(2, "0");

  // Vírgula decimal, como no resto da página.
  const numero = (n) => String(n).replace(".", ",");

  const instante = (ms, comData) => {
    const q = new Date(ms);
    return comData
      ? `${doisDigitos(q.getDate())}/${doisDigitos(q.getMonth() + 1)} ${doisDigitos(q.getHours())}h`
      : `${doisDigitos(q.getHours())}h${doisDigitos(q.getMinutes())}`;
  };

  const regua = document.createElement("canvas").getContext("2d");
  const larguraDoRotulo = (texto) => {
    regua.font = `13px ${fonte}`;
    return Math.ceil(regua.measureText(texto).width);
  };

  function desenhar(chave, d) {
    // Uma sessao de variantes duplica o bloco inteiro, entao ha mais de um
    // canvas por grandeza na pagina. Desenha em todos.
    const telas = document.querySelectorAll(`canvas[data-grafico="${chave}"]`);
    if (!telas.length) return;

    const serie = (campo) => d.pontos.map((p) => ({ x: p.t, y: p[campo] }));
    const medias = serie("m");
    const minimos = serie("n");
    const maximos = serie("x");

    return [...telas].map((tela) => new Chart(tela, {
      type: "line",
      data: {
        datasets: [
          // O envelope: duas séries preenchidas uma até a outra. A de cima
          // ganha traço fino porque é onde moram os picos, e pico de ruído
          // dura minutos — num recorte de sete dias isso é um balde só, uma
          // lasca de preenchimento claro que some contra o fundo. Com o
          // contorno, a mesma lasca vira uma agulha que se vê.
          { data: maximos, borderColor: "rgba(23,32,42,.3)", borderWidth: 1,
            pointRadius: 0, fill: "+1",
            backgroundColor: "rgba(23,32,42,.15)", tension: 0.25 },
          { data: minimos, borderWidth: 0, pointRadius: 0, fill: false, tension: 0.25 },
          { data: medias, borderColor: cor("--tinta"), borderWidth: 1.9,
            pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: cor("--tinta"),
            fill: false, tension: 0.25 },
        ],
      },
      plugins: [reguaDeFaixas, reguasDeLimite],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        layout: {
          padding: {
            // 14px deixam a régua de faixas (9px em x=0) encostada na área de
            // plotagem. Antes eram 16px mais a coluna de rótulos do eixo, e a
            // régua ficava a 50px da curva que deveria qualificar.
            left: 14,
            right: Math.max(18, ...d.reguas.map((r) => larguraDoRotulo(r.rotulo) + 18)),
            top: 6,
          },
        },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          faixas: { lista: d.faixas },
          limites: { lista: d.reguas },
          tooltip: {
            backgroundColor: cor("--tinta"),
            padding: 10,
            displayColors: false,
            titleFont: { family: fonte, size: 13, weight: "600" },
            bodyFont: { family: fonte, size: 13 },
            // Só a média abre a dica; mínimo e máximo entram no corpo dela.
            filter: (item) => item.datasetIndex === 2,
            callbacks: {
              title: (itens) => instante(itens[0].parsed.x, DADOS[chave].dias),
              label: (item) => {
                const atual = DADOS[chave];
                const p = atual.pontos[item.dataIndex];
                if (!p) return "";
                const linhas = [`${numero(p.m)} ${atual.unidade}`];
                // Balde de uma leitura só não variou: "de 19,5 a 19,5" é ruído.
                if (p.n !== p.x) {
                  linhas.push(`variou de ${numero(p.n)} a ${numero(p.x)} no intervalo`);
                }
                return linhas;
              },
            },
          },
        },
        scales: {
          /* Linear sobre o instante, não categórico sobre o índice. Com índice,
             uma janela de 24 h com 12 h de dados desenhava os pontos espalhados
             pelas 24 h e rotulava o primeiro como se fosse de 12 h antes do que
             era. Os limites são a janela pedida: faltando dados, o vazio
             aparece em vez de a série ser esticada para preencher. */
          x: {
            type: "linear",
            min: d.desde,
            max: d.ate,
            grid: { display: false },
            border: { color: cor("--regua") },
            ticks: {
              color: cor("--meio"),
              font: { family: fonte, size: 13 },
              maxTicksLimit: 6,
              maxRotation: 0,
              autoSkip: true,
              callback: (v) => instante(v, d.dias),
            },
          },
          y: {
            min: d.ymin,
            max: d.ymax,
            grid: { display: false },
            border: { display: false },
            // O eixo não imprime valor nenhum. A escala é dada pela régua de
            // faixas e pelo rótulo do intervalo de referência; a coluna de
            // números repetia a unidade a cada marca e empurrava a régua para
            // longe da curva. Também encerra o problema dos limites da janela
            // aparecerem como "29,2 dB(A)", com cara de referência.
            ticks: { display: false },
          },
        },
      },
    }));
  }

  const graficos = {};
  for (const [chave, d] of Object.entries(DADOS)) {
    graficos[chave] = desenhar(chave, d) || [];
  }

  /* As divulgações fecham com Esc e clicando fora: é o que separa um painel
     flutuante de uma sanfona. Sem este bloco o <details> continua abrindo e
     fechando no próprio clique, então nada depende daqui. */
  const divulgacoes = () => document.querySelectorAll("details.saiba[open]");

  document.addEventListener("click", (e) => {
    for (const d of divulgacoes()) if (!d.contains(e.target)) d.open = false;
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of divulgacoes()) {
      d.open = false;
      d.querySelector("summary")?.focus();
    }
  });

  // --- o que depende do tempo passar ---------------------------------------

  const intervalo = Number(document.body.dataset.intervalo) || 60;

  /* A duração conta no cliente, de segundo em segundo, e é corrigida a cada
     atualização com a idade que o servidor informa. */
  let segundos = 0;

  const descrever = (s) =>
    s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`;

  const escreverDuracao = () => {
    for (const el of document.querySelectorAll(".idade")) el.textContent = descrever(segundos);
  };

  const lerDuracaoInicial = () => {
    const el = document.querySelector(".idade");
    if (!el) return;
    const n = Number((el.textContent.match(/\d+/) || [0])[0]);
    const unidade = el.textContent.trim().split(/\s+/)[1] || "s";
    segundos = unidade === "min" ? n * 60 : unidade === "h" ? n * 3600 : n;
  };

  lerDuracaoInicial();
  setInterval(() => { segundos += 1; escreverDuracao(); }, 1000);

  /* Atualiza os dados, não o documento.

     `location.replace` a cada minuto descartava o scroll — a navegação não é
     do tipo "reload", então o navegador não o restaura —, reanunciava a página
     inteira para leitor de tela e fechava qualquer painel de informação
     aberto. Ler o rodapé era impossível e a leitura por voz recomeçava do topo
     uma vez por minuto, indefinidamente. */
  async function atualizar() {
    let v;
    try {
      const resposta = await fetch(`/api/painel${window.location.search}`, {
        headers: { Accept: "application/json" },
      });
      if (!resposta.ok) return;
      v = await resposta.json();
    } catch {
      return; // rede caiu: mantém o que está na tela, que é honesto
    }

    const resumo = document.querySelector(".resumo");
    if (resumo) {
      resumo.textContent = v.resumo || "";
      resumo.className = `resumo n-${v.geral || "sem"}`;
      resumo.hidden = !v.resumo;
    }

    const frescor = document.querySelector(".frescor");
    if (frescor) frescor.classList.toggle("parado", !v.atualizado);
    if (v.idade_segundos !== null && v.idade_segundos !== undefined) {
      segundos = v.idade_segundos;
      escreverDuracao();
    }

    for (const b of v.blocos) {
      const leitura = document.querySelector(`.leitura[data-bloco="${b.chave}"]`);
      if (!leitura) continue;

      leitura.querySelector(".marca")?.setAttribute("class", `marca ${b.marca_classe}`);

      const estado = leitura.querySelector(".estado");
      if (estado) {
        estado.textContent = b.estado_texto;
        estado.className = `estado ${b.estado_classe}`;
      }

      const valor = leitura.querySelector(".valor");
      if (valor) {
        valor.querySelector(".numero").textContent = b.valor ?? "";
        valor.className = `valor ${b.valor_classe}`;
        valor.hidden = b.valor === null;
      }

      const descricao = document.getElementById(`serie-${b.chave}`);
      if (descricao) descricao.textContent = b.resumo_serie;
    }

    for (const [chave, d] of Object.entries(v.graficos)) {
      DADOS[chave] = d;

      for (const gr of graficos[chave] || []) {
        const par = (campo) => d.pontos.map((p) => ({ x: p.t, y: p[campo] }));
        gr.data.datasets[0].data = par("x");
        gr.data.datasets[1].data = par("n");
        gr.data.datasets[2].data = par("m");
        gr.options.scales.x.min = d.desde;
        gr.options.scales.x.max = d.ate;
        gr.options.scales.y.min = d.ymin;
        gr.options.scales.y.max = d.ymax;
        gr.options.scales.y.ticks.stepSize = d.passo;
        gr.options.plugins.faixas.lista = d.faixas;
        gr.options.plugins.limites.lista = d.reguas;
        // A calha acompanha o rótulo mais largo: quando a faixa vermelha entra,
        // aparecem limites novos e eles podem medir mais.
        gr.options.layout.padding.right = Math.max(
          18,
          ...d.reguas.map((r) => larguraDoRotulo(r.rotulo) + 18),
        );
        gr.update("none");
      }
    }
  }

  setInterval(atualizar, Math.min(Math.max(intervalo, 15), 60) * 1000);
})();
