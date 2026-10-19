# Processamento GNSS da Estação IFSC com IBGE-PPP

## Objetivo

Este trabalho processa observações GNSS da estação RBMC IFSC com o serviço
IBGE-PPP, organiza e interpreta os resultados e compara as coordenadas
processadas com as coordenadas oficiais do IBGE. O arquivo de controle de
01/01/2026 foi processado com sucesso. O processamento em lote das demais
datas ainda não foi executado.

## Dados e processamento de controle

- **Estação:** IFSC.
- **Data do levantamento:** 01/01/2026 (dia do ano 001).
- **Origem do RINEX:** arquivo diário da RBMC, baixado da pasta `dados/2026/001`.
  O ZIP-fonte preservado no projeto é `dados/dados brutos/ifsc0011.zip`; contém
  o arquivo de observação Hatanaka `ifsc0011.26d` e arquivos de navegação.
- **Intervalo de rastreio:** 15 segundos.
- **Épocas:** 5.760, de 00:00:00 a 23:59:45.
- **Conversão:** CRINEX/Hatanaka `.26d` foi realmente descompactado e convertido
  para RINEX de observação 2.11 `.26o`, sem apenas trocar a extensão. A saída
  é `dados/rinex_convertidos/ifsc0010.26o`.
- **Entrada enviada ao PPP:** `dados/entrada_ppp/ifsc0010_26o.zip`, contendo
  somente `ifsc0010.26o`.
- **Envio:** submetido manualmente ao IBGE-PPP. O serviço identificou a antena,
  processou corretamente o arquivo e informou o fim do processamento. Os
  resultados baixados foram preservados em
  `dados/resultados_ppp/2026-01-01/`.

Os resultados fornecidos pelo PPP são:

- `ifsc0010.26o.kml`: localização/representação geográfica KML;
- `ifsc0010.26o.pdf`: relatório resumido em PDF;
- `ifsc0010.26o.pos`: série temporal de posições e indicadores por época;
- `ifsc0010.26o.sum`: relatório detalhado dos parâmetros de processamento;
- `ifsc0010.26o.txt`: resumo textual dos campos da solução;
- `ifsc0010.26o_LEIAME.txt`: descrição dos arquivos de saída.

## Resultados da solução estática

Os valores abaixo foram extraídos do resumo textual do IBGE-PPP. O sistema de
referência é SIRGAS2000 na época 2000.4.

| Grandeza | Resultado |
|---|---:|
| Latitude | -27.59443317° |
| Longitude | -48.54208369° |
| Altitude geométrica/elipsoidal | 26.50 m |
| Altitude normal HNOR | 25.78 m |
| UTM Norte | 6945311.595 m |
| UTM Este | 742610.071 m |
| Meridiano central | -51° |
| Sigma 95% da latitude | 0.001 m |
| Sigma 95% da longitude | 0.002 m |
| Sigma 95% da altitude | 0.004 m |
| Antena | TRM159900.00 NONE |
| Altura da antena | 0.008 m |

**HNOR é a altitude normal calculada pelo modelo `hgeoHNOR_IMBITUBA`; não deve
ser chamada automaticamente de altitude ortométrica.** O resultado disponível
não informa HORT (altitude ortométrica), ondulação geoidal nem coordenadas
cartesianas X, Y e Z. Esses valores não são inferidos nem preenchidos pelo
programa.

## Analisador e saídas locais

`analisar_resultado_ppp.py` localiza automaticamente os arquivos `.pos`, `.sum`
e o resumo `.txt` em `dados/resultados_ppp/2026-01-01`. Lê arquivos com
codificações comuns nos resultados do PPP, interpreta números com ponto ou
vírgula decimal, extrai a solução estática do `.txt` e resume as épocas e
indicadores disponíveis no `.pos` e os parâmetros relevantes do `.sum`.
Valores ausentes são mantidos vazios/identificados como não informados; o
programa não calcula XYZ nem confunde HNOR com HORT.

As saídas são:

- `resultados/resultado_ppp_ifsc.csv`: campos extraídos em colunas;
- `resultados/resumo_ppp_ifsc.txt`: relatório legível no terminal/editor.

Para executar novamente, a partir da raiz do projeto:

```powershell
python analisar_resultado_ppp.py
```

O programa usa somente a biblioteca padrão do Python. Para instalar as
dependências externas usadas pelos demais scripts, em um ambiente Python
ativado:

```powershell
python -m pip install -r requirements.txt
```

## Estrutura do projeto

```text
Trabalho_PPP_IFSC/
├── analisar_resultado_ppp.py
├── README.md
├── requirements.txt
├── dados/
│   ├── dados brutos/       # ZIP original diário da RBMC
│   ├── entrada_ppp/       # ZIP RINEX 2.11 usado no envio
│   ├── respostas_ppp/     # respostas e registros das tentativas
│   ├── resultados_ppp/
│   │   └── 2026-01-01/    # KML, PDF, POS, SUM, TXT e LEIAME do PPP
│   ├── rinex/             # observações compactas baixadas para as datas selecionadas
│   └── rinex_convertidos/ # RINEX 2.11 de controle
├── resultados/            # CSV e resumo TXT analisados
└── *.py                   # download, seleção, validação e envio controlado
```

O `.gitignore` exclui ambientes virtuais, caches e itens locais do editor. O
arquivo portátil não contém ambientes virtuais; eles devem ser recriados no
outro computador.

## Etapas ainda a realizar

1. Comparar a solução PPP de controle com as coordenadas oficiais da estação
   IFSC no BDG/IBGE e calcular discrepâncias planimétricas e altimétricas.
2. Gerar/validar tabelas e gráficos da comparação.
3. Revisar a seleção das demais datas e, após validação do controle e dos
   critérios, planejar o processamento. O projeto prevê no máximo 20 datas e
   observações com pelo menos 20 dias de antecedência; não há processamento em
   lote executado neste checkpoint.
4. Documentar os resultados e conclusões finais do trabalho.

Nenhum envio ao IBGE-PPP é iniciado pelo analisador. Não reenvie o controle
como parte da execução normal deste script.
