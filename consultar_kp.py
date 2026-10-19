import json
from pathlib import Path

import pandas as pd
import requests


URL_KP = "https://kp.gfz.de/app/json/"


def classificar_kp(valor_kp):
    """Classifica a atividade geomagnética pelo índice Kp."""

    if valor_kp < 3:
        return "Calmo"
    elif valor_kp < 5:
        return "Ativo"
    else:
        return "Tempestade geomagnética"


def consultar_kp(data_inicial, data_final):
    """
    Consulta o índice Kp na API do GFZ, guarda a resposta original
    e produz uma tabela com o maior valor de cada dia.
    """

    parametros = {
        "start": f"{data_inicial}T00:00:00Z",
        "end": f"{data_final}T23:59:59Z",
        "index": "Kp",
    }

    pasta_dados = Path("dados")
    pasta_dados.mkdir(exist_ok=True)

    print("Consultando o índice Kp no GFZ...")

    resposta = requests.get(
        URL_KP,
        params=parametros,
        timeout=30,
    )

    resposta.raise_for_status()
    dados_kp = resposta.json()

    # Guarda a resposta original da API
    arquivo_json = (
        pasta_dados
        / f"kp_{data_inicial}_a_{data_final}.json"
    )

    with arquivo_json.open("w", encoding="utf-8") as arquivo:
        json.dump(
            dados_kp,
            arquivo,
            ensure_ascii=False,
            indent=4,
        )

    # Identifica o campo de data e horário recebido
    campo_tempo = None

    for nome in ["datetime", "time", "timestamp"]:
        if nome in dados_kp:
            campo_tempo = nome
            break

    if campo_tempo is None:
        raise ValueError(
            "A API não retornou um campo reconhecido de data e horário."
        )

    if "Kp" not in dados_kp:
        raise ValueError(
            "A API não retornou os valores do índice Kp."
        )

    # Transforma os dados em tabela
    tabela = pd.DataFrame({
        "data_hora_utc": pd.to_datetime(
            dados_kp[campo_tempo],
            utc=True,
        ),
        "kp": pd.to_numeric(
            dados_kp["Kp"],
            errors="coerce",
        ),
    })

    # Remove registros sem valor numérico
    tabela = tabela.dropna(subset=["kp"])

    tabela["data_utc"] = tabela["data_hora_utc"].dt.date

    tabela["classificacao_intervalo"] = tabela["kp"].apply(
        classificar_kp
    )

    # Resume os oito intervalos de três horas de cada dia
    resumo_diario = (
        tabela.groupby("data_utc", as_index=False)
        .agg(
            kp_maximo=("kp", "max"),
            kp_medio=("kp", "mean"),
        )
    )

    resumo_diario["classificacao_dia"] = (
        resumo_diario["kp_maximo"].apply(classificar_kp)
    )

    # Arredonda somente para melhorar a apresentação
    resumo_diario["kp_maximo"] = (
        resumo_diario["kp_maximo"].round(3)
    )

    resumo_diario["kp_medio"] = (
        resumo_diario["kp_medio"].round(3)
    )

    # Salva as duas tabelas
    arquivo_intervalos = pasta_dados / "kp_intervalos.csv"
    arquivo_resumo = pasta_dados / "kp_resumo_diario.csv"

    tabela.to_csv(
        arquivo_intervalos,
        index=False,
        encoding="utf-8-sig",
    )

    resumo_diario.to_csv(
        arquivo_resumo,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Resposta original: {arquivo_json}")
    print(f"Tabela por intervalo: {arquivo_intervalos}")
    print(f"Resumo diário: {arquivo_resumo}")

    return tabela, resumo_diario