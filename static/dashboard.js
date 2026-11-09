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

  /* O limite normativo atravessa a área e se rotula numa calha à direita.
     Dentro da área ele colidiria com a série. */
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

      for (const r of reguas) {
        const y = scales.y.getPixelForValue(r.valor);
        ctx.strokeStyle = tinta;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(area.left, y);
        ctx.lineTo(area.right, y);
        ctx.stroke();

        ctx.fillStyle = tinta;
        ctx.fillText(r.rotulo, area.right + 8, y);
      }
      ctx.restore();
    },
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
        layout: { padding: { left: 16, right: 36, top: 6 } },
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
            ticks: {
              color: cor("--meio"),
              font: { family: fonte, size: 12.5 },
              stepSize: d.passo,
              // Sem isto o eixo rotula os próprios limites da janela, e
              // aparece "29,2 dB(A)" com cara de referência. A janela precisa
              // ficar exata: arredondá-la empurraria a faixa vermelha para
              // dentro de um período que nunca chegou nela.
              includeBounds: false,
              // A unidade no eixo: sem ela o número não diz o que mede.
              callback: (v) => `${v} ${d.unidade}`,
            },
          },
        },
      },
    }));
  }

  for (const [chave, d] of Object.entries(DADOS)) desenhar(chave, d);

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
