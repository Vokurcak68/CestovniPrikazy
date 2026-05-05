/*
  Nastaveni API callbacku pro import cestovnich prikazu.

  Spust v Helios/MSSQL databazi po vytvoreni staging tabulek.
  Hodnota ImportApiToken musi byt stejna jako HELIOS_IMPORT_API_TOKEN v .env aplikace.
*/

IF OBJECT_ID(N'dbo.vok_CPImportNastaveni', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.vok_CPImportNastaveni (
    Klic nvarchar(100) NOT NULL CONSTRAINT PK_vok_CPImportNastaveni PRIMARY KEY,
    Hodnota nvarchar(max) NULL,
    Popis nvarchar(255) NULL,
    UpdatedAt datetime2(0) NOT NULL CONSTRAINT DF_vok_CPImportNastaveni_UpdatedAt DEFAULT (sysdatetime())
  );
END;

MERGE dbo.vok_CPImportNastaveni AS target
USING (VALUES
  (N'ImportResultsApiUrl', N'http://192.168.0.54:5055/api/helios/import-results', N'API endpoint pro oznaceni uspesneho importu cestaku v aplikaci.'),
  (N'TravelOrderPreviewUrl', N'http://192.168.0.54:5055/helios/preview', N'Read-only nahled konkretniho cestovniho prikazu vcetne dokladu.'),
  (N'ImportApiToken', N'<DOPLNIT_HELIOS_IMPORT_API_TOKEN_Z_ENV>', N'Token z .env aplikace: HELIOS_IMPORT_API_TOKEN.')
) AS src(Klic, Hodnota, Popis)
ON target.Klic = src.Klic
WHEN MATCHED THEN UPDATE SET
  Hodnota = src.Hodnota,
  Popis = src.Popis,
  UpdatedAt = sysdatetime()
WHEN NOT MATCHED THEN INSERT (Klic, Hodnota, Popis)
VALUES (src.Klic, src.Hodnota, src.Popis);

SELECT Klic, CASE WHEN Klic = N'ImportApiToken' THEN N'<skryto>' ELSE Hodnota END AS Hodnota, UpdatedAt
FROM dbo.vok_CPImportNastaveni
WHERE Klic IN (N'ImportResultsApiUrl', N'TravelOrderPreviewUrl', N'ImportApiToken');
