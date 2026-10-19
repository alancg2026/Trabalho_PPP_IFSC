import requests

from consultar_kp import consultar_kp


# Período disponível para o estudo
# Em 06/10/2026, a data mais recente permitida é 16/09/2026.
DATA_INICIAL = "2026-01-01"
DATA_FINAL = "2026-09-16"


try:
    intervalos_kp, resumo_kp = consultar_kp(
        DATA_INICIAL,
        DATA_FINAL,
    )

    # Ordena os dias do maior para o menor Kp
    dias_mais_perturbados = (
        resumo_kp
        .sort_values(
            by=["kp_maximo", "kp_medio"],
            ascending=False,
        )
        .head(15)
    )

    # Seleciona somente dias cujo Kp máximo não ultrapassou 2
    dias_calmos = (
        resumo_kp[resumo_kp["kp_maximo"] <= 2]
        .sort_values(
            by=["kp_maximo", "kp_medio"],
            ascending=True,
        )
        .head(15)
    )

    print("\n15 DIAS COM MAIOR ATIVIDADE GEOMAGNÉTICA")
    print(
        dias_mais_perturbados.to_string(index=False)
    )

    print("\n15 DIAS MAIS CALMOS DO PERÍODO")
    print(
        dias_calmos.to_string(index=False)
    )

    print(
        "\nAs tabelas completas também foram salvas "
        "na pasta dados."
    )

except requests.exceptions.Timeout:
    print("Erro: a API demorou mais de 30 segundos para responder.")

except requests.exceptions.ConnectionError:
    print("Erro: não foi possível conectar à API.")

except requests.exceptions.HTTPError as erro:
    print(f"Erro HTTP retornado pela API: {erro}")

except requests.exceptions.RequestException as erro:
    print(f"Erro durante a consulta: {erro}")

except ValueError as erro:
    print(f"Erro nos dados recebidos: {erro}")