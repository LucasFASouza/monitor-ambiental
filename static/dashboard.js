/* O dashboard é montado no servidor. Este arquivo só faz duas coisas que
 * dependem do tempo passar: manter a idade da leitura honesta na tela e
 * recarregar quando houver dado novo para buscar.
 *
 * Sem ele a página continua correta, só não se atualiza sozinha. */

(() => {
  "use strict";

  const corpo = document.body;
  const intervalo = Number(corpo.dataset.intervalo) || 60;
  const idade = document.getElementById("idade");

  // Recarrega um pouco depois do coletor gravar, nunca mais rápido que ele.
  const recarga = Math.min(Math.max(intervalo, 15), 60) * 1000;

  let segundos = idade ? Number((idade.textContent.match(/\d+/) || [0])[0]) : 0;

  function descrever(s) {
    if (s < 90) return `leitura de ${s} s atrás`;
    if (s < 5400) return `leitura de ${Math.round(s / 60)} min atrás`;
    return `leitura de ${Math.round(s / 3600)} h atrás`;
  }

  if (idade) {
    setInterval(() => {
      segundos += 1;
      idade.textContent = descrever(segundos);
    }, 1000);
  }

  setInterval(() => {
    // Preserva o período escolhido ao recarregar.
    window.location.replace(window.location.pathname + window.location.search);
  }, recarga);
})();
