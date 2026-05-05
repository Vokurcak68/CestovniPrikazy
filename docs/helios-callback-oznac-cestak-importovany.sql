/*
  Helios / MSSQL: oznaceni cestaku jako importovaneho v aplikaci.

  Spousti se az po uspesnem zalozeni hlavicky v dbo.TabICestak.
  Do @TabICestakId patri hodnota dbo.TabICestak.id.
  API ji prijme jako project.code a ulozi do travel_order.helios_document_id.
*/

DECLARE @ImportId uniqueidentifier = NULL; -- ImportId ze selectu cestaku k importu
DECLARE @CisDok nvarchar(20) = N'';        -- napr. CP-2026-0001, volitelne
DECLARE @TabICestakId int = NULL;          -- id zalozeneho radku dbo.TabICestak
DECLARE @TabIVozidloId int = NULL;         -- id zalozeneho/dohledaneho vozidla, pokud bylo pouzite

DECLARE @ApiUrl nvarchar(4000) = N'http://192.168.0.54:5055/api/helios/import-results';
DECLARE @ApiToken nvarchar(4000) = N'<DOPLNIT_HELIOS_IMPORT_API_TOKEN>';

IF @ApiToken = N'<DOPLNIT_HELIOS_IMPORT_API_TOKEN>'
  THROW 51100, 'Dopln @ApiToken.', 1;

IF @ImportId IS NULL
  THROW 51101, 'Dopln @ImportId ze selectu cestaku k importu.', 1;

IF @TabICestakId IS NULL
  THROW 51102, 'Dopln @TabICestakId po insertu do dbo.TabICestak.', 1;

DECLARE @Body nvarchar(max) = (
  SELECT
    CONVERT(nvarchar(36), @ImportId) AS importId,
    NULLIF(@CisDok, N'') AS orderNo,
    JSON_QUERY((
      SELECT CONVERT(nvarchar(30), @TabICestakId) AS code
      FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
    )) AS project,
    JSON_QUERY((
      SELECT CONVERT(nvarchar(30), @TabIVozidloId) AS id
      WHERE @TabIVozidloId IS NOT NULL
      FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
    )) AS vehicle
  FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
);

DECLARE @Http int;
DECLARE @HttpStatus int;
DECLARE @Response nvarchar(max);

BEGIN TRY
  EXEC sys.sp_OACreate 'MSXML2.ServerXMLHTTP.6.0', @Http OUT;
END TRY
BEGIN CATCH
  THROW 51103, 'SQL ucet nema pravo spustit sys.sp_OACreate, nebo neni povolena Ole Automation.', 1;
END CATCH;

EXEC sys.sp_OAMethod @Http, 'open', NULL, 'POST', @ApiUrl, false;
EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'Accept', 'application/json';
EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'Content-Type', 'application/json; charset=utf-8';
EXEC sys.sp_OAMethod @Http, 'setRequestHeader', NULL, 'X-Helios-Import-Token', @ApiToken;
EXEC sys.sp_OAMethod @Http, 'send', NULL, @Body;
EXEC sys.sp_OAGetProperty @Http, 'status', @HttpStatus OUT;
EXEC sys.sp_OAGetProperty @Http, 'responseText', @Response OUT;
EXEC sys.sp_OADestroy @Http;

SELECT
  @HttpStatus AS HttpStatus,
  @Response AS ApiResponse,
  @Body AS SentBody;

IF @HttpStatus NOT BETWEEN 200 AND 299
  THROW 51104, 'API callback pro oznaceni importu selhal.', 1;
