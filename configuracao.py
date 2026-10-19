# Estação da RBMC analisada
ESTACAO = "IFSC"

# Código SAT utilizado pelo Banco de Dados Geodésicos
CODIGO_BDG = "94052"

# Datas escolhidas com base na atividade geomagnética
# Serão utilizados arquivos do dia inteiro.
DATAS = [
    # Dias com maior atividade geomagnética
    "2026-01-19",
    "2026-04-03",
    "2026-05-14",
    "2026-07-04",
    "2026-08-21",

    # Dias de atividade geomagnética calma
    "2026-03-19",
    "2026-04-16",
    "2026-06-08",
    "2026-07-19",
    "2026-08-28",
]

# Quantidade mínima de dias entre a observação e o processamento
DIAS_MINIMOS_PPP = 20

# Intervalo entre as requisições às APIs do IBGE
INTERVALO_REQUISICOES = 2