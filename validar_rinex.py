import gzip
import subprocess
from pathlib import Path


PASTA_PROJETO = Path(__file__).resolve().parent

PASTA_RINEX = PASTA_PROJETO / "dados" / "rinex"
PASTA_ESTATISTICAS = PASTA_PROJETO / "dados" / "estatisticas_rinex"

CRX2RNX = PASTA_PROJETO / "ferramentas" / "crx2rnx"
GFZRNX = PASTA_PROJETO / "ferramentas" / "gfzrnx"

PASTA_ESTATISTICAS.mkdir(parents=True, exist_ok=True)


def verificar_ferramentas():
    """Confere se os executáveis necessários existem."""

    if not CRX2RNX.exists():
        raise FileNotFoundError(
            f"Não foi encontrado: {CRX2RNX}"
        )

    if not GFZRNX.exists():
        raise FileNotFoundError(
            f"Não foi encontrado: {GFZRNX}"
        )


def validar_arquivo(caminho_gz):
    """
    Valida um arquivo usando a mesma cadeia que foi testada
    diretamente no terminal:
    GZIP -> CRX2RNX -> GFZRNX.
    """

    nome_saida = f"{caminho_gz.stem}_estatisticas.txt"
    caminho_saida = PASTA_ESTATISTICAS / nome_saida

    if caminho_saida.exists():
        print(f"Já validado: {caminho_gz.name}")
        return caminho_saida

    print(f"Validando: {caminho_gz.name}")

    comando = (
        'gzip -dc "$1" | '
        '"$2" - | '
        '"$3" -stk_obs'
    )

    resultado = subprocess.run(
        [
            "bash",
            "-c",
            comando,
            "_",
            str(caminho_gz),
            str(CRX2RNX),
            str(GFZRNX),
        ],
        capture_output=True,
        text=True,
    )

    # Linhas STO representam as estatísticas das observações.
    if "STO " not in resultado.stdout:
        raise RuntimeError(
            "O GFZRNX não produziu estatísticas válidas.\n"
            f"Saída de erro:\n{resultado.stderr}"
        )

    caminho_saida.write_text(
        resultado.stdout,
        encoding="utf-8",
    )

    print(f"Estatísticas salvas: {caminho_saida.name}")

    return caminho_saida

def validar_todos():
    """Valida todos os arquivos GZIP encontrados."""

    verificar_ferramentas()

    arquivos = sorted(PASTA_RINEX.glob("*.gz"))

    if not arquivos:
        print("Nenhum arquivo .gz foi encontrado.")
        return

    sucessos = []
    erros = []

    print("=" * 60)
    print("VALIDAÇÃO DOS ARQUIVOS COM GFZRNX")
    print(f"Arquivos encontrados: {len(arquivos)}")
    print("=" * 60)

    for numero, caminho_gz in enumerate(arquivos, start=1):
        print(f"\n[{numero}/{len(arquivos)}]")

        try:
            resultado = validar_arquivo(caminho_gz)
            sucessos.append(resultado)

        except Exception as erro:
            print(f"Falha: {erro}")
            erros.append(caminho_gz.name)

    print("\n" + "=" * 60)
    print("RESUMO DA VALIDAÇÃO")
    print(f"Arquivos válidos: {len(sucessos)}")
    print(f"Falhas: {len(erros)}")

    if erros:
        print("\nArquivos com falha:")
        for nome in erros:
            print(f"- {nome}")
    else:
        print("Todos os RINEX foram validados com sucesso!")

    print("=" * 60)


if __name__ == "__main__":
    validar_todos()