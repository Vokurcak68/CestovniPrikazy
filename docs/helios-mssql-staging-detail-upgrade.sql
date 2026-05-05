/*
  Upgrade uz vytvorene staging tabulky pro samotny import.

  Seznam cestaku potrebuje jen zakladni sloupce, ale import potrebuje i useky,
  doklady a detail vozidla. Ty jsou ulozene v plnem JSON payloadu.
*/

IF COL_LENGTH(N'dbo.vok_CPImportCestaky', N'PayloadJson') IS NULL
BEGIN
  ALTER TABLE dbo.vok_CPImportCestaky
  ADD PayloadJson nvarchar(max) NULL;
END;
GO

GRANT SELECT, INSERT, UPDATE ON dbo.vok_CPImportCestaky TO zynaptec;
GO
