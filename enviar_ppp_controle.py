"""Envio manual e único do arquivo de controle IFSC ao IBGE-PPP."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

import requests

from diagnosticar_rinex_controle import inspecionar


URL_PPP = "https://servicodados.ibge.gov.br/api/v1/ppp"
NOME_MULTIPART = "IFSC00BRA_R_20260010000_01D_15S_MO.crx.gz"
TAMANHO_MAXIMO_BYTES = 20_000_000
INTERVALO_REQUISICOES = 2

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_CONTROLE = (
    PASTA_PROJETO / "dados" / "rinex" / "IFSC_2026_001.crx.gz"
)
PASTA_RESPOSTAS = PASTA_PROJETO / "dados" / "respostas_ppp"
PASTA_RESULTADOS = PASTA_PROJETO / "dados" / "resultados_ppp"
ARQUIVO_REGISTRO = (
    PASTA_RESPOSTAS / "envio_controle_IFSC_2026-001.json"
)


def horario_local() -> datetime:
    return datetime.now().astimezone()


def timestamp_arquivo(instante: datetime) -> str:
    return instante.strftime("%Y%m%dT%H%M%S%z")


def nome_disponivel(pasta: Path, nome: str) -> Path:
    base = pasta / nome
    if not base.exists():
        return base
    indice = 2
    while True:
        candidato = pasta / f"{base.stem}_{indice}{base.suffix}"
        if not candidato.exists():
            return candidato
        indice += 1


def dados_formulario(email: str) -> dict[str, str]:
    return {
        "tipo-levantamento": "estatico",
        "modelo-antena": "TRM159900.00",
        "altura-antena": "0.0080",
        "marco-ibge": "SAT94052",
        "email": email,
        "autorizacao-uso": "true",
    }


def validar_arquivo_controle() -> dict[str, object]:
    if not ARQUIVO_CONTROLE.is_file():
        raise FileNotFoundError(f"Arquivo de controle ausente: {ARQUIVO_CONTROLE}")

    tamanho = ARQUIVO_CONTROLE.stat().st_size
    if tamanho <= 0 or tamanho > TAMANHO_MAXIMO_BYTES:
        raise ValueError(
            "O arquivo precisa ter tamanho entre 1 byte e 20.000.000 bytes; "
            f"tamanho observado: {tamanho} bytes. Não será cortado nem "
            "reenviado com extensão diferente."
        )

    dados = inspecionar(ARQUIVO_CONTROLE)
    verificacoes = {
        "formato Compact RINEX/Hatanaka em GZIP": str(dados["formato"])
        == "Compact RINEX/Hatanaka dentro de GZIP",
        "marcador IFSC": dados["marcador"] == "IFSC",
        "modelo de antena TRM159900.00": dados["modelo_antena"]
        == "TRM159900.00",
        "radome NONE": dados["radome"] == "NONE",
        "altura 0.0080 m": abs(float(dados["altura"]) - 0.0080) < 1e-9,
        "intervalo 15 s": abs(float(dados["intervalo"]) - 15.0) < 1e-9,
        "primeira época de controle": dados["primeira_epoca"]
        == "2026-01-01T00:00:00.000000",
        "última época de controle": dados["ultima_epoca"]
        == "2026-01-01T23:59:45.000000",
        "5.760 épocas": dados["quantidade_epocas"] == 5760,
        "todas as épocas com 15 s": all(
            abs(float(intervalo) - 15.0) < 1e-9
            for intervalo in dados["espacamentos"]
        ),
    }
    falhas = [nome for nome, valido in verificacoes.items() if not valido]
    if falhas:
        raise ValueError(
            "O arquivo não atende ao controle esperado: " + ", ".join(falhas)
        )
    return dados


def imprimir_previa(
    dados: dict[str, object],
    formulario: dict[str, str],
) -> None:
    tamanho_bytes = int(dados["bytes"])
    print("\nPRÉVIA — NENHUM ENVIO FOI FEITO AINDA")
    print(f"Arquivo local: {dados['caminho']}")
    print(f"Formato detectado: {dados['formato']}")
    print(
        f"Tamanho: {tamanho_bytes:,} bytes "
        f"({tamanho_bytes / 1_000_000:.3f} MB; "
        f"{tamanho_bytes / (1024 * 1024):.3f} MiB)"
    )
    print(f"Nome multipart: {NOME_MULTIPART}")
    print("Campos do formulário:")
    for chave, valor in formulario.items():
        print(f"  {chave}: {valor}")
    print(
        "Controle: IFSC; 01/01/2026, DOY 001; 00:00:00–23:59:45; "
        "intervalo 15 s; antena TRM159900.00 / radome NONE; "
        "altura 0.0080 m; marco SAT94052."
    )


def gravar_registro(registro: dict[str, object]) -> None:
    ARQUIVO_REGISTRO.write_text(
        json.dumps(registro, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resumo_vazio(resumo: object) -> bool:
    if not isinstance(resumo, dict):
        return resumo in (None, "", [], {})

    def tem_conteudo(valor: object) -> bool:
        if valor is None:
            return False
        if isinstance(valor, str):
            return bool(valor.strip())
        if isinstance(valor, dict):
            return any(tem_conteudo(item) for item in valor.values())
        if isinstance(valor, (list, tuple)):
            return any(tem_conteudo(item) for item in valor)
        return valor is not False

    return not any(
        str(chave).strip() and tem_conteudo(valor)
        for chave, valor in resumo.items()
    )


def atualizar_registro(
    registro: dict[str, object],
    estado: str,
    **campos: object,
) -> None:
    registro["estado"] = estado
    registro.update(campos)
    gravar_registro(registro)


def extrair_zip_com_seguranca(
    caminho_zip: Path,
    timestamp: str,
) -> Path:
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino_final = nome_disponivel(
        PASTA_RESULTADOS,
        f"IFSC_2026-01-01_{timestamp}",
    )
    diretorio_temporario = Path(
        tempfile.mkdtemp(prefix=".ppp_controle_", dir=PASTA_RESULTADOS)
    )

    try:
        with zipfile.ZipFile(caminho_zip) as arquivo_zip:
            membros = [
                info for info in arquivo_zip.infolist() if not info.is_dir()
            ]
            if not membros:
                raise ValueError("O ZIP não contém arquivos de resultado.")
            arquivo_corrompido = arquivo_zip.testzip()
            if arquivo_corrompido is not None:
                raise ValueError(
                    f"CRC inválido no arquivo ZIP: {arquivo_corrompido}"
                )

            caminhos: list[tuple[zipfile.ZipInfo, Path]] = []
            raiz = diretorio_temporario.resolve()
            for info in arquivo_zip.infolist():
                nome = info.filename.replace("\\", "/")
                relativo = PurePosixPath(nome)
                caminho_windows = PureWindowsPath(info.filename)
                if (
                    relativo.is_absolute()
                    or caminho_windows.is_absolute()
                    or caminho_windows.drive
                    or any(parte in ("", "..") for parte in relativo.parts)
                ):
                    raise ValueError(
                        f"Caminho inseguro dentro do ZIP: {info.filename}"
                    )
                modo = info.external_attr >> 16
                if modo & 0o170000 == 0o120000:
                    raise ValueError(
                        f"Link simbólico inesperado dentro do ZIP: {info.filename}"
                    )
                destino = diretorio_temporario.joinpath(*relativo.parts)
                if not destino.resolve().is_relative_to(raiz):
                    raise ValueError(
                        f"Caminho fora da pasta de extração: {info.filename}"
                    )
                caminhos.append((info, destino))

            for info, destino in caminhos:
                if info.is_dir():
                    destino.mkdir(parents=True, exist_ok=True)
                    continue
                destino.parent.mkdir(parents=True, exist_ok=True)
                with arquivo_zip.open(info) as origem, destino.open("xb") as saida:
                    shutil.copyfileobj(origem, saida)

        diretorio_temporario.rename(destino_final)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
        shutil.rmtree(diretorio_temporario, ignore_errors=True)
        raise

    return destino_final


def baixar_resultado(
    link: str,
    timestamp: str,
    registro: dict[str, object],
) -> bool:
    endereco = urlparse(link)
    if endereco.scheme != "https" or endereco.hostname != "www.ibge.gov.br":
        atualizar_registro(
            registro,
            "upload_aceito_resultado_nao_confirmado",
            erro_download="O link não pertence ao domínio HTTPS esperado do IBGE.",
        )
        print("Link de resultado fora do domínio esperado; não foi acessado.")
        return False

    time.sleep(INTERVALO_REQUISICOES)
    PASTA_RESPOSTAS.mkdir(parents=True, exist_ok=True)
    caminho_temporario: Path | None = None
    try:
        with requests.get(
            link,
            timeout=(30, 120),
            stream=True,
            allow_redirects=False,
        ) as resposta:
            if not 200 <= resposta.status_code < 300:
                corpo = b"".join(
                    bloco
                    for bloco in resposta.iter_content(chunk_size=64 * 1024)
                    if bloco
                )
                caminho_erro = nome_disponivel(
                    PASTA_RESPOSTAS,
                    f"ppp_IFSC_2026-01-01_resultado_HTTP_{resposta.status_code}_{timestamp}.txt",
                )
                caminho_erro.write_bytes(corpo)
                atualizar_registro(
                    registro,
                    "upload_aceito_resultado_nao_confirmado",
                    status_download_http=resposta.status_code,
                    resposta_download=str(caminho_erro),
                )
                print(
                    "Upload aceito, mas o resultado ainda não está "
                    f"disponível (HTTP {resposta.status_code})."
                )
                print(f"Resposta do download registrada em: {caminho_erro}")
                return False

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".ppp_resultado_",
                suffix=".tmp",
                dir=PASTA_RESPOSTAS,
                delete=False,
            ) as temporario:
                caminho_temporario = Path(temporario.name)
                for bloco in resposta.iter_content(chunk_size=64 * 1024):
                    if bloco:
                        temporario.write(bloco)

        if not zipfile.is_zipfile(caminho_temporario):
            caminho_invalido = nome_disponivel(
                PASTA_RESPOSTAS,
                f"ppp_IFSC_2026-01-01_resultado_nao_zip_{timestamp}.bin",
            )
            caminho_temporario.rename(caminho_invalido)
            caminho_temporario = None
            atualizar_registro(
                registro,
                "upload_aceito_resultado_nao_confirmado",
                resposta_download=str(caminho_invalido),
                erro_download="O corpo recebido não é um arquivo ZIP.",
            )
            print("Upload aceito, mas o link não retornou um ZIP.")
            print(f"Corpo recebido preservado em: {caminho_invalido}")
            return False

        caminho_zip = nome_disponivel(
            PASTA_RESPOSTAS,
            f"ppp_IFSC_2026-01-01_resultado_{timestamp}.zip",
        )
        caminho_temporario.rename(caminho_zip)
        caminho_temporario = None
        pasta_extraida = extrair_zip_com_seguranca(caminho_zip, timestamp)
        atualizar_registro(
            registro,
            "processamento_confirmado",
            arquivo_resultado=str(caminho_zip),
            pasta_extraida=str(pasta_extraida),
        )
        print("\nPROCESSAMENTO CONFIRMADO")
        print(f"ZIP íntegro: {caminho_zip}")
        print(f"Arquivos extraídos: {pasta_extraida}")
        return True
    except requests.exceptions.Timeout as erro:
        atualizar_registro(
            registro,
            "upload_aceito_resultado_nao_confirmado",
            erro_download=f"Timeout ao consultar o resultado: {erro}",
        )
        print(f"Upload aceito, mas houve timeout ao buscar o resultado: {erro}")
        return False
    except requests.exceptions.RequestException as erro:
        atualizar_registro(
            registro,
            "upload_aceito_resultado_nao_confirmado",
            erro_download=f"Erro de rede ao consultar o resultado: {erro}",
        )
        print(f"Upload aceito, mas o resultado não foi confirmado: {erro}")
        return False
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as erro:
        atualizar_registro(
            registro,
            "upload_aceito_resultado_nao_confirmado",
            erro_validacao_zip=str(erro),
        )
        print(f"Upload aceito, mas não foi possível validar o resultado: {erro}")
        return False
    finally:
        if caminho_temporario is not None:
            caminho_temporario.unlink(missing_ok=True)


def enviar(email: str, dados: dict[str, object]) -> None:
    PASTA_RESPOSTAS.mkdir(parents=True, exist_ok=True)
    instante = horario_local()
    timestamp = timestamp_arquivo(instante)
    caminho_resposta_bruta = nome_disponivel(
        PASTA_RESPOSTAS,
        f"ppp_IFSC_2026-01-01_resposta_bruta_{timestamp}.txt",
    )
    formulario = dados_formulario(email)
    registro: dict[str, object] = {
        "inicio_local": instante.isoformat(timespec="seconds"),
        "estacao": "IFSC",
        "data": "2026-01-01",
        "dia_do_ano": 1,
        "arquivo_local": str(ARQUIVO_CONTROLE),
        "nome_multipart": NOME_MULTIPART,
        "tamanho_bytes": dados["bytes"],
        "formato": dados["formato"],
        "campos_formulario": {
            chave: (
                "[redigido]"
                if chave == "email"
                else valor
            )
            for chave, valor in formulario.items()
        },
        "arquivo_resposta_bruta": str(caminho_resposta_bruta),
        "estado": "submissao_iniciada",
    }

    try:
        with ARQUIVO_REGISTRO.open("x", encoding="utf-8") as arquivo_log:
            json.dump(registro, arquivo_log, ensure_ascii=False, indent=2)
    except FileExistsError as erro:
        raise RuntimeError(
            f"Já existe um registro de tentativa em {ARQUIVO_REGISTRO}. "
            "Por segurança, este script não fará outra submissão automática. "
            "Confira o registro e as respostas existentes antes de qualquer "
            "nova tentativa."
        ) from erro

    try:
        with ARQUIVO_CONTROLE.open("rb") as arquivo:
            resposta = requests.post(
                URL_PPP,
                data=formulario,
                files={
                    "arquivo": (
                        NOME_MULTIPART,
                        arquivo,
                        "application/gzip",
                    )
                },
                timeout=(30, 600),
            )
    except requests.exceptions.Timeout as erro:
        atualizar_registro(
            registro,
            "submissao_sem_resposta_confirmada",
            erro=f"Timeout durante o envio: {erro}",
        )
        print(f"Timeout durante o envio: {erro}")
        print(
            "Não tente novamente automaticamente: o servidor pode ter "
            "recebido o arquivo antes do timeout."
        )
        return
    except requests.exceptions.ConnectionError as erro:
        mensagem = str(erro)
        codigo_10053 = "10053" in mensagem or getattr(erro, "winerror", None) == 10053
        descricao = (
            "Conexão abortada pelo host/rede (erro 10053)."
            if codigo_10053
            else "Erro de conexão durante o envio."
        )
        atualizar_registro(
            registro,
            "submissao_sem_resposta_confirmada",
            erro=f"{descricao} {mensagem}",
        )
        print(f"{descricao} {mensagem}")
        print(
            "O resultado do POST é ambíguo; o arquivo de controle não será "
            "submetido novamente automaticamente."
        )
        return
    except requests.exceptions.RequestException as erro:
        atualizar_registro(
            registro,
            "submissao_sem_resposta_confirmada",
            erro=f"Erro de requisição: {erro}",
        )
        print(f"Erro de requisição: {erro}")
        print(
            "O resultado do POST é ambíguo; nenhuma repetição automática "
            "será feita."
        )
        return
    except OSError as erro:
        atualizar_registro(
            registro,
            "submissao_sem_resposta_confirmada",
            erro=f"Erro local ao abrir/enviar o arquivo: {erro}",
        )
        print(f"Erro local ao abrir/enviar o arquivo: {erro}")
        return

    # Persistir os bytes exatos vem antes de analisar status ou JSON.
    try:
        caminho_resposta_bruta.write_bytes(resposta.content)
    except OSError as erro:
        atualizar_registro(
            registro,
            "resposta_recebida_nao_preservada",
            status_http=resposta.status_code,
            bytes_resposta=len(resposta.content),
            erro_gravacao_resposta=str(erro),
        )
        print(
            "A API respondeu, mas não foi possível salvar os bytes brutos. "
            "A resposta não será interpretada."
        )
        print(f"Erro ao salvar: {erro}")
        return
    atualizar_registro(
        registro,
        "resposta_recebida",
        status_http=resposta.status_code,
        resposta_bruta=str(caminho_resposta_bruta),
        bytes_resposta=len(resposta.content),
    )
    print(f"HTTP {resposta.status_code}")
    print(f"Resposta bruta preservada em: {caminho_resposta_bruta}")

    try:
        resposta.raise_for_status()
    except requests.exceptions.HTTPError as erro:
        atualizar_registro(
            registro,
            "erro_http",
            erro=str(erro),
        )
        print(f"Erro HTTP; leia a resposta bruta: {erro}")
        return

    try:
        dados_json = json.loads(resposta.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        atualizar_registro(
            registro,
            "resposta_recebida_nao_interpretavel",
            erro_interpretacao=str(erro),
        )
        print("A resposta não é JSON válido; não é possível confirmar o PPP.")
        return
    if not isinstance(dados_json, dict):
        atualizar_registro(
            registro,
            "resposta_recebida_nao_interpretavel",
            erro_interpretacao="O JSON não é um objeto.",
        )
        print("A resposta JSON não é um objeto; processamento não confirmado.")
        return

    caminho_json = nome_disponivel(
        PASTA_RESPOSTAS,
        f"ppp_IFSC_2026-01-01_resposta_{timestamp}.json",
    )
    caminho_json.write_text(
        json.dumps(dados_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    atualizar_registro(
        registro,
        "resposta_interpretada",
        resposta_json=str(caminho_json),
        status_api=dados_json.get("status"),
        resumo_vazio=resumo_vazio(dados_json.get("resumo")),
    )

    if dados_json.get("status") != "OK":
        atualizar_registro(registro, "processamento_nao_confirmado")
        print("A API não confirmou o recebimento/processamento.")
        print(f"Resposta interpretada salva em: {caminho_json}")
        return

    resumo_sem_dados = resumo_vazio(dados_json.get("resumo"))
    print("A API aceitou o upload (status OK).")
    if resumo_sem_dados:
        print(
            "O resumo veio vazio; isso não confirma o processamento. "
            "Vou verificar uma única vez se o link já contém um ZIP válido."
        )

    link = dados_json.get("link")
    if not isinstance(link, str) or not link.strip():
        atualizar_registro(
            registro,
            "upload_aceito_resultado_nao_confirmado",
        )
        print("Não foi fornecido link de resultado; processamento não confirmado.")
        return

    baixar_resultado(link, timestamp, registro)


def main() -> int:
    if ARQUIVO_REGISTRO.exists():
        print(
            "Já existe um registro da tentativa de controle. "
            "Por segurança, não haverá novo POST."
        )
        print(f"Registro: {ARQUIVO_REGISTRO}")
        return 2

    try:
        dados = validar_arquivo_controle()
    except (OSError, UnicodeError, ValueError, RuntimeError) as erro:
        print(f"Pré-validação falhou; nada será enviado: {erro}")
        return 1

    email = input("E-mail para receber o resultado do IBGE-PPP: ").strip()
    if not email or "@" not in email:
        print("E-mail inválido; nada será enviado.")
        return 1

    formulario = dados_formulario(email)
    imprimir_previa(dados, formulario)
    confirmacao = input(
        "\nPara enviar somente o controle, digite ENVIAR: "
    ).strip()
    if confirmacao != "ENVIAR":
        print("Envio cancelado; nenhum POST foi feito.")
        return 0

    enviar(email, dados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
