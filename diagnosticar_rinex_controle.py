"""Diagnóstico local e somente leitura dos arquivos RINEX do controle IFSC."""

from __future__ import annotations

import gzip
import re
from datetime import datetime, timedelta
from pathlib import Path

import hatanaka


PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVOS_CONTROLE = (
    PASTA_PROJETO / "dados" / "rinex" / "IFSC_2026_001.crx.gz",
    PASTA_PROJETO / "dados" / "rinex_convertidos" / "IFSC_2026_001.rnx",
    PASTA_PROJETO / "dados" / "rinex_convertidos" / "IFSC_2026_001.rnx.gz",
)

REGEX_EPOCA = re.compile(
    r"^>\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+"
    r"(\d{1,2})\s+(\d{1,2})\s+(\d+(?:\.\d*)?)"
)
ROTULOS_CABECALHO = (
    "RINEX VERSION / TYPE",
    "CRINEX VERS   / TYPE",
    "MARKER NAME",
    "ANT # / TYPE",
    "ANTENNA: DELTA H/E/N",
    "INTERVAL",
    "TIME OF FIRST OBS",
    "TIME OF LAST OBS",
    "END OF HEADER",
)


def ler_conteudo(caminho: Path) -> tuple[bytes, str]:
    """Lê e identifica gzip, RINEX normal ou Compact RINEX."""
    arquivo = caminho.read_bytes()

    if arquivo.startswith(b"\x1f\x8b"):
        try:
            conteudo = gzip.decompress(arquivo)
        except (OSError, EOFError) as erro:
            raise ValueError(f"GZIP inválido ou truncado: {erro}") from erro
        primeiro_trecho = conteudo[:4096].decode("ascii", errors="replace")
        formato = (
            "Compact RINEX/Hatanaka dentro de GZIP"
            if "COMPACT RINEX FORMAT" in primeiro_trecho
            else "RINEX normal dentro de GZIP"
        )
        return conteudo, formato

    primeiro_trecho = arquivo[:4096].decode("ascii", errors="replace")
    if "RINEX VERSION / TYPE" not in primeiro_trecho:
        raise ValueError("Conteúdo não identificado como RINEX ou GZIP.")
    return arquivo, "RINEX normal sem compressão"


def formatar_epoca(captura: tuple[str, ...]) -> tuple[datetime, str]:
    ano, mes, dia, hora, minuto = map(int, captura[:5])
    segundos = float(captura[5])
    instante = datetime(ano, mes, dia, hora, minuto) + timedelta(
        seconds=segundos
    )
    return instante, instante.isoformat(timespec="microseconds")


def inspecionar(caminho: Path) -> dict[str, object]:
    conteudo, formato = ler_conteudo(caminho)

    if formato.startswith("Compact RINEX"):
        try:
            rinex = hatanaka.decompress(conteudo)
        except Exception as erro:
            raise ValueError(f"Falha ao decodificar Hatanaka: {erro}") from erro
    else:
        rinex = conteudo

    texto = rinex.decode("ascii", errors="strict")
    linhas = texto.splitlines()
    try:
        fim_cabecalho = next(
            indice
            for indice, linha in enumerate(linhas)
            if linha[60:].strip() == "END OF HEADER"
        )
    except StopIteration as erro:
        raise ValueError("END OF HEADER não encontrado.") from erro

    cabecalho = linhas[: fim_cabecalho + 1]
    encontrados: dict[str, str] = {}
    for linha in cabecalho:
        rotulo = linha[60:].strip()
        if rotulo in ROTULOS_CABECALHO:
            encontrados[rotulo] = linha

    obrigatorios = (
        "RINEX VERSION / TYPE",
        "MARKER NAME",
        "ANT # / TYPE",
        "ANTENNA: DELTA H/E/N",
        "INTERVAL",
        "TIME OF FIRST OBS",
        "TIME OF LAST OBS",
    )
    ausentes = [rotulo for rotulo in obrigatorios if rotulo not in encontrados]
    if ausentes:
        raise ValueError(f"Campos ausentes no cabeçalho: {', '.join(ausentes)}")

    marcador = encontrados["MARKER NAME"][:60].strip()
    linha_antena = encontrados["ANT # / TYPE"]
    tipo_antena = linha_antena[20:40].strip()
    partes_antena = tipo_antena.split(maxsplit=1)
    if not partes_antena:
        raise ValueError("ANT # / TYPE não contém modelo de antena.")
    modelo_antena = partes_antena[0]
    radome = partes_antena[1] if len(partes_antena) > 1 else ""
    altura = float(encontrados["ANTENNA: DELTA H/E/N"][:14].strip())
    intervalo = float(encontrados["INTERVAL"][:10].strip())

    epocas = []
    for linha in linhas[fim_cabecalho + 1 :]:
        captura = REGEX_EPOCA.match(linha)
        if captura:
            epocas.append(formatar_epoca(captura.groups()))
    if not epocas:
        raise ValueError("Nenhuma época de observação RINEX 3 foi encontrada.")

    espacamentos = [
        (posterior[0] - anterior[0]).total_seconds()
        for anterior, posterior in zip(epocas, epocas[1:])
    ]
    return {
        "caminho": caminho,
        "formato": formato,
        "bytes": caminho.stat().st_size,
        "cabecalho": cabecalho,
        "marcador": marcador,
        "modelo_antena": modelo_antena,
        "radome": radome,
        "altura": altura,
        "intervalo": intervalo,
        "primeira_epoca": epocas[0][1],
        "ultima_epoca": epocas[-1][1],
        "quantidade_epocas": len(epocas),
        "espacamentos": espacamentos,
    }


def imprimir_diagnostico(caminho: Path) -> dict[str, object] | None:
    print("=" * 78)
    print(f"Arquivo: {caminho}")
    if not caminho.is_file():
        print("ERRO: arquivo não encontrado.")
        return None

    try:
        dados = inspecionar(caminho)
    except (OSError, UnicodeError, ValueError) as erro:
        print(f"ERRO DE VALIDAÇÃO: {erro}")
        return None

    tamanho_mb = int(dados["bytes"]) / (1024 * 1024)
    print(f"Formato detectado: {dados['formato']}")
    print(f"Tamanho: {dados['bytes']:,} bytes ({tamanho_mb:.3f} MiB)")
    print("Integridade do conteúdo: válida")
    cabecalho = dados["cabecalho"]
    print("Início do cabeçalho:")
    for linha in cabecalho[:12]:
        print(f"  {linha}")
    if len(cabecalho) > 12:
        print(f"  ... ({len(cabecalho) - 12} linhas validadas; campos-chave abaixo)")
    print(f"MARKER NAME: {dados['marcador']}")
    print(
        f"ANT # / TYPE: {dados['modelo_antena']} {dados['radome']}".rstrip()
    )
    print(f"ANTENNA: DELTA H/E/N (H): {dados['altura']:.4f} m")
    print(f"INTERVAL: {dados['intervalo']:.3f} s")
    print(f"Primeira época: {dados['primeira_epoca']}")
    print(f"Última época: {dados['ultima_epoca']}")
    print(f"Quantidade de épocas: {dados['quantidade_epocas']}")

    espacamentos = dados["espacamentos"]
    if espacamentos:
        print(
            "Espaçamento real entre épocas: "
            f"mínimo {min(espacamentos):.3f} s; "
            f"máximo {max(espacamentos):.3f} s"
        )
    return dados


def main() -> int:
    print("DIAGNÓSTICO LOCAL — CONTROLE IFSC, 01/01/2026 (DIA 001)")
    print("Nenhum arquivo será alterado e nenhuma requisição será enviada.")
    resultados = [imprimir_diagnostico(caminho) for caminho in ARQUIVOS_CONTROLE]

    validos = [resultado for resultado in resultados if resultado is not None]
    if validos:
        origem = validos[0]
        if origem["formato"].startswith("Compact RINEX"):
            print("=" * 78)
            print("VERIFICAÇÃO CRUZADA")
            normais = [
                resultado
                for resultado in validos
                if resultado["formato"].startswith("RINEX normal")
            ]
            for normal in normais:
                compactado, _ = ler_conteudo(Path(origem["caminho"]))
                normal_bytes, _ = ler_conteudo(Path(normal["caminho"]))
                decodificado = hatanaka.decompress(compactado)
                print(
                    f"Hatanaka -> {Path(normal['caminho']).name}: "
                    f"{'idêntico byte a byte' if decodificado == normal_bytes else 'DIFERENTE'}"
                )

    falhas = len(resultados) - len(validos)
    print("=" * 78)
    print(f"Arquivos validados: {len(validos)}/{len(resultados)}")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
