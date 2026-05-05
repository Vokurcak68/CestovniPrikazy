/*
  Reset jednoho cestovniho prikazu pro opakovany import po smazani v Heliosu.

  Pouziti:
    1. Smaz cestak / pripadne auto v Heliosu.
    2. Dopln @ImportId.
    3. Pokud uz byl volany callback do aplikace, nastav @ResetAplikace = 1 a dopln @ApiToken.
    4. Spust skript a potom znovu synchronizuj staging, nebo rovnou otevri select k importu.
*/

DECLARE @ImportId uniqueidentifier = NULL; -- ImportId cestaku z dbo.vok_CPImportCestaky
DECLARE @ResetAplikace bit = 0;            -- 1 = zavola API a odznaci import i v aplikaci
DECLARE @ResetVozidlo bit = 1;             -- 1 = pokud slo o lokalni auto, vrati ho do fronty pro zalozeni

DECLARE @ApiUrl nvarchar(4000) = N'http://192.168.0.54:5055/api/helios/import-reset';
DECLARE @ApiToken nvarchar(4000) = N'<DOPLNIT_HELIOS_IMPORT_API_TOKEN>';

IF @ImportId IS NULL
  THROW 51200, 'Dopln @ImportId.', 1;

IF @ResetAplikace = 1
BEGIN
  IF @ApiToken = N'<DOPLNIT_HELIOS_IMPORT_API_TOKEN>'
    THROW 51201, 'Dopln @ApiToken pro reset v aplikaci.', 1;

  DECLARE @Body nvarchar(max) = (
    SELECT
      CONVERT(nvarchar(36), @ImportId) AS importId,
      CAST(@ResetVozidlo AS bit) AS resetVehicle
    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
  );

  DECLARE @Http int;
  DECLARE @HttpStatus int;
  DECLARE @Response nvarchar(max);

  EXEC sys.sp_OACreate 'MSXML2.ServerXMLHTTP.6.0', @Http OUT;
  EXEC sys.sp_OAMethod @Http, 'open', NULL, 'POST', @ApiUrl, false;
  EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'Accept', 'application/json';
  EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'Content-Type', 'application/json; charset=utf-8';
  EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'X-Helios-Import-Token', @ApiToken;
  EXEC sys.sp_OAMethod @Http, 'send', NULL, @Body;
  EXEC sys.sp_OAGetProperty @Http, 'status', @HttpStatus OUT;
  EXEC sys.sp_OAGetProperty @Http, 'responseText', @Response OUT;
  EXEC sys.sp_OADestroy @Http;

  SELECT @HttpStatus AS HttpStatus, @Response AS ApiResponse, @Body AS SentBody;

  IF @HttpStatus NOT BETWEEN 200 AND 299
    THROW 51202, 'API reset v aplikaci selhal.', 1;
END;

UPDATE dbo.vok_CPImportCestaky
SET ExportStatus = N'ready',
    IsActive = 1,
    ImportStartedAt = NULL,
    ImportFinishedAt = NULL,
    HeliosCestakId = NULL,
    ImportError = NULL,
    SyncedAt = sysdatetime()
WHERE ImportId = @ImportId;

SELECT *
FROM dbo.vok_CPImportCestakyKImportu
WHERE ImportId = @ImportId;
