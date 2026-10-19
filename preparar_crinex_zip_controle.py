"""Cria e valida um ZIP de controle contendo CRINEX sem a camada GZIP."""

from __future__ import annotations

import gzip
import hashlib
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import hatanaka


API_CONTRATO = "https://servicodados.ibge.gov.br/api/docs/ppp?versao=1"
PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_ORIGINAL = (
    PASTA_PROJETO / "dados" / "rinex" / "IFSC_2026_001.crx.gz"
)
ARQUIVO_RINEX_NORMAL = (
    PASTA_PROJETO / "dados" / "rinex_convertidos" / "IFSC_2026_001.rnx"
)
PASTA_SAIDA = PASTA_PROJETO / "dados" / "rinex_convertidos"
NOME_INTERNO = "IFSC00BRA_R_20260010000_01D_15S_MO.crx"
ARQUIVO_ZIP = PASTA_SAIDA / "IFSC00BRA_R_20260010000_01D_15S_MO.zip"
TAMANHO_MAXIMO_API = 10_000_000

REGEX_EPOCA = re.compile(
    r"^>\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+"
    r"(\d{1,2})\s+(\d{1,2})\s+(\d+(?:\.\d*)?)"
)


def validar_rinex_normal(conteudo: bytes) -> dict[str, object]:
    texto = conteudo.decode("ascii", errors="strict")
    linhas = texto.splitlines()
    try:
        fim_cabecalho = next(
            indice
            for indice, linha in enumerate(linhas)
            if linha[60:].strip() == "END OF HEADER"
        )
    except StopIteration as erro:
        raise ValueError("RINEX reconstruído sem END OF HEADER.") from erro

    cabecalho = linhas[: fim_cabecalho + 1]
    campos: dict[str, str] = {}
    for linha in cabecalho:
        rotulo = linha[60:].strip()
        if rotulo in {
            "RINEX VERSION / TYPE",
            "MARKER NAME",
            "ANT # / TYPE",
            "ANTENNA: DELTA H/E/N",
            "INTERVAL",
            "TIME OF FIRST OBS",
            "TIME OF LAST OBS",
        }:
            campos[rotulo] = linha

    necessarios = {
        "RINEX VERSION / TYPE",
        "MARKER NAME",
        "ANT # / TYPE",
        "ANTENNA: DELTA H/E/N",
        "INTERVAL",
        "TIME OF FIRST OBS",
        "TIME OF LAST OBS",
    }
    faltando = necessarios - campos.keys()
    if faltando:
        raise ValueError(
            "RINEX reconstruído sem campos: " + ", ".join(sorted(faltando))
        )
    if campos["RINEX VERSION / TYPE"][:9].strip() != "3.05":
        raise ValueError("Versão RINEX reconstruída não é 3.05.")
    if campos["MARKER NAME"][:60].strip() != "IFSC":
        raise ValueError("MARKER NAME reconstruído não é IFSC.")

    antena = campos["ANT # / TYPE"][20:60].split()
    if antena != ["TRM159900.00", "NONE"]:
        raise ValueError(f"ANT # / TYPE inesperado: {antena!r}")
    altura = float(campos["ANTENNA: DELTA H/E/N"][:14].strip())
    if abs(altura - 0.0080) > 1e-9:
        raise ValueError(f"Altura de antena inesperada: {altura}")
    intervalo = float(campos["INTERVAL"][:10].strip())
    if abs(intervalo - 15.0) > 1e-9:
        raise ValueError(f"Intervalo no cabeçalho inesperado: {intervalo}")

    epocas: list[datetime] = []
    for linha in linhas[fim_cabecalho + 1 :]:
        captura = REGEX_EPOCA.match(linha)
        if captura:
            ano, mes, dia, hora, minuto = map(int, captura.groups()[:5])
            segundos = float(captura.group(6))
            epocas.append(
                datetime(ano, mes, dia, hora, minuto)
                + timedelta(seconds=segundos)
            )
    if len(epocas) != 5760:
        raise ValueError(f"Esperadas 5760 épocas; encontradas {len(epocas)}.")
    if epocas[0] != datetime(2026, 1, 1, 0, 0, 0):
        raise ValueError(f"Primeira época inesperada: {epocas[0].isoformat()}")
    if epocas[-1] != datetime(2026, 1, 1, 23, 59, 45):
        raise ValueError(f"Última época inesperada: {epocas[-1].isoformat()}")
    if any(
        (depois - antes).total_seconds() != 15
        for antes, depois in zip(epocas, epocas[1:])
    ):
        raise ValueError("Foi encontrado espaçamento de época diferente de 15 s.")

    return {
        "versao": "3.05",
        "marcador": "IFSC",
        "modelo_antena": antena[0],
        "radome": antena[1],
        "altura": altura,
        "intervalo": intervalo,
        "primeira_epoca": epocas[0].isoformat(),
        "ultima_epoca": epocas[-1].isoformat(),
        "quantidade_epocas": len(epocas),
    }


def validar_origem() -> tuple[bytes, bytes, dict[str, object]]:
    if not ARQUIVO_ORIGINAL.is_file():
        raise FileNotFoundError(f"RINEX compacto original ausente: {ARQUIVO_ORIGINAL}")
    bytes_gzip = ARQUIVO_ORIGINAL.read_bytes()
    if not bytes_gzip.startswith(b"\x1f\x8b"):
        raise ValueError("O arquivo original não tem assinatura GZIP.")

    try:
        compact_rinex = gzip.decompress(bytes_gzip)
    except (OSError, EOFError) as erro:
        raise ValueError(f"GZIP original corrompido ou truncado: {erro}") from erro
    if not compact_rinex.startswith(
        b"3.0                 COMPACT RINEX FORMAT"
    ):
        raise ValueError(
            "Após remover GZIP, o conteúdo não começa com cabeçalho CRINEX."
        )
    if b"CRINEX VERS   / TYPE" not in compact_rinex[:256]:
        raise ValueError("Cabeçalho CRINEX não encontrado no conteúdo interno.")

    try:
        rinex_normal = hatanaka.decompress(compact_rinex, strict=True)
    except Exception as erro:
        raise ValueError(f"CRINEX/Hatanaka inválido: {erro}") from erro
    dados = validar_rinex_normal(rinex_normal)

    if ARQUIVO_RINEX_NORMAL.is_file():
        rnx_existente = ARQUIVO_RINEX_NORMAL.read_bytes()
        if rnx_existente != rinex_normal:
            raise ValueError(
                "RINEX normal reconstruído difere do controle convertido já "
                "existente; ZIP não será criado."
            )
        dados["coincide_rinex_normal_existente"] = True
    else:
        dados["coincide_rinex_normal_existente"] = None
    return bytes_gzip, compact_rinex, dados


def criar_zip(compact_rinex: bytes) -> None:
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    criado = False
    try:
        with ARQUIVO_ZIP.open("xb") as arquivo_saida:
            criado = True
            with zipfile.ZipFile(
                arquivo_saida,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as arquivo_zip:
                arquivo_zip.writestr(NOME_INTERNO, compact_rinex)
    except Exception:
        if criado:
            ARQUIVO_ZIP.unlink(missing_ok=True)
        raise


def validar_zip(
    bytes_gzip: bytes,
    compact_original: bytes,
    rinex_esperado: dict[str, object],
) -> tuple[bytes, dict[str, object]]:
    if not zipfile.is_zipfile(ARQUIVO_ZIP):
        raise ValueError("O arquivo criado não é um ZIP válido.")
    with zipfile.ZipFile(ARQUIVO_ZIP, mode="r") as arquivo_zip:
        if arquivo_zip.testzip() is not None:
            raise ValueError("CRC do ZIP inválido.")
        membros = [info for info in arquivo_zip.infolist() if not info.is_dir()]
        if len(membros) != 1 or membros[0].filename != NOME_INTERNO:
            raise ValueError(
                "O ZIP deve conter somente o nome interno "
                f"{NOME_INTERNO!r}."
            )
        interno = arquivo_zip.read(NOME_INTERNO)

    if interno.startswith(b"\x1f\x8b"):
        raise ValueError("O membro do ZIP ainda contém uma camada GZIP.")
    if interno != compact_original:
        raise ValueError(
            "Conteúdo interno do ZIP difere dos bytes CRINEX descompactados."
        )
    if hashlib.sha256(interno).digest() != hashlib.sha256(
        gzip.decompress(bytes_gzip)
    ).digest():
        raise ValueError("SHA-256 interno não corresponde ao CRINEX de origem.")

    reconstruido = hatanaka.decompress(interno, strict=True)
    dados_reconstruidos = validar_rinex_normal(reconstruido)
    chaves_rinex = (
        "versao",
        "marcador",
        "modelo_antena",
        "radome",
        "altura",
        "intervalo",
        "primeira_epoca",
        "ultima_epoca",
        "quantidade_epocas",
    )
    if any(
        dados_reconstruidos[chave] != rinex_esperado[chave]
        for chave in chaves_rinex
    ):
        raise ValueError("Metadados do RINEX reconstruído foram alterados.")
    return interno, dados_reconstruidos


def mostrar_previa(
    bytes_gzip: bytes,
    compact_rinex: bytes,
    interno: bytes,
    dados: dict[str, object],
) -> None:
    tamanho = ARQUIVO_ZIP.stat().st_size
    formulario = {
        "tipo-levantamento": "estatico",
        "modelo-antena": "TRM159900.00    NONE",
        "altura-antena": "0.0080",
        "marco-ibge": "SAT94052",
        "email": "<informar no envio autorizado>",
        "autorizacao-uso": "true",
    }
    print("\nALTERNATIVA PREPARADA — NÃO ENVIADA")
    print(f"Arquivo para eventual envio: {ARQUIVO_ZIP}")
    print("Formato: ZIP (ZIP_DEFLATED) contendo Compact RINEX/Hatanaka sem GZIP")
    print(f"Nome do membro interno: {NOME_INTERNO}")
    print(f"Tamanho GZIP original: {len(bytes_gzip):,} bytes")
    print(f"Tamanho do CRINEX interno: {len(compact_rinex):,} bytes")
    print(f"Tamanho final do ZIP: {tamanho:,} bytes ({tamanho / 1_000_000:.3f} MB)")
    print(f"SHA-256 do membro CRINEX: {hashlib.sha256(interno).hexdigest()}")
    print(
        "RINEX reconstruído: "
        f"{dados['versao']}; época {dados['primeira_epoca']} até "
        f"{dados['ultima_epoca']}; intervalo {dados['intervalo']:.0f} s; "
        f"{dados['quantidade_epocas']} épocas."
    )
    print(
        "Membro idêntico ao conteúdo CRINEX após descompactar GZIP: sim; "
        "camada GZIP no membro: não."
    )
    print(
        "Contrato API: aceita as extensões .crx, .gz e .zip; "
        "limite documentado de 10 MB por requisição."
    )
    print(
        "Nota: a documentação não descreve explicitamente a estrutura interna "
        "de um .zip; confirme esse detalhe com o IBGE antes da submissão."
    )
    print("Campos multipart previstos:")
    print(f"  arquivo: {ARQUIVO_ZIP.name} (application/zip)")
    for nome, valor in formulario.items():
        print(f"  {nome}: {valor}")
    if tamanho >= TAMANHO_MAXIMO_API:
        raise ValueError(
            "ZIP não está abaixo do limite documentado de 10 MB."
        )
    print("Submissão: NÃO realizada. É necessária autorização explícita.")


def main() -> int:
    zip_criado = False
    try:
        bytes_gzip, compact_rinex, dados_rinex = validar_origem()
        criar_zip(compact_rinex)
        zip_criado = True
        interno, dados_reconstruidos = validar_zip(
            bytes_gzip,
            compact_rinex,
            dados_rinex,
        )
        mostrar_previa(
            bytes_gzip,
            compact_rinex,
            interno,
            dados_reconstruidos,
        )
    except (
        FileExistsError,
        OSError,
        UnicodeError,
        ValueError,
        zipfile.BadZipFile,
    ) as erro:
        if zip_criado:
            ARQUIVO_ZIP.unlink(missing_ok=True)
        print(f"Falha na preparação local; nenhum envio foi feito: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
