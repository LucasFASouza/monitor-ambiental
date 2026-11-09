"""Desenho do gráfico temporal, em SVG, no servidor.

Sai mais barato que mandar uma biblioteca de gráficos para o navegador: são
poucos clientes na rede local, o Raspberry desenha isso sem esforço, e a página
passa a funcionar sem JavaScript.

As decisões aqui são de legibilidade, e cada uma responde a um erro que o
desenho anterior cometia:

- o eixo Y é fixo nas faixas de classificação, nunca autoescalado nos dados.
  Autoescala transforma 0,9 °C de variação num penhasco e esconde que a sala
  está estável;
- a série é a média de baldes, com o mínimo e o máximo do balde correndo atrás
  como envelope. Amostra crua em 288 pontos vira faixa peluda; média sozinha
  apagaria o pico, que é o que importa em ruído;
- as faixas de classificação aparecem numa régua no próprio eixo, e não
  preenchendo a área de plotagem. Preenchimento tinge tudo e mata a leitura da
  série;
- o limite normativo é régua anotada na calha à direita, em tom de anotação. O
  rótulo dentro da área colide com a série; vermelho ali mente, porque 18 e
  25 °C são os limites do que é bom.
"""

from math import log10


def agregar(valores, alvo):
    """Reduz a série a `alvo` baldes, com média, mínimo e máximo de cada um."""
    if not valores:
        return []

    passo = max(len(valores) // alvo, 1)
    baldes = []

    for inicio in range(0, len(valores), passo):
        balde = valores[inicio:inicio + passo]
        baldes.append((sum(balde) / len(balde), min(balde), max(balde)))

    return baldes


def _passo_de_escala(ymin, ymax):
    """Um passo redondo que renda de três a cinco marcas na escala."""
    bruto = (ymax - ymin) / 4

    if bruto <= 0:
        return 1

    magnitude = 10 ** int(log10(bruto))

    for multiplo in (1, 2, 2.5, 5, 10):
        if magnitude * multiplo >= bruto:
            return magnitude * multiplo

    return magnitude * 10


def desenhar(
    valores,
    ymin,
    ymax,
    reguas,
    rotulos_x,
    faixas,
    *,
    largura=660,
    altura=184,
    calha=74,
    margem_y=34,
    trilho=9,
    base_eixo=26,
    fonte=13,
    pontos=96,
    cor_serie="#17202a",
    cor_envelope="rgba(23,32,42,.17)",
    cor_limite="#8a6a20",
    cor_eixo="#c2c7cc",
    cor_texto="#5f6a74",
):
    """Devolve o SVG do gráfico como string.

    `reguas` é uma lista de (valor, rótulo) com os limites normativos.
    `faixas` é uma lista de (de, até, cor) para a régua do eixo.
    `rotulos_x` é uma lista de (fração de 0 a 1, rótulo).
    """
    if not valores:
        return (
            f'<svg viewBox="0 0 {largura} {altura}" width="100%" height="{altura}" '
            f'role="img" aria-label="sem dados no período">'
            f'<text x="{largura/2:.0f}" y="{altura/2:.0f}" text-anchor="middle" '
            f'font-size="{fonte}" fill="{cor_texto}">sem leituras neste período</text></svg>'
        )

    baldes = agregar(valores, pontos)
    n = len(baldes)
    x0 = margem_y + trilho + 10
    px = largura - calha
    py = altura - base_eixo

    def X(i):
        return x0 if n == 1 else x0 + (px - x0 - 6) * i / (n - 1)

    def Y(v):
        return py - (py - 10) * (v - ymin) / (ymax - ymin)

    partes = [
        f'<svg viewBox="0 0 {largura} {altura}" width="100%" height="{altura}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="inherit" '
        f'style="font-variant-numeric:tabular-nums">'
    ]

    for de, ate, cor in faixas:
        topo, base = Y(min(ate, ymax)), Y(max(de, ymin))
        partes.append(
            f'<rect x="{margem_y}" y="{topo:.1f}" width="{trilho}" '
            f'height="{max(base - topo, 0):.1f}" fill="{cor}"/>'
        )

    # Marcas da escala, pulando as que caem em cima de um limite: número
    # repetido dos dois lados é ruído, não reforço.
    passo = _passo_de_escala(ymin, ymax)
    valores_limite = [v for v, _ in reguas]
    marca = ymin + (passo - ymin % passo) % passo

    while marca <= ymax:
        if all(abs(marca - v) > (ymax - ymin) * 0.04 for v in valores_limite):
            partes.append(
                f'<text x="{margem_y - 6}" y="{Y(marca) + 4:.1f}" font-size="{fonte - 0.5}" '
                f'fill="{cor_texto}" text-anchor="end">{marca:g}</text>'
            )
        marca += passo

    for valor, rotulo in reguas:
        y = Y(valor)
        partes.append(
            f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{y:.1f}" '
            f'stroke="{cor_limite}" stroke-width="1"/>'
        )
        partes.append(
            f'<text x="{px + 8:.1f}" y="{y + 4:.1f}" font-size="{fonte}" '
            f'fill="{cor_limite}">{rotulo}</text>'
        )

    partes.append(
        f'<line x1="{x0:.1f}" y1="{py:.1f}" x2="{px:.1f}" y2="{py:.1f}" '
        f'stroke="{cor_eixo}" stroke-width="1"/>'
    )

    for fracao, rotulo in rotulos_x:
        x = x0 + (px - x0 - 6) * fracao
        ancora = "start" if fracao <= 0.01 else ("end" if fracao >= 0.99 else "middle")
        partes.append(
            f'<line x1="{x:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{py + 4:.1f}" '
            f'stroke="{cor_eixo}" stroke-width="1"/>'
        )
        partes.append(
            f'<text x="{x:.1f}" y="{py + 18:.1f}" font-size="{fonte}" '
            f'fill="{cor_texto}" text-anchor="{ancora}">{rotulo}</text>'
        )

    if n > 1:
        cima = " ".join(f"{X(i):.1f},{Y(mx):.1f}" for i, (_, _, mx) in enumerate(baldes))
        baixo = " ".join(
            f"{X(i):.1f},{Y(mn):.1f}" for i, (_, mn, _) in reversed(list(enumerate(baldes)))
        )
        partes.append(f'<polygon points="{cima} {baixo}" fill="{cor_envelope}"/>')

        linha = " ".join(f"{X(i):.1f},{Y(m):.1f}" for i, (m, _, _) in enumerate(baldes))
        partes.append(
            f'<polyline points="{linha}" fill="none" stroke="{cor_serie}" '
            f'stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    partes.append(
        f'<circle cx="{X(n - 1):.1f}" cy="{Y(baldes[-1][0]):.1f}" r="3.6" fill="{cor_serie}"/>'
    )
    partes.append("</svg>")

    return "".join(partes)
