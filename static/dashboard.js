/* Dashboard do monitor ambiental.
 *
 * Busca /api/latest e /api/history, preenche os cartões e desenha os dois
 * gráficos. Sem framework e sem build: o arquivo é servido como está.
 */

(() => {
  "use strict";

  const ROTULOS = { bom: "Bom", atencao: "Atenção", ruim: "Ruim" };
  const NIVEIS = ["bom", "atencao", "ruim"];

  // O coletor grava a cada `intervalo` segundos; atualizar bem mais rápido que
  // isso só gastaria rede sem trazer dado novo.
  const intervaloColeta = Number(document.body.dataset.intervalo) || 60;
  const intervaloAtualizacao = Math.min(Math.max(intervaloColeta, 15), 60) * 1000;

  let horasSelecionadas = 24;
  let graficoTemperatura = null;
  let graficoUmidade = null;

  const elemento = (id) => document.getElementById(id);

  const cor = (nome) =>
    getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

  function aplicarNivel(no, nivel) {
    no.classList.remove(...NIVEIS.map((n) => `nivel-${n}`));
    if (nivel) no.classList.add(`nivel-${nivel}`);
  }

  function formatarRotulo(dataHora, horas) {
    const data = new Date(dataHora);
    const opcoes =
      horas > 24
        ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
        : { hour: "2-digit", minute: "2-digit" };

    return data.toLocaleString("pt-BR", opcoes);
  }

  function descreverIdade(segundos) {
    if (segundos < 90) return `há ${segundos} s`;
    if (segundos < 5400) return `há ${Math.round(segundos / 60)} min`;
    return `há ${Math.round(segundos / 3600)} h`;
  }

  function mostrarAviso(mensagem) {
    const aviso = elemento("aviso");
    aviso.textContent = mensagem;
    aviso.hidden = !mensagem;
  }

  // --- Cartões --------------------------------------------------------------

  function preencherCartoes(dados) {
    const indicador = elemento("indicador");

    if (!dados.leitura) {
      indicador.textContent = "Sem dados";
      indicador.className = "indicador parado";
      elemento("atualizacao").textContent = "";
      mostrarAviso(
        "Nenhuma leitura no banco ainda. O coletor já está rodando?"
      );
      return;
    }

    const { leitura, avaliacao, atualizado } = dados;

    // O driver de kernel devolve décimos de grau; a umidade vem inteira.
    elemento("valor-temperatura").textContent =
      leitura.temperatura.toFixed(1);
    elemento("valor-umidade").textContent = leitura.umidade.toFixed(0);
    elemento("valor-geral").textContent = ROTULOS[avaliacao.geral];

    const selos = [
      [elemento("selo-temperatura"), elemento("cartao-temperatura"), avaliacao.temperatura],
      [elemento("selo-umidade"), elemento("cartao-umidade"), avaliacao.umidade],
    ];

    for (const [selo, cartao, nivel] of selos) {
      selo.textContent = ROTULOS[nivel];
      aplicarNivel(selo, nivel);
      aplicarNivel(cartao, nivel);
    }

    aplicarNivel(elemento("valor-geral"), avaliacao.geral);
    aplicarNivel(elemento("cartao-geral"), avaliacao.geral);

    indicador.textContent = atualizado ? "Ao vivo" : "Parado";
    indicador.className = `indicador ${atualizado ? "ativo" : "parado"}`;

    elemento("atualizacao").textContent =
      `Última leitura ${descreverIdade(leitura.idade_segundos)}`;

    mostrarAviso(
      atualizado
        ? ""
        : "A última leitura está velha. O coletor pode ter parado."
    );
  }

  // --- Gráficos -------------------------------------------------------------

  function criarGrafico(canvas, rotulo, corLinha, unidade) {
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: rotulo,
            data: [],
            borderColor: corLinha,
            backgroundColor: "transparent",
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) => `${rotulo}: ${item.parsed.y} ${unidade}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: cor("--grade") },
            ticks: {
              color: cor("--texto-fraco"),
              maxTicksLimit: 8,
              maxRotation: 0,
              autoSkip: true,
            },
          },
          y: {
            grid: { color: cor("--grade") },
            ticks: {
              color: cor("--texto-fraco"),
              callback: (valor) => `${valor} ${unidade}`,
            },
          },
        },
      },
    });
  }

  function atualizarGrafico(grafico, rotulos, valores) {
    grafico.data.labels = rotulos;
    grafico.data.datasets[0].data = valores;
    grafico.update("none");
  }

  // --- Carga ----------------------------------------------------------------

  async function buscarJson(url) {
    const resposta = await fetch(url, { cache: "no-store" });
    if (!resposta.ok) throw new Error(`${url} respondeu ${resposta.status}`);
    return resposta.json();
  }

  async function carregarUltima() {
    preencherCartoes(await buscarJson("/api/latest"));
  }

  async function carregarHistorico() {
    const dados = await buscarJson(`/api/history?horas=${horasSelecionadas}`);
    const rotulos = dados.leituras.map((l) =>
      formatarRotulo(l.data_hora, dados.horas)
    );

    atualizarGrafico(
      graficoTemperatura,
      rotulos,
      dados.leituras.map((l) => l.temperatura)
    );

    atualizarGrafico(
      graficoUmidade,
      rotulos,
      dados.leituras.map((l) => l.umidade)
    );
  }

  async function atualizarTudo() {
    try {
      await Promise.all([carregarUltima(), carregarHistorico()]);
    } catch (erro) {
      const indicador = elemento("indicador");
      indicador.textContent = "Offline";
      indicador.className = "indicador parado";
      mostrarAviso(`Falha ao falar com o servidor: ${erro.message}`);
    }
  }

  // --- Início ---------------------------------------------------------------

  function ligarPeriodos() {
    elemento("periodos").addEventListener("click", (evento) => {
      const botao = evento.target.closest("button[data-horas]");
      if (!botao) return;

      for (const outro of evento.currentTarget.querySelectorAll("button")) {
        outro.classList.toggle("ativo", outro === botao);
      }

      horasSelecionadas = Number(botao.dataset.horas);
      carregarHistorico().catch(() => {});
    });
  }

  function ligarTema() {
    // Os gráficos recebem as cores da folha de estilo na criação, então
    // precisam ser avisados quando o sistema troca de claro para escuro.
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => {
        for (const grafico of [graficoTemperatura, graficoUmidade]) {
          grafico.options.scales.x.grid.color = cor("--grade");
          grafico.options.scales.y.grid.color = cor("--grade");
          grafico.options.scales.x.ticks.color = cor("--texto-fraco");
          grafico.options.scales.y.ticks.color = cor("--texto-fraco");
          grafico.update("none");
        }
      });
  }

  graficoTemperatura = criarGrafico(
    elemento("grafico-temperatura"),
    "Temperatura",
    "#e07a3f",
    "°C"
  );

  graficoUmidade = criarGrafico(
    elemento("grafico-umidade"),
    "Umidade",
    "#3f8fe0",
    "%"
  );

  ligarPeriodos();
  ligarTema();
  atualizarTudo();
  setInterval(atualizarTudo, intervaloAtualizacao);
})();
