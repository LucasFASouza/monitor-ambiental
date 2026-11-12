"""Gera uma cópia estática do painel, para publicar fora da rede local.

O painel completo continua existindo e intocado no aparelho: este script não
altera nada do que roda no Pi. Ele renderiza as páginas pelo cliente de teste
do Flask e trata o HTML para virar um site sem servidor.

    MONITOR_DB=data/monitor.db python scripts/publicar.py --saida publicado/

O que sai daqui é somente leitura por construção, não por permissão: são
arquivos. Não existe rota de calibração para proteger porque não existe rota.

O que o tratamento remove, e por quê:

- a entrada de calibração, que é ação e num arquivo estático não leva a lugar
  nenhum;
- o botão de exportar CSV, pela mesma razão;
- o ciclo de atualização automática, que buscaria /api/painel e levaria 404 a
  cada minuto;
- o link para a página de sistema é mantido, e a página de sistema também é
  publicada, sem as ações dela.

Cada remoção é feita por marcador exato e conferida: se um template mudar de
forma, este script falha em vez de publicar uma página quebrada em silêncio.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacao  # noqa: E402
import config  # noqa: E402

SP = timezone(timedelta(hours=-3))

# Os recortes publicados. O filtro da página passa a navegar entre estes
# arquivos em vez de entre parâmetros de consulta.
PERIODOS = [(24, "24 horas", "index.html"), (168, "7 dias", "7-dias.html")]


class RemocaoFalhou(RuntimeError):
    """Um marcador esperado não foi encontrado no HTML renderizado."""


def _remover(html: str, inicio: str, fim: str, o_que: str) -> str:
    """Corta de `inicio` até `fim`, inclusive. Falha se não achar."""
    i = html.find(inicio)
    if i == -1:
        raise RemocaoFalhou(f"não achei o início de {o_que}: {inicio!r}")

    f = html.find(fim, i)
    if f == -1:
        raise RemocaoFalhou(f"não achei o fim de {o_que}: {fim!r}")

    return html[:i] + html[f + len(fim):]


def _tratar(html: str, quando: datetime) -> str:
    """O tratamento comum a toda página: caminhos, links e carimbo.

    As remoções específicas de cada página ficam fora daqui — a de sistema não
    tem entrada de calibração, e tentar removê-la ali fazia o script falhar.
    """

    # Caminhos absolutos não servem num site publicado em subdiretório.
    html = html.replace('href="/static/', 'href="static/')
    html = html.replace('src="/static/', 'src="static/')

    # O filtro passa a apontar para os arquivos irmãos.
    for horas, _rotulo, arquivo in PERIODOS:
        html = html.replace(f'href="/?horas={horas}"', f'href="{arquivo}"')
    html = html.replace('href="/sistema"', 'href="sistema.html"')
    html = html.replace('href="/"', f'href="{PERIODOS[0][2]}"')

    # Recortes que existem no painel mas não aqui: o filtro não pode oferecer
    # um arquivo que não foi publicado.
    for horas in (1, 6, 720):
        html = re.sub(
            rf'<a\s+href="/\?horas={horas}"[^>]*>.*?</a>', "", html, flags=re.S)

    # E o que sobrar apontando para o servidor sai de cena.
    sobraram = re.findall(r'href="/[^"]*"', html)
    if sobraram:
        raise RemocaoFalhou(f"sobraram links para o servidor: {set(sobraram)}")

    # Diz o que é, e de quando.
    carimbo = (
        '<p class="aviso-espelho">Cópia somente leitura, gerada em '
        f'{quando:%d/%m/%Y às %Hh%M}. O painel ao vivo, a calibração e a '
        "exportação ficam no aparelho, na rede local.</p>"
    )
    html = html.replace("</footer>", f"{carimbo}\n</footer>")

    return html


def _tratar_script(js: str) -> str:
    """Tira o ciclo de atualização: sem servidor, ele só geraria 404."""
    alvo = "  setInterval(atualizar, Math.min(Math.max(intervalo, 15), 60) * 1000);"
    if alvo not in js:
        raise RemocaoFalhou(
            "não achei a chamada de atualização periódica em dashboard.js; "
            "o arquivo mudou de forma e este script precisa ser revisto")

    return js.replace(alvo, "  // A cópia estática não se atualiza sozinha.")


def _estilo_extra() -> str:
    return """

/* --- cópia estática -------------------------------------------------------- */

.aviso-espelho {
  flex-basis: 100%;
  max-width: var(--medida);
  margin-top: var(--e3);
  color: var(--meio);
  font-size: var(--t-apoio);
  line-height: 1.6;
}
"""


def publicar(saida: Path) -> list[Path]:
    quando = datetime.now(tz=SP)
    raiz = Path(__file__).resolve().parent.parent

    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)

    cliente = aplicacao.app.test_client()
    escritos = []

    for horas, _rotulo, arquivo in PERIODOS:
        resposta = cliente.get(f"/?horas={horas}")
        if resposta.status_code != 200:
            raise RemocaoFalhou(f"/?horas={horas} devolveu {resposta.status_code}")

        html = resposta.get_data(as_text=True)
        # Só o painel tem estes dois.
        html = _remover(html, '<p class="afericao">', "</p>",
                        "a entrada de calibração")
        html = _remover(html, '<a class="botao"', "</a>", "o botão de exportar")

        destino = saida / arquivo
        destino.write_text(_tratar(html, quando), encoding="utf-8")
        escritos.append(destino)

    resposta = cliente.get("/sistema")
    if resposta.status_code != 200:
        raise RemocaoFalhou(f"/sistema devolveu {resposta.status_code}")

    html = resposta.get_data(as_text=True)
    html = _remover(html, '<p><a class="botao"', "</p>", "o botão de calibrar")
    html = _remover(html, '<p class="fileira">', "</p>", "os botões de exportar")
    html = _tratar(html, quando)
    (saida / "sistema.html").write_text(html, encoding="utf-8")
    escritos.append(saida / "sistema.html")

    # Estáticos: a folha de estilo com o acréscimo da cópia, o script sem o
    # ciclo de atualização, e o Chart.js como está.
    (saida / "static" / "vendor").mkdir(parents=True)
    (saida / "static" / "style.css").write_text(
        (raiz / "static" / "style.css").read_text(encoding="utf-8") + _estilo_extra(),
        encoding="utf-8")
    (saida / "static" / "dashboard.js").write_text(
        _tratar_script((raiz / "static" / "dashboard.js").read_text(encoding="utf-8")),
        encoding="utf-8")
    shutil.copy2(raiz / "static" / "vendor" / "chart.umd.min.js",
                 saida / "static" / "vendor" / "chart.umd.min.js")

    # O GitHub Pages passa o conteúdo pelo Jekyll por padrão, que ignora
    # diretórios começados em sublinhado e pode engasgar com o que não espera.
    (saida / ".nojekyll").write_text("", encoding="utf-8")

    return escritos


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saida", default="publicado",
                   help="diretório de saída; é apagado e recriado")
    args = p.parse_args()

    saida = Path(args.saida)
    escritos = publicar(saida)

    print(f"Banco lido: {config.DB_PATH}")
    for caminho in escritos:
        print(f"  {caminho}  ({caminho.stat().st_size // 1024} KB)")
    total = sum(f.stat().st_size for f in saida.rglob("*") if f.is_file())
    print(f"Total: {total // 1024} KB em {saida}/")


if __name__ == "__main__":
    main()
