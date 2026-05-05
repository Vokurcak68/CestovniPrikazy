/*
  Helios / MSSQL staging pro seznam cestovnich prikazu k importu.

  Tohle je databazova vrstva, na kterou se ma napojit Helios:

    SELECT * FROM dbo.vok_CPImportCestakyKImportu;

  Tabulku plni aplikace/synchronizacni job. Helios uz nad tim dela jen
  obycejny MSSQL SELECT bez HTTP, OLE Automation a JSON volani.

  Sloupec NahledUrl otevira konkretni cestovni prikaz v aplikaci v read-only
  rezimu vcetne dokladu. Vyplnuje se z dbo.vok_CPImportNastaveni:
    TravelOrderPreviewUrl = napriklad http://192.168.0.54:5055/helios/preview
    ImportApiToken = stejny token jako HELIOS_IMPORT_API_TOKEN v aplikaci
*/

IF OBJECT_ID(N'dbo.vok_CPImportCestaky', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.vok_CPImportCestaky (
    ImportId uniqueidentifier NOT NULL CONSTRAINT PK_vok_CPImportCestaky PRIMARY KEY,
    CisloCestovnihoPrikazu nvarchar(20) NOT NULL,
    StavAplikace nvarchar(30) NOT NULL,
    ExportStatus nvarchar(30) NOT NULL,
    SchvalenoDne datetime2(0) NULL,
    OdeslanoDne datetime2(0) NULL,
    CisloZamestnance int NOT NULL,
    OsobniCisloVAplikaci nvarchar(30) NOT NULL,
    OsobniCisloOverenoVErp bit NOT NULL CONSTRAINT DF_vok_CPImportCestaky_OsobniCisloOverenoVErp DEFAULT (0),
    Zamestnanec nvarchar(255) NULL,
    Email nvarchar(255) NULL,
    Organizace nvarchar(255) NULL,
    StrediskoZamestnance nvarchar(30) NULL,
    StrediskoNazev nvarchar(255) NULL,
    Utvar nvarchar(255) NULL,
    UcelCesty nvarchar(max) NULL,
    CilCesty nvarchar(60) NULL,
    CilCestyPlnyText nvarchar(255) NULL,
    NavstiveneFirmy nvarchar(255) NULL,
    Spolucestujici nvarchar(255) NULL,
    DatVystDokl datetime2(0) NULL,
    DatCasPocatek datetime2(0) NULL,
    DatCasKonec datetime2(0) NULL,
    Stredisko nvarchar(30) NULL,
    TypCesty nchar(1) NULL,
    TypDopravy nchar(1) NULL,
    SPZ nvarchar(20) NULL,
    KMCelkem decimal(19, 6) NULL,
    KMZahr decimal(19, 6) NULL,
    Spotreba decimal(19, 6) NULL,
    CenaL decimal(19, 6) NULL,
    SazbaKM decimal(19, 6) NULL,
    PHMKc decimal(19, 6) NULL,
    CelkemPHM decimal(19, 6) NULL,
    CelkemDiety decimal(19, 6) NULL,
    CelkemNaklady decimal(19, 6) NULL,
    CelkemNahrady decimal(19, 6) NULL,
    CelkemPrepocet decimal(19, 6) NULL,
    MenaPrepocet nvarchar(3) NULL,
    KurzPrepocet decimal(19, 6) NULL,
    HodinCelkem decimal(19, 6) NULL,
    Zaloha decimal(19, 6) NULL,
    DoplatekNeboVratka decimal(19, 6) NULL,
    DoplatekNeboVratkaZaokrouhlene decimal(19, 6) NULL,
    IsActive bit NOT NULL CONSTRAINT DF_vok_CPImportCestaky_IsActive DEFAULT (1),
    SyncBatchId uniqueidentifier NULL,
    SyncedAt datetime2(0) NOT NULL CONSTRAINT DF_vok_CPImportCestaky_SyncedAt DEFAULT (sysdatetime()),
    ImportStartedAt datetime2(0) NULL,
    ImportFinishedAt datetime2(0) NULL,
    HeliosCestakId int NULL,
    ImportError nvarchar(max) NULL,
    PayloadJson nvarchar(max) NULL
  );
END;
GO

IF OBJECT_ID(N'dbo.vok_CPImportNastaveni', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.vok_CPImportNastaveni (
    Klic nvarchar(100) NOT NULL CONSTRAINT PK_vok_CPImportNastaveni PRIMARY KEY,
    Hodnota nvarchar(max) NULL,
    Popis nvarchar(255) NULL,
    UpdatedAt datetime2(0) NOT NULL CONSTRAINT DF_vok_CPImportNastaveni_UpdatedAt DEFAULT (sysdatetime())
  );
END;
GO

IF COL_LENGTH(N'dbo.vok_CPImportCestaky', N'PayloadJson') IS NULL
BEGIN
  ALTER TABLE dbo.vok_CPImportCestaky
  ADD PayloadJson nvarchar(max) NULL;
END;
GO

IF NOT EXISTS (
  SELECT 1
  FROM sys.indexes
  WHERE object_id = OBJECT_ID(N'dbo.vok_CPImportCestaky')
    AND name = N'IX_vok_CPImportCestaky_KImportu'
)
BEGIN
  CREATE INDEX IX_vok_CPImportCestaky_KImportu
  ON dbo.vok_CPImportCestaky(IsActive, ExportStatus, SchvalenoDne DESC, CisloCestovnihoPrikazu);
END;
GO

CREATE OR ALTER VIEW dbo.vok_CPImportCestakyPrehled
AS
SELECT
  cestak.ImportId,
  CASE
    WHEN COALESCE(cfg.TravelOrderPreviewUrl, N'') <> N''
     AND COALESCE(cfg.ImportApiToken, N'') <> N''
    THEN cfg.TravelOrderPreviewUrl
      + CASE WHEN CHARINDEX(N'?', cfg.TravelOrderPreviewUrl) > 0 THEN N'&' ELSE N'?' END
      + N'importId=' + CONVERT(nvarchar(36), cestak.ImportId)
      + N'&token=' + cfg.ImportApiToken
    ELSE CASE WHEN ISJSON(cestak.PayloadJson) = 1 THEN JSON_VALUE(cestak.PayloadJson, '$.previewUrl') END
  END AS NahledUrl,
  cestak.CisloCestovnihoPrikazu,
  cestak.SchvalenoDne,
  cestak.OdeslanoDne,
  cestak.CisloZamestnance,
  cestak.OsobniCisloVAplikaci,
  cestak.OsobniCisloOverenoVErp,
  cestak.Zamestnanec,
  cestak.Email,
  cestak.Organizace,
  cestak.StrediskoZamestnance,
  cestak.StrediskoNazev,
  cestak.Utvar,
  cestak.UcelCesty,
  cestak.CilCesty,
  cestak.CilCestyPlnyText,
  cestak.NavstiveneFirmy,
  cestak.Spolucestujici,
  cestak.DatVystDokl,
  cestak.DatCasPocatek,
  cestak.DatCasKonec,
  cestak.Stredisko,
  cestak.TypCesty,
  cestak.TypDopravy,
  cestak.SPZ,
  cestak.KMCelkem,
  cestak.KMZahr,
  cestak.Spotreba,
  cestak.CenaL,
  cestak.SazbaKM,
  cestak.PHMKc,
  cestak.CelkemPHM,
  cestak.CelkemDiety,
  cestak.CelkemNaklady,
  cestak.CelkemNahrady,
  cestak.CelkemPrepocet,
  cestak.MenaPrepocet,
  cestak.KurzPrepocet,
  cestak.HodinCelkem,
  cestak.Zaloha,
  cestak.DoplatekNeboVratka,
  cestak.DoplatekNeboVratkaZaokrouhlene,
  cestak.StavAplikace,
  cestak.ExportStatus,
  cestak.IsActive,
  cestak.HeliosCestakId,
  cestak.SyncedAt,
  CASE
    WHEN cestak.HeliosCestakId IS NOT NULL OR cestak.ExportStatus = N'exported' THEN N'Naimportovano'
    WHEN cestak.IsActive = 1
     AND cestak.StavAplikace = N'approved'
     AND cestak.ExportStatus <> N'exported'
     AND cestak.OsobniCisloOverenoVErp = 1
     AND cestak.HeliosCestakId IS NULL THEN N'Pripraveno k importu'
    ELSE N'Mimo import'
  END AS StavImportu
FROM dbo.vok_CPImportCestaky cestak
OUTER APPLY (
  SELECT
    MAX(CASE WHEN Klic = N'TravelOrderPreviewUrl' THEN Hodnota END) AS TravelOrderPreviewUrl,
    MAX(CASE WHEN Klic = N'ImportApiToken' THEN Hodnota END) AS ImportApiToken
  FROM dbo.vok_CPImportNastaveni
) cfg;
GO

CREATE OR ALTER VIEW dbo.vok_CPImportCestakyKImportu
AS
SELECT
  ImportId,
  NahledUrl,
  CisloCestovnihoPrikazu,
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
  StavAplikace,
  ExportStatus,
  SyncedAt,
  StavImportu
FROM dbo.vok_CPImportCestakyPrehled
WHERE IsActive = 1
  AND StavAplikace = N'approved'
  AND ExportStatus <> N'exported'
  AND OsobniCisloOverenoVErp = 1
  AND HeliosCestakId IS NULL;
GO
