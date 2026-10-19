import json
from pathlib import Path

import requests

from configuracao import CODIGO_BDG, ESTACAO


URL_BDG = (
    "https://servicodados.ibge.gov.br/api/v1/bdg/"
    f"estacoes/{CODIGO_BDG}"
)

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_DADOS = PASTA_PROJETO / "dados"
PASTA_DADOS.mkdir(exist_ok=True)


def converter_numero(valor):
    """Converte números do BDG para float."""

    if valor in (None, ""):
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip().replace(".", "").replace(",", ".")
    return float(texto)


def consultar_coordenada_oficial():
    """Consulta no BDG a coordenada oficial da estação."""

    print(f"Consultando a estação {ESTACAO} no BDG...")
    print(f"Código SAT: {CODIGO_BDG}")
    print(f"Endereço: {URL_BDG}")

    resposta = requests.get(URL_BDG, timeout=30)
    resposta.raise_for_status()

    dados = resposta.json()

    arquivo_saida = PASTA_DADOS / f"bdg_{ESTACAO}.json"

    with arquivo_saida.open("w", encoding="utf-8") as arquivo:
        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=4,
        )

    if isinstance(dados, list):
        if not dados:
            raise ValueError(
                f"O BDG não encontrou a estação {CODIGO_BDG}."
            )

        estacao = dados[0]

    elif isinstance(dados, dict):
        estacao = dados

    else:
        raise ValueError("Formato inesperado retornado pelo BDG.")

    coordenada = {
        "estacao": ESTACAO,
        "codigo_bdg": CODIGO_BDG,
        "latitude": converter_numero(estacao.get("latitude")),
        "longitude": converter_numero(estacao.get("longitude")),
        "altitude_geometrica": converter_numero(
            estacao.get("altitudeGeometrica")
        ),
    }

    print("\nCOORDENADA OFICIAL")
    print(f"Estação: {coordenada['estacao']}")
    print(f"Latitude: {coordenada['latitude']}")
    print(f"Longitude: {coordenada['longitude']}")
    print(
        "Altitude geométrica: "
        f"{coordenada['altitude_geometrica']} m"
    )
    print(f"\nResposta completa salva em: {arquivo_saida}")

    return coordenada


if __name__ == "__main__":
    try:
        consultar_coordenada_oficial()

    except requests.exceptions.Timeout:
        print("Erro: o BDG demorou mais de 30 segundos.")

    except requests.exceptions.ConnectionError:
        print("Erro: não foi possível conectar ao BDG.")

    except requests.exceptions.HTTPError as erro:
        print(f"Erro HTTP retornado pelo BDG: {erro}")

    except requests.exceptions.RequestException as erro:
        print(f"Erro durante a consulta: {erro}")

    except (ValueError, TypeError) as erro:
        print(f"Erro ao interpretar os dados: {erro}")