"""Classificação das leituras em Bom / Atenção / Ruim."""

import config

# Do melhor para o pior. A ordem é usada para calcular a condição geral.
NIVEIS = ("bom", "atencao", "ruim")

ROTULOS = {"bom": "Bom", "atencao": "Atenção", "ruim": "Ruim"}


def classificar(grandeza: str, valor: float) -> str:
    """Devolve "bom", "atencao" ou "ruim" para uma grandeza medida."""
    limites = config.LIMITES[grandeza]

    minimo, maximo = limites["bom"]
    if minimo <= valor <= maximo:
        return "bom"

    minimo, maximo = limites["atencao"]
    if minimo <= valor <= maximo:
        return "atencao"

    return "ruim"


def condicao_geral(*niveis: str) -> str:
    """A condição geral é sempre a pior entre as grandezas avaliadas."""
    return max(niveis, key=NIVEIS.index)


def avaliar(temperatura: float, umidade: float) -> dict:
    nivel_temperatura = classificar("temperatura", temperatura)
    nivel_umidade = classificar("umidade", umidade)

    return {
        "temperatura": nivel_temperatura,
        "umidade": nivel_umidade,
        "geral": condicao_geral(nivel_temperatura, nivel_umidade),
    }
