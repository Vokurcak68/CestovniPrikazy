from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from urllib.request import Request, urlopen

import pyodbc


ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def connection_string() -> str:
    server = os.environ.get("ERP_DB_SERVER", "")
    database = os.environ.get("ERP_DB_NAME", "")
    user = os.environ.get("ERP_DB_USER", "")
    password = os.environ.get("ERP_DB_PASSWORD", "")
    if not all((server, database, user, password)):
        raise RuntimeError("Missing ERP_DB_SERVER, ERP_DB_NAME, ERP_DB_USER or ERP_DB_PASSWORD.")
    encrypt = os.environ.get("ERP_DB_ENCRYPT", "false").lower() in {"1", "true", "yes"}
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={'Yes' if encrypt else 'No'};"
        "TrustServerCertificate=Yes;"
    )


def split_go_batches(sql: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            batch = "\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    batch = "\n".join(current).strip()
    if batch:
        batches.append(batch)
    return batches


def ensure_schema(cursor: pyodbc.Cursor) -> None:
    ddl = (ROOT / "docs" / "helios-mssql-staging-cestaky.sql").read_text(encoding="utf-8")
    for batch in split_go_batches(ddl):
        cursor.execute(batch)
        while cursor.nextset():
            pass


def fetch_url(url: str, token: str, timeout: int) -> str:
    request = Request(url, headers={"X-Helios-Import-Token": token})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_payload(args: argparse.Namespace) -> str:
    if args.payload_file:
        return pathlib.Path(args.payload_file).read_text(encoding="utf-8")

    token = os.environ.get("HELIOS_IMPORT_API_TOKEN", "")
    if not token:
        raise RuntimeError("Missing HELIOS_IMPORT_API_TOKEN.")

    url = args.url or os.environ.get(
        "HELIOS_IMPORT_LIST_URL",
        "http://127.0.0.1:5055/api/helios/import-candidates?limit=500&shape=list",
    )
    list_payload = fetch_url(url, token, args.timeout)
    if args.no_full_payload:
        return list_payload

    full_url = args.full_url or os.environ.get(
        "HELIOS_IMPORT_FULL_URL",
        "http://127.0.0.1:5055/api/helios/import-candidates?limit=500",
    )
    full_payload = fetch_url(full_url, token, args.timeout)
    list_data = validate_payload(list_payload)
    full_data = validate_payload(full_payload)
    full_by_id = {
        str(item.get("importId") or ""): item
        for item in full_data.get("items") or []
        if isinstance(item, dict)
    }
    for item in list_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        full_item = full_by_id.get(str(item.get("importId") or ""))
        item["payloadJson"] = json.dumps(full_item or item, ensure_ascii=False)
    return json.dumps(list_data, ensure_ascii=False)


def validate_payload(payload: str) -> dict:
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError("Payload must be a JSON object with an items array.")
    return data


def sync_payload(cursor: pyodbc.Cursor, payload: str) -> dict:
    sql = """
DECLARE @Payload nvarchar(max) = ?;
DECLARE @BatchId uniqueidentifier = newid();

DECLARE @MergeLog table(ActionName nvarchar(10) NOT NULL);
DECLARE @DeactivatedCount int = 0;

;WITH src AS (
  SELECT
    ImportId,
    CisloCestovnihoPrikazu,
    StavAplikace,
    ExportStatus,
    CAST(TRY_CONVERT(datetimeoffset(0), SchvalenoDneText) AS datetime2(0)) AS SchvalenoDne,
    CAST(TRY_CONVERT(datetimeoffset(0), OdeslanoDneText) AS datetime2(0)) AS OdeslanoDne,
    CisloZamestnance,
    OsobniCisloVAplikaci,
    OsobniCisloOverenoVErp,
    Zamestnanec,
    Email,
    Organizace,
    StrediskoZamestnance,
    StrediskoNazev,
    Utvar,
    UcelCesty,
    CilCesty,
    CilCestyPlnyText,
    NavstiveneFirmy,
    Spolucestujici,
    CAST(TRY_CONVERT(datetimeoffset(0), DatVystDoklText) AS datetime2(0)) AS DatVystDokl,
    CAST(TRY_CONVERT(datetimeoffset(0), DatCasPocatekText) AS datetime2(0)) AS DatCasPocatek,
    CAST(TRY_CONVERT(datetimeoffset(0), DatCasKonecText) AS datetime2(0)) AS DatCasKonec,
    Stredisko,
    TypCesty,
    TypDopravy,
    SPZ,
    KMCelkem,
    KMZahr,
    Spotreba,
    CenaL,
    SazbaKM,
    PHMKc,
    CelkemPHM,
    CelkemDiety,
    CelkemNaklady,
    CelkemNahrady,
    CelkemPrepocet,
    MenaPrepocet,
    KurzPrepocet,
    HodinCelkem,
    Zaloha,
    DoplatekNeboVratka,
    DoplatekNeboVratkaZaokrouhlene,
    PayloadJson
  FROM OPENJSON(@Payload, '$.items')
  WITH (
    ImportId uniqueidentifier '$.importId',
    CisloCestovnihoPrikazu nvarchar(20) '$.cisloCestovnihoPrikazu',
    StavAplikace nvarchar(30) '$.status',
    ExportStatus nvarchar(30) '$.exportStatus',
    SchvalenoDneText nvarchar(50) '$.approvedAt',
    OdeslanoDneText nvarchar(50) '$.submittedAt',
    CisloZamestnance int '$.cisloZamestnance',
    OsobniCisloVAplikaci nvarchar(30) '$.osobniCisloVAplikaci',
    OsobniCisloOverenoVErp bit '$.osobniCisloOverenoVErp',
    Zamestnanec nvarchar(255) '$.zamestnanec',
    Email nvarchar(255) '$.email',
    Organizace nvarchar(255) '$.organizace',
    StrediskoZamestnance nvarchar(30) '$.strediskoZamestnance',
    StrediskoNazev nvarchar(255) '$.strediskoNazev',
    Utvar nvarchar(255) '$.utvar',
    UcelCesty nvarchar(max) '$.ucelCesty',
    CilCesty nvarchar(60) '$.cilCesty',
    CilCestyPlnyText nvarchar(255) '$.cilCestyPlnyText',
    NavstiveneFirmy nvarchar(255) '$.navstiveneFirmy',
    Spolucestujici nvarchar(255) '$.spolucestujici',
    DatVystDoklText nvarchar(50) '$.datVystDokl',
    DatCasPocatekText nvarchar(50) '$.datCasPocatek',
    DatCasKonecText nvarchar(50) '$.datCasKonec',
    Stredisko nvarchar(30) '$.stredisko',
    TypCesty nchar(1) '$.typCesty',
    TypDopravy nchar(1) '$.typDopravy',
    SPZ nvarchar(20) '$.spz',
    KMCelkem decimal(19, 6) '$.kmCelkem',
    KMZahr decimal(19, 6) '$.kmZahr',
    Spotreba decimal(19, 6) '$.spotreba',
    CenaL decimal(19, 6) '$.cenaL',
    SazbaKM decimal(19, 6) '$.sazbaKm',
    PHMKc decimal(19, 6) '$.phmKc',
    CelkemPHM decimal(19, 6) '$.celkemPhm',
    CelkemDiety decimal(19, 6) '$.celkemDiety',
    CelkemNaklady decimal(19, 6) '$.celkemNaklady',
    CelkemNahrady decimal(19, 6) '$.celkemNahrady',
    CelkemPrepocet decimal(19, 6) '$.celkemPrepocet',
    MenaPrepocet nvarchar(3) '$.menaPrepocet',
    KurzPrepocet decimal(19, 6) '$.kurzPrepocet',
    HodinCelkem decimal(19, 6) '$.hodinCelkem',
    Zaloha decimal(19, 6) '$.zaloha',
    DoplatekNeboVratka decimal(19, 6) '$.doplatekNeboVratka',
    DoplatekNeboVratkaZaokrouhlene decimal(19, 6) '$.doplatekNeboVratkaZaokrouhlene',
    PayloadJson nvarchar(max) '$.payloadJson'
  )
)
MERGE dbo.vok_CPImportCestaky AS target
USING src
ON target.ImportId = src.ImportId
WHEN MATCHED THEN UPDATE SET
  CisloCestovnihoPrikazu = src.CisloCestovnihoPrikazu,
  StavAplikace = src.StavAplikace,
  ExportStatus = src.ExportStatus,
  SchvalenoDne = src.SchvalenoDne,
  OdeslanoDne = src.OdeslanoDne,
  CisloZamestnance = src.CisloZamestnance,
  OsobniCisloVAplikaci = src.OsobniCisloVAplikaci,
  OsobniCisloOverenoVErp = src.OsobniCisloOverenoVErp,
  Zamestnanec = src.Zamestnanec,
  Email = src.Email,
  Organizace = src.Organizace,
  StrediskoZamestnance = src.StrediskoZamestnance,
  StrediskoNazev = src.StrediskoNazev,
  Utvar = src.Utvar,
  UcelCesty = src.UcelCesty,
  CilCesty = src.CilCesty,
  CilCestyPlnyText = src.CilCestyPlnyText,
  NavstiveneFirmy = src.NavstiveneFirmy,
  Spolucestujici = src.Spolucestujici,
  DatVystDokl = src.DatVystDokl,
  DatCasPocatek = src.DatCasPocatek,
  DatCasKonec = src.DatCasKonec,
  Stredisko = src.Stredisko,
  TypCesty = src.TypCesty,
  TypDopravy = src.TypDopravy,
  SPZ = src.SPZ,
  KMCelkem = src.KMCelkem,
  KMZahr = src.KMZahr,
  Spotreba = src.Spotreba,
  CenaL = src.CenaL,
  SazbaKM = src.SazbaKM,
  PHMKc = src.PHMKc,
  CelkemPHM = src.CelkemPHM,
  CelkemDiety = src.CelkemDiety,
  CelkemNaklady = src.CelkemNaklady,
  CelkemNahrady = src.CelkemNahrady,
  CelkemPrepocet = src.CelkemPrepocet,
  MenaPrepocet = src.MenaPrepocet,
  KurzPrepocet = src.KurzPrepocet,
  HodinCelkem = src.HodinCelkem,
  Zaloha = src.Zaloha,
  DoplatekNeboVratka = src.DoplatekNeboVratka,
  DoplatekNeboVratkaZaokrouhlene = src.DoplatekNeboVratkaZaokrouhlene,
  PayloadJson = src.PayloadJson,
  IsActive = 1,
  SyncBatchId = @BatchId,
  SyncedAt = sysdatetime(),
  ImportStartedAt = NULL,
  ImportFinishedAt = NULL,
  HeliosCestakId = NULL,
  ImportError = NULL
WHEN NOT MATCHED THEN INSERT (
  ImportId,
  CisloCestovnihoPrikazu,
  StavAplikace,
  ExportStatus,
  SchvalenoDne,
  OdeslanoDne,
  CisloZamestnance,
  OsobniCisloVAplikaci,
  OsobniCisloOverenoVErp,
  Zamestnanec,
  Email,
  Organizace,
  StrediskoZamestnance,
  StrediskoNazev,
  Utvar,
  UcelCesty,
  CilCesty,
  CilCestyPlnyText,
  NavstiveneFirmy,
  Spolucestujici,
  DatVystDokl,
  DatCasPocatek,
  DatCasKonec,
  Stredisko,
  TypCesty,
  TypDopravy,
  SPZ,
  KMCelkem,
  KMZahr,
  Spotreba,
  CenaL,
  SazbaKM,
  PHMKc,
  CelkemPHM,
  CelkemDiety,
  CelkemNaklady,
  CelkemNahrady,
  CelkemPrepocet,
  MenaPrepocet,
  KurzPrepocet,
  HodinCelkem,
  Zaloha,
  DoplatekNeboVratka,
  DoplatekNeboVratkaZaokrouhlene,
  PayloadJson,
  IsActive,
  SyncBatchId,
  SyncedAt
) VALUES (
  src.ImportId,
  src.CisloCestovnihoPrikazu,
  src.StavAplikace,
  src.ExportStatus,
  src.SchvalenoDne,
  src.OdeslanoDne,
  src.CisloZamestnance,
  src.OsobniCisloVAplikaci,
  src.OsobniCisloOverenoVErp,
  src.Zamestnanec,
  src.Email,
  src.Organizace,
  src.StrediskoZamestnance,
  src.StrediskoNazev,
  src.Utvar,
  src.UcelCesty,
  src.CilCesty,
  src.CilCestyPlnyText,
  src.NavstiveneFirmy,
  src.Spolucestujici,
  src.DatVystDokl,
  src.DatCasPocatek,
  src.DatCasKonec,
  src.Stredisko,
  src.TypCesty,
  src.TypDopravy,
  src.SPZ,
  src.KMCelkem,
  src.KMZahr,
  src.Spotreba,
  src.CenaL,
  src.SazbaKM,
  src.PHMKc,
  src.CelkemPHM,
  src.CelkemDiety,
  src.CelkemNaklady,
  src.CelkemNahrady,
  src.CelkemPrepocet,
  src.MenaPrepocet,
  src.KurzPrepocet,
  src.HodinCelkem,
  src.Zaloha,
  src.DoplatekNeboVratka,
  src.DoplatekNeboVratkaZaokrouhlene,
  src.PayloadJson,
  1,
  @BatchId,
  sysdatetime()
)
OUTPUT $action INTO @MergeLog;

UPDATE dbo.vok_CPImportCestaky
SET IsActive = 0,
    SyncedAt = sysdatetime()
WHERE IsActive = 1
  AND (SyncBatchId IS NULL OR SyncBatchId <> @BatchId);

SET @DeactivatedCount = @@ROWCOUNT;

SELECT
  JSON_QUERY((
    SELECT
      @BatchId AS syncBatchId,
      (SELECT count(*) FROM OPENJSON(@Payload, '$.items')) AS sourceCount,
      (SELECT count(*) FROM @MergeLog WHERE ActionName = N'INSERT') AS insertedCount,
      (SELECT count(*) FROM @MergeLog WHERE ActionName = N'UPDATE') AS updatedCount,
      @DeactivatedCount AS deactivatedCount,
      (SELECT count(*) FROM dbo.vok_CPImportCestakyKImportu) AS activeImportCount
    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
  )) AS ResultJson;
"""
    cursor.execute(sql, payload)
    result = {}
    while True:
        if cursor.description:
            rows = cursor.fetchall()
            if rows:
                result = json.loads(rows[0][0])
        if not cursor.nextset():
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync travel order import candidates into Helios MSSQL staging table.")
    parser.add_argument("--url", help="Import list URL. Defaults to local API shape=list endpoint.")
    parser.add_argument("--full-url", help="Full import payload URL. Defaults to local API import-candidates endpoint.")
    parser.add_argument("--payload-file", help="Read API JSON payload from a file instead of HTTP.")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--skip-schema", action="store_true", help="Do not create/update staging table and view.")
    parser.add_argument("--no-full-payload", action="store_true", help="Do not merge full item JSON into PayloadJson.")
    args = parser.parse_args()

    load_env(ROOT / ".env")
    payload = fetch_payload(args)
    data = validate_payload(payload)

    with pyodbc.connect(connection_string(), timeout=15) as connection:
        cursor = connection.cursor()
        if not args.skip_schema:
            ensure_schema(cursor)
        result = sync_payload(cursor, payload)
        connection.commit()

    print(json.dumps({"apiCount": data.get("count"), **result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
