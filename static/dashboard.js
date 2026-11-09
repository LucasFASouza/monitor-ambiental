/* Desenho dos gráficos e o pouco de comportamento que depende do tempo passar.
 *
 * O servidor decide a semântica — janela do eixo, faixas, limites, agregação —
 * e manda pronta no JSON. Aqui só se desenha e se cuida da interação, que é
 * justamente o que faltava quando o gráfico era SVG estático: passar o mouse e
 * ler o valor de um ponto é função numa série temporal, não enfeite.
 */

(() => {
  "use strict";

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

  /* O limite normativo atravessa a área e a faixa inteira se rotula uma vez
     na calha à direita. Dentro da área o rótulo colidiria com a série, e dois
     inteiros nus — "25" e "18" — não diziam nem a unidade nem que eram
     limites. Com o eixo Y sem valores, este é o único lugar onde a escala é
     nomeada. */
  const reguasDeLimite = {
    id: "limites",
    afterDatasetsDraw(gr) {
      const reguas = gr.options.plugins.limites?.lista;
      if (!reguas) return;

      const { ctx, chartArea: area, scales } = gr;
      const tinta = cor("--limite");
      const faixa = gr.options.plugins.limites.faixa;

      ctx.save();
      ctx.strokeStyle = tinta;
      ctx.lineWidth = 1;

      for (const r of reguas) {
        const y = scales.y.getPixelForValue(r.valor);
        ctx.beginPath();
        ctx.moveTo(area.left, y);
        ctx.lineTo(area.right, y);
        ctx.stroke();
      }

      if (faixa) {
        const topo = scales.y.getPixelForValue(faixa.ate);
        const base = scales.y.getPixelForValue(faixa.de);
        ctx.font = `13px ${fonte}`;
        ctx.textBaseline = "middle";
        ctx.textAlign = "left";
        ctx.fillStyle = tinta;
        ctx.fillText(faixa.rotulo, area.right + 10, (topo + base) / 2);
      }

      ctx.restore();
    },
  };

  /* A calha precisa caber o rótulo, que muda de largura por grandeza:
     "18–25 °C" e "45–65 dB(A)" não medem o mesmo. */
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

    const medias = d.pontos.map((p) => p.m);
    const minimos = d.pontos.map((p) => p.n);
    const maximos = d.pontos.map((p) => p.x);

    return telas.forEach((tela) => new Chart(tela, {
      type: "line",
      data: {
        labels: d.rotulos,
        datasets: [
          // O envelope são duas séries sem traço, preenchidas uma até a outra.
          { data: maximos, borderWidth: 0, pointRadius: 0, fill: "+1",
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
            right: d.faixa ? larguraDoRotulo(d.faixa.rotulo) + 18 : 18,
            top: 6,
          },
        },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          faixas: { lista: d.faixas },
          limites: { lista: d.reguas, faixa: d.faixa },
          tooltip: {
            backgroundColor: cor("--tinta"),
            padding: 10,
            displayColors: false,
            titleFont: { family: fonte, size: 13, weight: "600" },
            bodyFont: { family: fonte, size: 13 },
            // Só a média abre a dica; mínimo e máximo entram no corpo dela.
            filter: (item) => item.datasetIndex === 2,
            callbacks: {
              label: (item) => {
                const p = d.pontos[item.dataIndex];
                return [
                  `${p.m} ${d.unidade}`,
                  `variou de ${p.n} a ${p.x} no intervalo`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: cor("--regua") },
            ticks: { color: cor("--meio"), font: { family: fonte, size: 13 },
                     maxTicksLimit: 6, maxRotation: 0, autoSkip: true },
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

  for (const [chave, d] of Object.entries(DADOS)) desenhar(chave, d);

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
  const idade = document.getElementById("idade");

  if (idade) {
    let segundos = Number((idade.textContent.match(/\d+/) || [0])[0]);
    const unidade = idade.textContent.trim().split(/\s+/)[1] || "s";
    if (unidade === "min") segundos *= 60;
    else if (unidade === "h") segundos *= 3600;

    // Só a duração: a frase em volta vem do template, que sabe se a coleta
    // está viva ou parada. Escrever a frase inteira aqui duplicava palavra.
    const descrever = (s) =>
      s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`;

    setInterval(() => { idade.textContent = descrever(++segundos); }, 1000);
  }

  setInterval(
    () => window.location.replace(window.location.pathname + window.location.search),
    Math.min(Math.max(intervalo, 15), 60) * 1000,
  );
})();
