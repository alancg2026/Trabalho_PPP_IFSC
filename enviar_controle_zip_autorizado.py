"""Submete uma única vez o ZIP de controle já autorizado pelo usuário."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import hatanaka
import requests

from enviar_ppp_controle import extrair_zip_com_seguranca
from preparar_crinex_zip_controle import (
    ARQUIVO_ORIGINAL,
    NOME_INTERNO,
    validar_rinex_normal,
)


URL_PPP = "https://servicodados.ibge.gov.br/api/v1/ppp"
EMAIL = "alanguimaraesc@gmail.com"
NOME_MULTIPART = "IFSC00BRA_R_20260010000_01D_15S_MO.zip"
ARQUIVO_ZIP = (
    Path(__file__).resolve().parent
    / "dados"
    / "rinex_convertidos"
    / NOME_MULTIPART
)
PASTA_RESPOSTAS = (
    Path(__file__).resolve().parent / "dados" / "respostas_ppp"
)
ARQUIVO_REGISTRO = (
    PASTA_RESPOSTAS / "envio_controle_zip_IFSC_2026-001.json"
)
SHA256_ZIP_AUTORIZADO = (
    "5e655f00fc27fc069b976481602ee87c2c69d4283248d2a5505c2fbfed47d554"
)
INTERVALO_REQUISICOES = 2
REGEX_EPOCA = re.compile(
    r"^>\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+"
    r"(\d{1,2})\s+(\d{1,2})\s+(\d+(?:\.\d*)?)"
)


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def caminho_disponivel(nome: str) -> Path:
    caminho = PASTA_RESPOSTAS / nome
    if not caminho.exists():
        return caminho
    indice = 2
    while True:
        candidato = caminho.with_name(
            f"{caminho.stem}_{indice}{caminho.suffix}"
        )
        if not candidato.exists():
            return candidato
        indice += 1


def gravar_registro(registro: dict[str, object]) -> None:
    with ARQUIVO_REGISTRO.open("w", encoding="utf-8") as arquivo:
        json.dump(registro, arquivo, ensure_ascii=False, indent=2)


def validar_zip_autorizado() -> tuple[int, str]:
    if not ARQUIVO_ZIP.is_file():
        raise FileNotFoundError(f"ZIP de controle não encontrado: {ARQUIVO_ZIP}")

    bytes_zip = ARQUIVO_ZIP.read_bytes()
    tamanho = len(bytes_zip)
    hash_atual = hashlib.sha256(bytes_zip).hexdigest()
    if tamanho != 4_298_389 or hash_atual != SHA256_ZIP_AUTORIZADO:
        raise ValueError(
            "O ZIP não corresponde exatamente ao artefato apresentado e "
            "autorizado; nenhuma submissão será feita."
        )

    if not zipfile.is_zipfile(ARQUIVO_ZIP):
        raise ValueError("O arquivo aprovado não é um ZIP válido.")
    with zipfile.ZipFile(ARQUIVO_ZIP) as arquivo_zip:
        if arquivo_zip.testzip() is not None:
            raise ValueError("O CRC do ZIP está inválido.")
        if arquivo_zip.namelist() != [NOME_INTERNO]:
            raise ValueError(
                f"Conteúdo interno inesperado: {arquivo_zip.namelist()}"
            )
        crinex = arquivo_zip.read(NOME_INTERNO)

    bytes_origem = gzip.decompress(ARQUIVO_ORIGINAL.read_bytes())
    if crinex != bytes_origem or crinex.startswith(b"\x1f\x8b"):
        raise ValueError(
            "O CRINEX interno não corresponde ao GZIP original "
            "descompactado uma vez."
        )
    rinex = hatanaka.decompress(crinex, strict=True)
    dados = validar_rinex_normal(rinex)
    if (
        dados["versao"] != "3.05"
        or dados["marcador"] != "IFSC"
        or dados["modelo_antena"] != "TRM159900.00"
        or dados["radome"] != "NONE"
        or dados["altura"] != 0.008
        or dados["intervalo"] != 15.0
        or dados["primeira_epoca"] != "2026-01-01T00:00:00"
        or dados["ultima_epoca"] != "2026-01-01T23:59:45"
        or dados["quantidade_epocas"] != 5760
    ):
        raise ValueError(f"Conteúdo RINEX não corresponde ao controle: {dados}")
    return tamanho, hash_atual


def registrar_resultado(link: str, registro: dict[str, object]) -> None:
    destino = urlparse(link)
    if destino.scheme != "https" or destino.hostname != "www.ibge.gov.br":
        registro.update(
            estado="upload_aceito_resultado_nao_confirmado",
            erro_link="URL de resultado fora do host HTTPS esperado.",
        )
        gravar_registro(registro)
        print("O link não pertence ao domínio esperado; não foi acessado.")
        return

    print("\nLink do resultado — abra manualmente no navegador:")
    print(link)
    time.sleep(INTERVALO_REQUISICOES)

    caminho_bruto = caminho_disponivel(
        f"ppp_IFSC_2026-01-01_resultado_http_{timestamp()}.bin"
    )
    caminho_temporario: Path | None = None
    try:
        resposta = requests.get(link, timeout=(30, 120))
    except requests.exceptions.Timeout as erro:
        registro.update(
            estado="upload_aceito_download_nao_confirmado",
            erro_download=f"Timeout ao consultar o link: {erro}",
        )
        gravar_registro(registro)
        print(f"Upload aceito; timeout consultando o resultado: {erro}")
        return
    except requests.exceptions.RequestException as erro:
        registro.update(
            estado="upload_aceito_download_nao_confirmado",
            erro_download=f"Erro de rede ao consultar o link: {erro}",
        )
        gravar_registro(registro)
        print(f"Upload aceito; consulta automática não confirmada: {erro}")
        return

    # Preserva o corpo recebido antes de inspecionar código ou conteúdo.
    caminho_bruto.write_bytes(resposta.content)
    registro.update(
        status_download_http=resposta.status_code,
        resposta_download=str(caminho_bruto),
        bytes_resposta_download=len(resposta.content),
    )

    if resposta.status_code == 403:
        corpo = resposta.content.lower()
        cloudflare = any(
            marcador in corpo
            for marcador in (
                b"cloudflare",
                b"just a moment",
                b"challenge-platform",
                b"enable javascript and cookies",
            )
        )
        registro["estado"] = (
            "upload_aceito_download_bloqueado_cloudflare"
            if cloudflare
            else "upload_aceito_download_http_403"
        )
        gravar_registro(registro)
        if cloudflare:
            print(
                "A API aceitou o upload, mas a consulta automática do "
                "resultado foi bloqueada pelo desafio Cloudflare (HTTP 403)."
            )
        else:
            print(
                "A API aceitou o upload, mas a consulta automática do "
                "resultado recebeu HTTP 403."
            )
        print(f"Resposta HTTP preservada em: {caminho_bruto}")
        print("Abra o link acima manualmente no navegador.")
        return

    if not 200 <= resposta.status_code < 300:
        registro["estado"] = "upload_aceito_download_http_nao_confirmado"
        gravar_registro(registro)
        print(
            "Upload aceito, mas o download automático do resultado retornou "
            f"HTTP {resposta.status_code}."
        )
        print(f"Resposta preservada em: {caminho_bruto}")
        print("Abra o link acima manualmente no navegador.")
        return

    if not zipfile.is_zipfile(caminho_bruto):
        registro["estado"] = "upload_aceito_download_nao_zip"
        gravar_registro(registro)
        print(
            "A consulta automática não retornou um ZIP válido; "
            "resultado não confirmado."
        )
        print(f"Corpo recebido preservado em: {caminho_bruto}")
        print("Abra o link acima manualmente no navegador.")
        return

    try:
        with zipfile.ZipFile(caminho_bruto) as arquivo_zip:
            corrompido = arquivo_zip.testzip()
            if corrompido is not None:
                raise ValueError(f"CRC inválido: {corrompido}")
        caminho_zip = caminho_disponivel(
            f"ppp_IFSC_2026-01-01_resultado_{timestamp()}.zip"
        )
        caminho_bruto.replace(caminho_zip)
        caminho_bruto = caminho_zip
        pasta_extraida = extrair_zip_com_seguranca(caminho_zip, timestamp())
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as erro:
        registro.update(
            estado="upload_aceito_zip_resultado_invalido",
            erro_validacao_zip=str(erro),
            resposta_download=str(caminho_bruto),
        )
        gravar_registro(registro)
        print(f"ZIP do resultado não pôde ser validado: {erro}")
        print(f"Resposta preservada em: {caminho_bruto}")
        return

    registro.update(
        estado="processamento_confirmado",
        arquivo_resultado=str(caminho_bruto),
        pasta_extraida=str(pasta_extraida),
    )
    gravar_registro(registro)
    print("\nPROCESSAMENTO CONFIRMADO: ZIP válido e íntegro.")
    print(f"Resultado: {caminho_bruto}")
    print(f"Extraído em: {pasta_extraida}")


def main() -> int:
    if ARQUIVO_REGISTRO.exists():
        print(
            "Já existe um registro desta submissão ZIP. "
            "Nenhum novo POST será feito."
        )
        print(f"Registro: {ARQUIVO_REGISTRO}")
        return 2

    try:
        tamanho, hash_zip = validar_zip_autorizado()
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as erro:
        print(f"Pré-validação falhou; nada foi enviado: {erro}")
        return 1

    PASTA_RESPOSTAS.mkdir(parents=True, exist_ok=True)
    instante = datetime.now().astimezone()
    marcador_tempo = instante.strftime("%Y%m%dT%H%M%S%z")
    caminho_resposta = caminho_disponivel(
        f"ppp_IFSC_2026-01-01_zip_resposta_bruta_{marcador_tempo}.txt"
    )
    formulario = {
        "tipo-levantamento": "estatico",
        "modelo-antena": "TRM159900.00    NONE",
        "altura-antena": "0.0080",
        "marco-ibge": "SAT94052",
        "email": EMAIL,
        "autorizacao-uso": "true",
    }
    registro: dict[str, object] = {
        "inicio_local": instante.isoformat(timespec="seconds"),
        "estacao": "IFSC",
        "data": "2026-01-01",
        "dia_do_ano": 1,
        "arquivo_local": str(ARQUIVO_ZIP),
        "tamanho_bytes": tamanho,
        "sha256": hash_zip,
        "membro_zip": NOME_INTERNO,
        "nome_multipart": NOME_MULTIPART,
        "campos_formulario": {
            chave: ("[redigido]" if chave == "email" else valor)
            for chave, valor in formulario.items()
        },
        "arquivo_resposta_bruta": str(caminho_resposta),
        "estado": "submissao_iniciada",
    }

    try:
        with ARQUIVO_REGISTRO.open("x", encoding="utf-8") as arquivo:
            json.dump(registro, arquivo, ensure_ascii=False, indent=2)
    except FileExistsError:
        print("Registro de tentativa já existe; nenhum POST foi feito.")
        return 2

    print("Executando a submissão autorizada única do controle IFSC.")
    print(f"Arquivo: {ARQUIVO_ZIP}")
    print(f"Tamanho: {tamanho:,} bytes")
    print(f"Membro ZIP: {NOME_INTERNO}")
    print(f"Nome multipart: {NOME_MULTIPART}")
    print("Campos: tipo-levantamento=estatico; modelo-antena=TRM159900.00    NONE;")
    print("altura-antena=0.0080; marco-ibge=SAT94052;")
    print(f"email={EMAIL}; autorizacao-uso=true")

    try:
        with ARQUIVO_ZIP.open("rb") as arquivo:
            resposta = requests.post(
                URL_PPP,
                data=formulario,
                files={
                    "arquivo": (
                        NOME_MULTIPART,
                        arquivo,
                        "application/zip",
                    )
                },
                timeout=(30, 600),
            )
    except requests.exceptions.Timeout as erro:
        registro.update(
            estado="submissao_sem_resposta_confirmada",
            erro=f"Timeout durante o POST: {erro}",
        )
        gravar_registro(registro)
        print(f"Timeout durante o POST: {erro}")
        print("Não será feita outra submissão; o resultado é ambíguo.")
        return 1
    except requests.exceptions.ConnectionError as erro:
        registro.update(
            estado="submissao_sem_resposta_confirmada",
            erro=f"Erro de conexão durante o POST: {erro}",
        )
        gravar_registro(registro)
        print(f"Erro de conexão durante o POST: {erro}")
        print("Não será feita outra submissão; o resultado é ambíguo.")
        return 1
    except requests.exceptions.RequestException as erro:
        registro.update(
            estado="submissao_sem_resposta_confirmada",
            erro=f"Erro HTTP/rede durante o POST: {erro}",
        )
        gravar_registro(registro)
        print(f"Erro durante o POST: {erro}")
        print("Não será feita outra submissão.")
        return 1
    except OSError as erro:
        registro.update(
            estado="falha_local_antes_da_resposta",
            erro=f"Erro local ao ler o arquivo: {erro}",
        )
        gravar_registro(registro)
        print(f"Erro local ao ler o arquivo: {erro}")
        return 1

    try:
        caminho_resposta.write_bytes(resposta.content)
    except OSError as erro:
        registro.update(
            estado="resposta_recebida_nao_preservada",
            status_http=resposta.status_code,
            bytes_resposta=len(resposta.content),
            erro_gravacao_resposta=str(erro),
        )
        gravar_registro(registro)
        print(
            "O POST respondeu, mas não foi possível preservar a resposta "
            "bruta. Não será feita outra submissão."
        )
        return 1

    registro.update(
        estado="resposta_recebida",
        status_http=resposta.status_code,
        bytes_resposta=len(resposta.content),
        resposta_bruta=str(caminho_resposta),
    )
    gravar_registro(registro)
    print(f"\nHTTP POST: {resposta.status_code}")
    print(f"Resposta bruta preservada: {caminho_resposta}")

    if not 200 <= resposta.status_code < 300:
        registro["estado"] = "erro_http_post"
        gravar_registro(registro)
        print("A API não aceitou o POST; nenhuma nova tentativa será feita.")
        return 1

    try:
        dados_json = json.loads(resposta.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        registro.update(
            estado="resposta_post_nao_json",
            erro_interpretacao=str(erro),
        )
        gravar_registro(registro)
        print("A resposta foi preservada, mas não é JSON interpretável.")
        return 1

    if not isinstance(dados_json, dict):
        registro["estado"] = "resposta_post_json_nao_objeto"
        gravar_registro(registro)
        print("A resposta JSON não é um objeto; resultado não confirmado.")
        return 1

    caminho_json = caminho_disponivel(
        f"ppp_IFSC_2026-01-01_zip_resposta_{marcador_tempo}.json"
    )
    caminho_json.write_text(
        json.dumps(dados_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    resumo = dados_json.get("resumo")
    resumo_vazio = (
        not isinstance(resumo, dict)
        or not any(
            str(chave).strip() and str(valor).strip()
            for chave, valor in resumo.items()
            if valor is not None
        )
    )
    registro.update(
        resposta_json=str(caminho_json),
        status_api=dados_json.get("status"),
        resumo_vazio=resumo_vazio,
    )

    if dados_json.get("status") != "OK":
        registro["estado"] = "processamento_nao_confirmado"
        gravar_registro(registro)
        print("Upload/processamento não confirmado pela API.")
        return 1

    registro["estado"] = "upload_aceito_resultado_nao_confirmado"
    gravar_registro(registro)
    print("Upload aceito pela API (status: OK).")
    print(f"Resumo vazio: {'sim' if resumo_vazio else 'não'}")
    print(f"Resposta JSON preservada: {caminho_json}")

    link = dados_json.get("link")
    if isinstance(link, str) and link.strip():
        registro["link_resultado"] = link
        gravar_registro(registro)
        registrar_resultado(link, registro)
    else:
        gravar_registro(registro)
        print("A API não forneceu link de resultado; processamento não confirmado.")

    print(f"\nRegistro final: {ARQUIVO_REGISTRO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
