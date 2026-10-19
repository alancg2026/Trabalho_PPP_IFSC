from datetime import datetime, timezone
from pathlib import Path
import time

import requests

from configuracao import ESTACAO, DATAS, DIAS_MINIMOS_PPP

# Pasta principal do projeto
PASTA_PROJETO = Path(__file__).resolve().parent

# Pasta onde os arquivos RINEX serão guardados
PASTA_RINEX = PASTA_PROJETO / "dados" / "rinex"
PASTA_RINEX.mkdir(parents=True, exist_ok=True)


def verificar_data(data_texto):
    """
    Verifica se a data está no formato correto e se possui
    pelo menos 20 dias de antecedência.
    """
    data = datetime.strptime(data_texto, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )

    agora = datetime.now(timezone.utc)
    dias_passados = (agora - data).days

    if data > agora:
        raise ValueError("A data informada está no futuro.")

    if dias_passados < DIAS_MINIMOS_PPP:
        raise ValueError(
            f"A data precisa ter pelo menos "
            f"{DIAS_MINIMOS_PPP} dias de antecedência."
        )

    return data


def baixar_rinex(data_texto):
    """
    Baixa o arquivo RINEX 3 da estação e da data informadas.
    """
    data = verificar_data(data_texto)

    ano = data.year
    dia_do_ano = data.timetuple().tm_yday

    url = (
        "https://servicodados.ibge.gov.br/api/v1/rbmc/dados/"
        f"rinex3/{ESTACAO}/{ano}/{dia_do_ano}"
    )

    print(f"Estação: {ESTACAO}")
    print(f"Data: {data_texto}")
    print(f"Dia do ano: {dia_do_ano}")
    print(f"Consultando: {url}")

    try:
        resposta = requests.get(url, timeout=120)
        resposta.raise_for_status()

        # Tenta obter o nome original enviado pelo IBGE
        content_disposition = resposta.headers.get(
            "Content-Disposition",
            ""
        )

        if "filename=" in content_disposition:
            nome_arquivo = content_disposition.split("filename=")[-1]
            nome_arquivo = nome_arquivo.strip().strip('"')
        else:
            nome_arquivo = (
                f"{ESTACAO}_{ano}_{dia_do_ano:03d}_rinex3.zip"
            )

        caminho_saida = PASTA_RINEX / nome_arquivo

        # Evita baixar novamente um arquivo já existente
        if caminho_saida.exists():
            print(f"\nO arquivo já existe: {caminho_saida}")
            return caminho_saida

       # Cria um nome simples e compatível com Windows
        caminho_saida = PASTA_RINEX / f"IFSC_{ano}_{dia_do_ano:03d}.crx.gz"
       
        caminho_saida.write_bytes(resposta.content)

        tamanho_mb = caminho_saida.stat().st_size / (1024 * 1024)

        print("\nDownload realizado com sucesso!")
        print(f"Arquivo: {caminho_saida}")
        print(f"Tamanho: {tamanho_mb:.2f} MB")

        return caminho_saida

    except requests.exceptions.Timeout:
        print("Erro: o IBGE demorou demais para responder.")

    except requests.exceptions.ConnectionError:
        print("Erro: não foi possível conectar ao IBGE.")

    except requests.exceptions.HTTPError as erro:
        print(f"Erro HTTP: {erro}")
        print("Confira a estação, a data e a disponibilidade do RINEX.")

    except requests.exceptions.RequestException as erro:
        print(f"Erro durante o download: {erro}")

    return None


if __name__ == "__main__":
    # Data indicada pelo professor para validar o programa
    DATA_CONTROLE = "2026-01-01"

    # A data de controle é processada primeiro.
    # dict.fromkeys evita datas repetidas.
    datas_para_baixar = list(
        dict.fromkeys([DATA_CONTROLE] + DATAS)
    )

    print("=" * 60)
    print("DOWNLOAD DOS ARQUIVOS RINEX")
    print(f"Estação: {ESTACAO}")
    print(f"Quantidade de datas: {len(datas_para_baixar)}")
    print("=" * 60)

    arquivos_baixados = []
    erros = []

    for numero, data_texto in enumerate(
        datas_para_baixar,
        start=1
    ):
        print(
            f"\n[{numero}/{len(datas_para_baixar)}] "
            f"Processando {data_texto}"
        )

        arquivo = baixar_rinex(data_texto)

        if arquivo is not None:
            arquivos_baixados.append(arquivo)
        else:
            erros.append(data_texto)

        # Intervalo para não sobrecarregar o servidor do IBGE
        if numero < len(datas_para_baixar):
            print("Aguardando 2 segundos...")
            time.sleep(2)

    print("\n" + "=" * 60)
    print("RESUMO")
    print(f"Arquivos baixados: {len(arquivos_baixados)}")
    print(f"Falhas: {len(erros)}")

    if erros:
        print("Datas que apresentaram erro:")
        for data_texto in erros:
            print(f"- {data_texto}")
    else:
        print("Todos os arquivos foram obtidos com sucesso!")

    print("=" * 60)