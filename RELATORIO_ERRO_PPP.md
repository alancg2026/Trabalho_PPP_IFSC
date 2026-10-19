# Relatório de erro — IBGE-PPP

## Tentativa do controle IFSC

- **Estação/data:** IFSC, 01/01/2026 (dia do ano 001), observação de dia inteiro.
- **Arquivo enviado:** `dados/rinex_convertidos/IFSC00BRA_R_20260010000_01D_15S_MO.zip`
- **Conteúdo do ZIP:** `IFSC00BRA_R_20260010000_01D_15S_MO.crx` (Compact RINEX/Hatanaka, sem camada GZIP interna).
- **Tamanho enviado:** 4.298.389 bytes (aproximadamente 4,298 MB).
- **Quantidade de épocas:** 5.760, em intervalo de 15 segundos.

## Resposta do serviço

- **Resposta HTTP do POST:** 200.
- **Status informado pela API:** `OK`.
- **Resumo:** vazio (`{"": ""}`).
- **Link retornado:**  
  https://www.ibge.gov.br/ppp/processados_ppp/alanguimaraesc@gmail.com_IFSC00BRA_R_20260010000_01D_15S_MO.zip_LIB_20261013160501.zip
- **Resultado ao abrir no navegador:** “Not Found”. O endereço não disponibilizou um ZIP de resultado válido, indicando que o resultado não foi efetivamente gerado/disponibilizado pelo servidor.

## Diagnóstico e conclusão

O arquivo de observação local passou pela validação antes do envio: o ZIP e seu CRC foram verificados; o membro interno corresponde ao Compact RINEX obtido ao descompactar o GZIP original; e o Hatanaka foi reconstruído para RINEX 3.05, com 5.760 épocas entre 00:00:00 e 23:59:45 de 01/01/2026. A reconstrução coincide com o RINEX normal convertido localmente.

Assim, considerando a integridade e a conversão local confirmadas, o HTTP 200 com status `OK`, o resumo vazio e o “Not Found” observado no navegador, a causa mais provável está no processamento ou na geração/disponibilização do resultado pelo servidor IBGE-PPP, e não na leitura ou conversão local do arquivo.

O registro da submissão está em `dados/respostas_ppp/envio_controle_zip_IFSC_2026-001.json`; a resposta bruta do POST e as respostas da consulta ao link também foram preservadas em `dados/respostas_ppp`. A consulta automatizada ao link recebeu HTTP 403 com página de desafio Cloudflare; esse bloqueio automático é distinto do “Not Found” relatado ao abrir o endereço no navegador.

Nenhuma nova submissão foi feita e nenhum lote foi iniciado.
