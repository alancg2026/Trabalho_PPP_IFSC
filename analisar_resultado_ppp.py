from __future__ import annotations

import csv
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "dados" / "resultados_ppp" / "2026-01-01"
OUTPUT_DIR = ROOT / "resultados"
CSV_OUTPUT = OUTPUT_DIR / "resultado_ppp_ifsc.csv"
TXT_OUTPUT = OUTPUT_DIR / "resumo_ppp_ifsc.txt"


class AnalysisError(Exception):
    """Erro previsível ao localizar, ler ou interpretar os arquivos PPP."""


def find_file(folder: Path, suffix: str, *, exclude: str = "") -> Path:
    matches = sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.casefold() == suffix.casefold()
        and (not exclude or exclude.casefold() not in path.name.casefold())
    )
    if not matches:
        raise AnalysisError(f"Nenhum arquivo {suffix} encontrado em: {folder}")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise AnalysisError(
            f"Mais de um arquivo {suffix} encontrado; não é seguro escolher "
            f"automaticamente: {names}"
        )
    return matches[0]


def read_text(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisError(f"Não foi possível ler {path}: {exc}") from exc
    if not raw:
        raise AnalysisError(f"O arquivo está vazio: {path}")

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise AnalysisError(f"Não foi possível decodificar o arquivo: {path}")


def read_key_values(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            fields[parts[0].upper()] = parts[1].strip()
    return fields


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    return float(match.group().replace(",", "."))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("/", "-").replace(",", ".")
    normalized = normalized.replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def parse_dms(value: str | None) -> tuple[str | None, float | None]:
    if not value:
        return None, None
    parts = value.split()
    if len(parts) < 3:
        return value, None
    try:
        degrees = float(parts[0].replace(",", "."))
        minutes = float(parts[1].replace(",", "."))
        seconds = float(parts[2].replace(",", "."))
    except ValueError:
        return value, None
    sign = -1.0 if degrees < 0 else 1.0
    decimal_degrees = sign * (abs(degrees) + minutes / 60 + seconds / 3600)
    return value, decimal_degrees


def parse_position_series(path: Path) -> dict[str, Any]:
    text, encoding = read_text(path)
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        parts = line.split()
        if len(parts) < 27 or parts[0] not in {"FWD", "BWD"}:
            continue
        try:
            timestamp = datetime.fromisoformat(f"{parts[4]}T{parts[5]}")
            latitude_text = f"{parts[20]} {parts[21]} {parts[22]}"
            longitude_text = f"{parts[23]} {parts[24]} {parts[25]}"
            latitude = parse_dms(latitude_text)[1]
            longitude = parse_dms(longitude_text)[1]
            record = {
                "timestamp": timestamp,
                "station": parts[2],
                "frame": parts[1],
                "satellites": int(parts[6]),
                "gdop": float(parts[7]),
                "sdc_m": float(parts[8]),
                "sdp_m": float(parts[9]),
                "latitude_deg": latitude,
                "longitude_deg": longitude,
                "height_m": float(parts[26]),
                "sigma_latitude_m": float(parts[15]),
                "sigma_longitude_m": float(parts[16]),
                "sigma_height_m": float(parts[17]),
            }
        except (IndexError, ValueError) as exc:
            warnings.append(
                f"Linha {line_number} de {path.name} não pôde ser interpretada: {exc}"
            )
            continue
        records.append(record)

    if not records:
        raise AnalysisError(
            f"Nenhuma época de posicionamento válida foi encontrada em {path}"
        )

    records.sort(key=lambda record: record["timestamp"])
    intervals = [
        (later["timestamp"] - earlier["timestamp"]).total_seconds()
        for earlier, later in zip(records, records[1:])
    ]
    return {
        "encoding": encoding,
        "records": records,
        "count": len(records),
        "first": records[0],
        "last": records[-1],
        "median_interval_s": statistics.median(intervals) if intervals else None,
        "min_interval_s": min(intervals) if intervals else None,
        "max_interval_s": max(intervals) if intervals else None,
        "mean_gdop": statistics.mean(record["gdop"] for record in records),
        "warnings": warnings,
    }


def extract_sum_details(text: str) -> dict[str, str | None]:
    lines = text.splitlines()

    def find_value(pattern: str) -> str | None:
        for line in lines:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def find_observation_code(label: str) -> str | None:
        for line in lines:
            if line.strip().casefold().startswith(label.casefold()):
                if ":" in line:
                    return line.split(":", maxsplit=1)[1].strip()
                return line.split()[-1]
        return None

    return {
        "codigo_l1": find_observation_code("Codigo L1"),
        "codigo_l2": find_observation_code("Codigo L2"),
        "antena_no_sum": find_value(r"Modelo da Antena\s+(.+)"),
        "transformacao_referencial": find_value(r"(ITRF\s*\([^)]+\)\s*->\s*SIRGAS2000[^\r\n]*)"),
    }


def make_result(fields: dict[str, str], series: dict[str, Any], sum_details: dict[str, str | None]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    def required_text(key: str) -> str | None:
        value = fields.get(key)
        if value is None:
            warnings.append(f"Campo {key} não localizado no arquivo .txt.")
        return value

    def required_number(key: str) -> float | None:
        value = required_text(key)
        number = parse_number(value)
        if value is not None and number is None:
            warnings.append(f"O campo {key} não contém um número reconhecível: {value!r}")
        return number

    latitude_dms, latitude_decimal = parse_dms(fields.get("LAT"))
    longitude_dms, longitude_decimal = parse_dms(fields.get("LON"))
    if fields.get("LAT") and latitude_decimal is None:
        warnings.append(f"Não foi possível interpretar a latitude: {fields['LAT']!r}")
    if fields.get("LON") and longitude_decimal is None:
        warnings.append(f"Não foi possível interpretar a longitude: {fields['LON']!r}")

    start = parse_datetime(fields.get("INICIO"))
    end = parse_datetime(fields.get("FIM"))
    processed = parse_datetime(fields.get("PROCES"))
    datum = fields.get("DATUM")
    reference_epoch_match = re.search(r"época\s+([\d.,]+)", datum or "", re.IGNORECASE)
    reference_epoch = (
        parse_number(reference_epoch_match.group(1))
        if reference_epoch_match
        else None
    )
    duration_s = (end - start).total_seconds() if start and end else None

    row: dict[str, Any] = {
        "estacao": required_text("MARCO"),
        "arquivo_rinex": required_text("RINEX"),
        "processado_em": processed.isoformat(sep=" ") if processed else required_text("PROCES"),
        "inicio_observacao": start.isoformat(sep=" ") if start else required_text("INICIO"),
        "fim_observacao": end.isoformat(sep=" ") if end else required_text("FIM"),
        "duracao_observacao_entre_epocas_s": duration_s,
        "modo_processamento": required_text("MODO"),
        "antena": required_text("ANTENA"),
        "altura_antena_m": required_number("ALTANT"),
        "intervalo_observacoes_s": required_number("INTERV"),
        "frequencia_processada": required_text("FREQ"),
        "tipo_observacao": required_text("OBSERV"),
        "orbita": required_text("ORBITA"),
        "referencial_e_epoca": datum,
        "epoca_referencial_ano": reference_epoch,
        "latitude_dms": latitude_dms,
        "latitude_graus_decimais": latitude_decimal,
        "longitude_dms": longitude_dms,
        "longitude_graus_decimais": longitude_decimal,
        "altitude_geometrica_elipsoidal_m": required_number("HGEO"),
        "sigma95_latitude_m": required_number("SLAT"),
        "sigma95_longitude_m": required_number("SLON"),
        "sigma95_altitude_m": required_number("SHGEO"),
        "utm_norte_m": required_number("UTMN"),
        "utm_leste_m": required_number("UTME"),
        "utm_meridiano_central_graus": required_number("MC"),
        "modelo_altitude": fields.get("MODELO"),
        "fator_correcao_modelo_m": required_number("FATCOR"),
        "incerteza_modelo_altitude_m": required_number("INCERT"),
        "altitude_normal_hnor_m": required_number("HNOR"),
        "ondulacao_geoidal_m": required_number("ONDGEO"),
        "altitude_ortometrica_hort_m": required_number("HORT"),
        "coordenada_cartesiana_x_m": None,
        "coordenada_cartesiana_y_m": None,
        "coordenada_cartesiana_z_m": None,
        "pos_numero_epocas": series["count"],
        "pos_primeira_epoca": series["first"]["timestamp"].isoformat(sep=" "),
        "pos_ultima_epoca": series["last"]["timestamp"].isoformat(sep=" "),
        "pos_intervalo_mediano_s": series["median_interval_s"],
        "pos_intervalo_minimo_s": series["min_interval_s"],
        "pos_intervalo_maximo_s": series["max_interval_s"],
        "pos_gdop_medio": series["mean_gdop"],
        "sum_codigo_l1": sum_details["codigo_l1"],
        "sum_codigo_l2": sum_details["codigo_l2"],
        "sum_antena": sum_details["antena_no_sum"],
        "sum_transformacao_referencial": sum_details["transformacao_referencial"],
    }
    return row, warnings


def format_value(value: Any) -> str:
    if value is None or value == "":
        return "Não informado nos arquivos de resultado."
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def write_outputs(row: dict[str, Any], warnings: list[str]) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with CSV_OUTPUT.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

        labels = {
            "estacao": "Estação/marco",
            "arquivo_rinex": "Arquivo RINEX",
            "processado_em": "Processado em",
            "inicio_observacao": "Início da observação",
            "fim_observacao": "Fim da observação",
            "duracao_observacao_entre_epocas_s": "Duração entre primeira e última época (s)",
            "modo_processamento": "Modo de processamento",
            "antena": "Antena",
            "altura_antena_m": "Altura da antena (m)",
            "intervalo_observacoes_s": "Intervalo de observação (s)",
            "frequencia_processada": "Frequência",
            "tipo_observacao": "Tipo de observação",
            "orbita": "Órbita",
            "referencial_e_epoca": "Referencial e época",
            "epoca_referencial_ano": "Época do referencial (ano)",
            "latitude_dms": "Latitude (graus, minutos, segundos)",
            "latitude_graus_decimais": "Latitude (graus decimais; convertida do DMS)",
            "longitude_dms": "Longitude (graus, minutos, segundos)",
            "longitude_graus_decimais": "Longitude (graus decimais; convertida do DMS)",
            "altitude_geometrica_elipsoidal_m": "Altitude geométrica/elipsoidal (m)",
            "sigma95_latitude_m": "Sigma 95% da latitude (m)",
            "sigma95_longitude_m": "Sigma 95% da longitude (m)",
            "sigma95_altitude_m": "Sigma 95% da altitude (m)",
            "utm_norte_m": "UTM norte (m)",
            "utm_leste_m": "UTM leste (m)",
            "utm_meridiano_central_graus": "Meridiano central UTM (graus)",
            "modelo_altitude": "Modelo de altitude",
            "fator_correcao_modelo_m": "Fator de correção do modelo (m)",
            "incerteza_modelo_altitude_m": "Incerteza do modelo de altitude (m)",
            "altitude_normal_hnor_m": "Altitude normal HNOR (m; não confundir com ortométrica)",
            "ondulacao_geoidal_m": "Ondulação geoidal (m)",
            "altitude_ortometrica_hort_m": "Altitude ortométrica HORT (m)",
            "coordenada_cartesiana_x_m": "Coordenada cartesiana X (m)",
            "coordenada_cartesiana_y_m": "Coordenada cartesiana Y (m)",
            "coordenada_cartesiana_z_m": "Coordenada cartesiana Z (m)",
            "pos_numero_epocas": "Épocas válidas no arquivo POS",
            "pos_primeira_epoca": "Primeira época no POS",
            "pos_ultima_epoca": "Última época no POS",
            "pos_intervalo_mediano_s": "Intervalo mediano entre épocas POS (s)",
            "pos_intervalo_minimo_s": "Menor intervalo entre épocas POS (s)",
            "pos_intervalo_maximo_s": "Maior intervalo entre épocas POS (s)",
            "pos_gdop_medio": "GDOP médio no POS",
            "sum_codigo_l1": "Código usado em L1 (SUM)",
            "sum_codigo_l2": "Código usado em L2 (SUM)",
            "sum_antena": "Modelo de antena (SUM)",
            "sum_transformacao_referencial": "Transformação de referencial (SUM)",
        }
        report_lines = [
            "RESUMO DO RESULTADO IBGE-PPP — ESTAÇÃO IFSC",
            "",
            f"Pasta analisada: {RESULTS_DIR}",
            "Solução estática: coordenadas finais lidas do arquivo .txt do IBGE-PPP.",
            "O arquivo .pos contém uma série temporal; seus valores de época não substituem "
            "a coordenada final estática do .txt.",
            "",
        ]
        report_lines.extend(
            f"{labels.get(key, key)}: {format_value(value)}"
            for key, value in row.items()
        )
        report_lines.extend(
            [
                "",
                "Observações sobre disponibilidade:",
                "- X, Y e Z cartesianos não aparecem nos arquivos analisados.",
                "- HORT e ondulação geoidal não foram informados; HNOR é altitude normal "
                "do modelo hgeoHNOR_IMBITUBA e não foi rotulada como altitude ortométrica.",
                "- Conversões de latitude/longitude para graus decimais foram calculadas "
                "a partir dos DMS informados pelo PPP.",
                "",
                "Arquivos de texto lidos: .txt, .sum e .pos.",
            ]
        )
        if warnings:
            report_lines.extend(["", "Avisos:"])
            report_lines.extend(f"- {warning}" for warning in warnings)
        else:
            report_lines.extend(["", "Avisos: nenhum."])
        TXT_OUTPUT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"Não foi possível gravar os arquivos em {OUTPUT_DIR}: {exc}") from exc


def main() -> int:
    if not RESULTS_DIR.is_dir():
        print(f"ERRO: pasta dos resultados não encontrada: {RESULTS_DIR}", file=sys.stderr)
        return 2

    try:
        pos_path = find_file(RESULTS_DIR, ".pos")
        sum_path = find_file(RESULTS_DIR, ".sum")
        text_path = find_file(RESULTS_DIR, ".txt", exclude="LEIAME")
        pos_data = parse_position_series(pos_path)
        summary_text, summary_encoding = read_text(text_path)
        sum_text, sum_encoding = read_text(sum_path)
        fields = read_key_values(summary_text)
        sum_details = extract_sum_details(sum_text)
        row, warnings = make_result(fields, pos_data, sum_details)
        warnings.extend(pos_data["warnings"])
        write_outputs(row, warnings)
    except AnalysisError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERRO: problema de acesso aos arquivos do resultado: {exc}", file=sys.stderr)
        return 2

    print("Análise do resultado IBGE-PPP concluída.")
    print(f"Estação: {format_value(row['estacao'])}")
    print(f"Latitude: {format_value(row['latitude_dms'])} "
          f"({format_value(row['latitude_graus_decimais'])}°)")
    print(f"Longitude: {format_value(row['longitude_dms'])} "
          f"({format_value(row['longitude_graus_decimais'])}°)")
    print(f"Altitude geométrica/elipsoidal: "
          f"{format_value(row['altitude_geometrica_elipsoidal_m'])} m")
    print(f"Altitude normal HNOR: {format_value(row['altitude_normal_hnor_m'])} m")
    print(f"Épocas no .pos: {row['pos_numero_epocas']}; "
          f"intervalo mediano: {format_value(row['pos_intervalo_mediano_s'])} s")
    print(f"CSV: {CSV_OUTPUT}")
    print(f"Resumo TXT: {TXT_OUTPUT}")
    for warning in warnings:
        print(f"AVISO: {warning}")
    print(f"Codificações lidas: .txt={summary_encoding}, .sum={sum_encoding}, "
      f".pos={pos_data['encoding']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
