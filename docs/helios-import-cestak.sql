/*
  Import jednoho cestovniho prikazu z aplikace do Heliosu.

  Vstup:
    @ImportId = hodnota ze selectu dbo.vok_CPImportCestakyKImportu.ImportId
    @CisDok = cislo dokladu z rady Helios pro dbo.TabICestak.CisDok

  Poradi importu:
    1. zalozi / dohleda zakazku v dbo.TabZakazka
    2. dohleda vozidlo z ERP; pokud neni importovane z ERP a je pouzite auto,
       zalozi vozidlo v dbo.TabIVozidlo
    3. zalozi hlavicku cestaku v dbo.TabICestak
    4. zalozi useky v dbo.TabICestaUsek
    5. zalozi naklady v dbo.TabICestaNakl
    6. oznaci staging radek jako importovany

  Poznamka:
    Staging tabulka musi mit vyplneny sloupec PayloadJson.
    Doplnuje ho tools/sync_helios_import_queue.py z plneho API payloadu.
*/

SET XACT_ABORT ON;

DECLARE @ImportId uniqueidentifier = NULL; -- DOPLNIT z vybraneho radku v Heliosu
DECLARE @CisDok nvarchar(20) = NULL;       -- DOPLNIT z rady dokladu Heliosu
DECLARE @DryRun bit = 1;                   -- 1 = test s ROLLBACK, 0 = opravdu ulozit

DECLARE @Payload nvarchar(max);
DECLARE @OrderNo nvarchar(20);
DECLARE @HeliosCisDok nvarchar(20);
DECLARE @CisloZakazky nvarchar(15);
DECLARE @EmployeeNo int;
DECLARE @Stredisko nvarchar(30);
DECLARE @StagingIsActive bit = NULL;
DECLARE @StagingExportStatus nvarchar(30) = NULL;
DECLARE @StagingHeliosCestakId int = NULL;
DECLARE @Now datetime = getdate();
DECLARE @ZakazkaId int = NULL;
DECLARE @VozidloId int = NULL;
DECLARE @CestakId int = NULL;
DECLARE @VehicleHeliosId int = NULL;
DECLARE @VehiclePlate nvarchar(20);
DECLARE @VehiclePlateLookup nvarchar(20);
DECLARE @VehicleDescription nvarchar(100);
DECLARE @VehicleEvCislo nvarchar(20);
DECLARE @UsesVehicle bit = 0;
DECLARE @VehicleCreated bit = 0;
DECLARE @TotalKm decimal(19, 6) = 0;
DECLARE @BasicKmRate decimal(19, 6) = 0;
DECLARE @FuelKmRate decimal(19, 6) = 0;
DECLARE @FuelAmount decimal(19, 6) = 0;
DECLARE @MealAmount decimal(19, 6) = 0;
DECLARE @ExpensesAmount decimal(19, 6) = 0;
DECLARE @KmCompensationAmount decimal(19, 6) = 0;
DECLARE @TotalAmountPredZao decimal(19, 6) = 0;
DECLARE @TotalAmountRounded decimal(19, 6) = 0;

IF @ImportId IS NULL
  THROW 52000, 'Dopln @ImportId z dbo.vok_CPImportCestakyKImportu.', 1;

SET @HeliosCisDok = LEFT(LTRIM(RTRIM(COALESCE(@CisDok, N''))), 20);

IF COALESCE(@HeliosCisDok, N'') = N''
  THROW 52009, 'Dopln @CisDok - cislo dokladu z rady Helios pro TabICestak.CisDok.', 1;

SELECT
  @Payload = PayloadJson,
  @OrderNo = CisloCestovnihoPrikazu,
  @EmployeeNo = CisloZamestnance,
  @Stredisko = Stredisko,
  @StagingIsActive = IsActive,
  @StagingExportStatus = ExportStatus,
  @StagingHeliosCestakId = HeliosCestakId
FROM dbo.vok_CPImportCestaky WITH (UPDLOCK, HOLDLOCK)
WHERE ImportId = @ImportId;

IF @OrderNo IS NULL
  THROW 52011, 'ImportId neni ve staging tabulce dbo.vok_CPImportCestaky. Nejdriv spust synchronizaci seznamu k importu.', 1;

IF COALESCE(@StagingIsActive, 0) <> 1 OR @StagingHeliosCestakId IS NOT NULL OR @StagingExportStatus = N'exported'
  THROW 52012, 'Tento ImportId je ve stagingu oznaceny jako uz importovany. Pokud jsi cestak v Heliosu smazal, spust nejdriv reset skript helios-reset-cestak-pro-opakovany-import.sql.', 1;

IF @Payload IS NULL OR ISJSON(@Payload) <> 1
  THROW 52001, 'Staging radek nema platny PayloadJson. Nejdriv spust sync s plnym payloadem.', 1;

SET @OrderNo = COALESCE(NULLIF(JSON_VALUE(@Payload, '$.orderNo'), N''), @OrderNo);
SET @CisloZakazky = LEFT(@OrderNo, 15);
SET @EmployeeNo = COALESCE(TRY_CONVERT(int, JSON_VALUE(@Payload, '$.helios.headerValues.CisloZamestnance')), @EmployeeNo);
SET @Stredisko = COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.Stredisko'), N''), @Stredisko);
SET @VehicleHeliosId = TRY_CONVERT(int, NULLIF(JSON_VALUE(@Payload, '$.vehicle.heliosId'), N''));
SET @VehiclePlate = LEFT(COALESCE(NULLIF(JSON_VALUE(@Payload, '$.vehicle.plate'), N''), NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.SPZ'), N''), N''), 20);
SET @VehiclePlateLookup = LEFT(REPLACE(REPLACE(REPLACE(UPPER(@VehiclePlate), N' ', N''), N'-', N''), N'.', N''), 12);
SET @VehicleDescription = LEFT(COALESCE(NULLIF(JSON_VALUE(@Payload, '$.vehicle.brand'), N''), NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.SPZ'), N''), @VehiclePlate, N''), 100);
SET @UsesVehicle = CASE
  WHEN COALESCE(JSON_VALUE(@Payload, '$.helios.headerValues.TypDopravy'), N'') = N'S'
    AND COALESCE(@VehiclePlateLookup, N'') <> N''
  THEN 1 ELSE 0 END;

SET @TotalKm = COALESCE(
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.totals.totalKm')),
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.helios.headerValues.KMCelkem')),
  0
);
SET @BasicKmRate = COALESCE(
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.vehicle.basicKmRate')),
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.helios.headerValues.SazbaKM')),
  0
);
SET @FuelKmRate =
  (COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.vehicle.consumption')), 0) / 100.0)
    * COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.vehicle.fuelPrice')), 0)
  + (COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.vehicle.secondaryConsumption')), 0) / 100.0)
    * COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.vehicle.secondaryFuelPrice')), 0);
SET @KmCompensationAmount = ROUND(@TotalKm * @BasicKmRate, 2);
SET @FuelAmount = ROUND(@TotalKm * @FuelKmRate, 2);
SET @MealAmount = COALESCE(
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.totals.mealAmount')),
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.helios.headerValues.CelkemDiety')),
  0
);
SET @ExpensesAmount =
  COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.totals.lodgingAmount')), 0)
  + COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.totals.otherAmount')), 0);
SET @TotalAmountPredZao = COALESCE(
  TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.totals.grossAmount')),
  @MealAmount + @ExpensesAmount + @KmCompensationAmount + @FuelAmount,
  0
);
SET @TotalAmountRounded = ROUND(@TotalAmountPredZao, 0);

IF EXISTS (SELECT 1 FROM dbo.TabICestak WHERE CisDok = @HeliosCisDok)
  THROW 52002, 'Cestovni prikaz s timto CisDok uz v dbo.TabICestak existuje.', 1;

BEGIN TRY
  BEGIN TRANSACTION;

  /* 1. Zakazka */
  SELECT TOP (1) @ZakazkaId = ID
  FROM dbo.TabZakazka WITH (UPDLOCK, HOLDLOCK)
  WHERE Rada = N'CPR'
    AND CisloZakazky = @CisloZakazky;

  IF @ZakazkaId IS NULL
  BEGIN
    INSERT INTO dbo.TabZakazka (
      CisloZakazky,
      Nazev,
      DruhyNazev,
      Stredisko,
      DatumStartPlan,
      DatumStartReal,
      DatumKonecPlan,
      DatumKonecReal,
      Ukonceno,
      Stav,
      Priorita,
      Identifikator,
      CisloObjednavky,
      CisloNabidky,
      CisloSmlouvy,
      Upozorneni,
      VynosPlan,
      JeProjekt,
      JeServis,
      Autor,
      DatPorizeni,
      Rada,
      VerejnaZakazka,
      JeNovaVetaEditor,
      AVAReferenceID,
      AVAExternalID,
      AVAOutputFlag
    )
    VALUES (
      @CisloZakazky,
      LEFT(COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.zakazkaValues.Nazev'), N''), @OrderNo), 100),
      N'',
      @Stredisko,
      CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.zakazkaValues.DatumStartPlan')) AS datetime),
      CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.zakazkaValues.DatumStartReal')) AS datetime),
      CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.zakazkaValues.DatumKonecPlan')) AS datetime),
      CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.zakazkaValues.DatumKonecReal')) AS datetime),
      0,
      N'1',
      N'Normal',
      N'',
      N'',
      N'',
      N'',
      N'',
      0,
      0,
      0,
      N'CestovniPrikazy',
      @Now,
      N'CPR',
      0,
      0,
      LEFT(CONVERT(nvarchar(36), @ImportId), 40),
      N'',
      0
    );

    SET @ZakazkaId = SCOPE_IDENTITY();
  END;

  /* 2. Vozidlo: pouzij ERP vozidlo, existujici SPZ, nebo zaloz lokalni auto */
  IF @UsesVehicle = 1
  BEGIN
    IF @VehicleHeliosId IS NOT NULL
    BEGIN
      SELECT TOP (1) @VozidloId = id
      FROM dbo.TabIVozidlo
      WHERE id = @VehicleHeliosId;
    END;

    IF @VozidloId IS NULL
    BEGIN
      SELECT TOP (1) @VozidloId = id
      FROM dbo.TabIVozidlo WITH (UPDLOCK, HOLDLOCK)
      WHERE SPZVyhled = @VehiclePlateLookup;
    END;

    IF @VozidloId IS NULL
    BEGIN
      SELECT @VehicleEvCislo = CONVERT(nvarchar(20), COALESCE(MAX(TRY_CONVERT(int, EvCislo)), 2999999) + 1)
      FROM dbo.TabIVozidlo WITH (UPDLOCK, HOLDLOCK)
      WHERE TRY_CONVERT(int, EvCislo) BETWEEN 3000000 AND 3099999;

      IF TRY_CONVERT(int, @VehicleEvCislo) NOT BETWEEN 3000000 AND 3100000
        THROW 52010, 'Nelze pridelit evidencni cislo vozidla v rozsahu 3000000-3100000.', 1;

      INSERT INTO dbo.TabIVozidlo (
        SPZZobraz,
        TazneVozidlo,
        SPZVyhled,
        EvCislo,
        Popis,
        SledovKM,
        SledovMTH,
        DatPorizeni,
        Rozliseni,
        Stredisko,
        CisloRidic,
        TPTovZnacka,
        Objem,
        CisPojSml,
        CisLeasSml,
        CisZakSml,
        PorizCena,
        SDPar12,
        SDCelkem,
        SDZal1,
        SDZal2,
        SDZal3,
        SDZal4,
        SDDoplatek,
        SDRok,
        SDMPQ1,
        SDMPQ2,
        SDMPQ3,
        SDMPQ4,
        SDMPQ5,
        SDMOQ1,
        SDMOQ2,
        SDMOQ3,
        SDMOQ4,
        SDMOQ5,
        SDPar6proc,
        SDPar6Kc,
        SDPar3Kc,
        SDRokBez6,
        Koef1,
        Koef2,
        Koef3,
        Stav,
        Autor,
        Elektromobil,
        AltPohon,
        CisloZakazky,
        TLM,
        JeNovaVetaEditor,
        InicMesProvozu,
        AVAReferenceID,
        AVAExternalID
      )
      VALUES (
        LEFT(@VehiclePlate, 12),
        N'A',
        @VehiclePlateLookup,
        @VehicleEvCislo,
        @VehicleDescription,
        N'A',
        N'N',
        @Now,
        N'E',
        @Stredisko,
        @EmployeeNo,
        LEFT(@VehicleDescription, 30),
        TRY_CONVERT(int, NULLIF(JSON_VALUE(@Payload, '$.vehicle.engineVolume'), N'')),
        N'',
        N'',
        N'',
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        1,
        0,
        N'CestovniPrikazy',
        CASE WHEN JSON_VALUE(@Payload, '$.vehicle.fuelType') = N'electricity' THEN 1 ELSE 0 END,
        CASE WHEN NULLIF(JSON_VALUE(@Payload, '$.vehicle.secondaryFuelType'), N'') IS NOT NULL THEN 1 ELSE 0 END,
        @CisloZakazky,
        0,
        0,
        1,
        LEFT(CONVERT(nvarchar(36), @ImportId), 40),
        N''
      );

      SET @VozidloId = SCOPE_IDENTITY();
      SET @VehicleCreated = 1;
    END;
  END;

  /* 3. Hlavicka cestaku */
  INSERT INTO dbo.TabICestak (
    CisloZamestnance,
    CisDok,
    DatVystDokl,
    Stav,
    CilCesty,
    UcelCesty,
    DatCasPocatek,
    DatCasKonec,
    CisloZakazky,
    TypDopravy,
    SPZ,
    Spotreba,
    CenaL,
    SazbaKM,
    SDPlati,
    ProcKapes,
    PHMZahrpo,
    PHMKc,
    CelkemDiety,
    CelkemDietyZak,
    CelkemNaklady,
    CelkemNahrady,
    CelkemPHM,
    CelkemKc,
    CelkemKCZak,
    CelkemKcPredZao,
    CelkemKcZakPredZao,
    KMCelkem,
    KMZahr,
    TypCesty,
    idVozidlo,
    VratkaTuz,
    Stredisko,
    idrada,
    Autor,
    DatPorizeni,
    MenaPrepocet,
    KurzPrepocet,
    FixKurz,
    JeNovaVetaEditor,
    CestakJakHledatKurz,
    ZpusobKurzu
  )
  VALUES (
    @EmployeeNo,
    @HeliosCisDok,
    COALESCE(CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.headerValues.DatVystDokl')) AS datetime), @Now),
    COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.Stav'), N''), N'O'),
    LEFT(COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.CilCesty'), N''), N''), 60),
    COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.UcelCesty'), N''), N''),
    CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.headerValues.DatCasPocatek')) AS datetime),
    CAST(TRY_CONVERT(datetimeoffset(0), JSON_VALUE(@Payload, '$.helios.headerValues.DatCasKonec')) AS datetime),
    @CisloZakazky,
    COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.TypDopravy'), N''), N'J'),
    NULLIF(@VehiclePlate, N''),
    TRY_CONVERT(decimal(19, 6), NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.Spotreba'), N'')),
    TRY_CONVERT(decimal(19, 6), NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.CenaL'), N'')),
    @BasicKmRate,
    N'O',
    0,
    0,
    @FuelAmount,
    @MealAmount,
    @MealAmount,
    @ExpensesAmount,
    @KmCompensationAmount,
    @FuelAmount,
    @TotalAmountRounded,
    @TotalAmountRounded,
    @TotalAmountPredZao,
    @TotalAmountPredZao,
    @TotalKm,
    COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.helios.headerValues.KMZahr')), 0),
    COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.TypCesty'), N''), N'T'),
    @VozidloId,
    1,
    @Stredisko,
    15,
    N'CestovniPrikazy',
    @Now,
    COALESCE(NULLIF(JSON_VALUE(@Payload, '$.helios.headerValues.MenaPrepocet'), N''), N'CZK'),
    COALESCE(TRY_CONVERT(decimal(19, 6), JSON_VALUE(@Payload, '$.helios.headerValues.KurzPrepocet')), 1),
    0,
    0,
    1,
    0
  );

  SET @CestakId = SCOPE_IDENTITY();

  /* 4. Useky */
  IF EXISTS (
    SELECT 1
    FROM OPENJSON(@Payload, '$.routeLines')
    WITH (
      DatCasPocatekText nvarchar(50) '$.startAt',
      DatCasKonecText nvarchar(50) '$.endAt',
      odkud nvarchar(100) '$.from',
      kam nvarchar(100) '$.to',
      Stravne decimal(19, 6) '$.mealAmount',
      Hod1 decimal(19, 6) '$.calculatedHours',
      TotalAmount decimal(19, 6) '$.totalAmount'
    ) line
    CROSS APPLY (
      SELECT
        CAST(TRY_CONVERT(datetimeoffset(0), line.DatCasPocatekText) AS datetime) AS DatCasPocatek,
        CAST(TRY_CONVERT(datetimeoffset(0), line.DatCasKonecText) AS datetime) AS DatCasKonec
    ) parsed
    WHERE parsed.DatCasPocatek IS NOT NULL
      AND parsed.DatCasKonec IS NULL
      AND (
        NULLIF(line.odkud, N'') IS NOT NULL
        OR NULLIF(line.kam, N'') IS NOT NULL
        OR COALESCE(line.Stravne, 0) <> 0
        OR COALESCE(line.Hod1, 0) <> 0
        OR COALESCE(line.TotalAmount, 0) <> 0
      )
  )
    THROW 51000, N'Nektery radek vyuctovani ma vyplneny zacatek, ale chybi konec. Dopln cas prijezdu/ukonceni useku a spust import znovu.', 1;

  INSERT INTO dbo.TabICestaUsek (
    idCestak,
    Autor,
    DatPorizeni,
    TypUseku,
    DatCasPocatek,
    DatCasKonec,
    odkud,
    kam,
    Mena,
    Stravne,
    CelkemStravne,
    CelkemKC,
    Dny,
    Hod1,
    Hod2,
    ProcStrav,
    ZpusobKurzu,
    CisloZakazky,
    Stredisko,
    Snidane,
    Obed,
    Vecere,
    RucProc
  )
  SELECT
    @CestakId,
    N'CestovniPrikazy',
    @Now,
    COALESCE(NULLIF(TypUseku, N''), N'T'),
    parsed.DatCasPocatek,
    parsed.DatCasKonec,
    LEFT(COALESCE(odkud, N''), 100),
    LEFT(COALESCE(kam, N''), 100),
    COALESCE(Mena, N'CZK'),
    COALESCE(Stravne, 0),
    COALESCE(CelkemStravne, Stravne, 0),
    COALESCE(CelkemKC, Stravne, 0),
    0,
    COALESCE(Hod1, 0),
    0,
    COALESCE(ProcStrav, 0),
    0,
    @CisloZakazky,
    @Stredisko,
    0,
    0,
    0,
    CASE WHEN COALESCE(FreeMeals, 0) = 0 THEN 1 ELSE 0 END
  FROM OPENJSON(@Payload, '$.routeLines')
  WITH (
    SequenceNo int '$.sequenceNo',
    TypUseku nchar(1) '$.helios.values.TypUseku',
    DatCasPocatekText nvarchar(50) '$.startAt',
    DatCasKonecText nvarchar(50) '$.endAt',
    odkud nvarchar(100) '$.from',
    kam nvarchar(100) '$.to',
    Mena nvarchar(3) '$.helios.values.Mena',
    Stravne decimal(19, 6) '$.mealAmountForeign',
    CelkemStravne decimal(19, 6) '$.mealAmountForeign',
    CelkemKC decimal(19, 6) '$.mealAmount',
    Hod1 decimal(19, 6) '$.calculatedHours',
    ProcStrav decimal(19, 6) '$.helios.values.ProcStrav',
    FreeMeals int '$.freeMeals'
  )
  CROSS APPLY (
    SELECT
      CAST(TRY_CONVERT(datetimeoffset(0), DatCasPocatekText) AS datetime) AS DatCasPocatek,
      CAST(TRY_CONVERT(datetimeoffset(0), DatCasKonecText) AS datetime) AS DatCasKonec
  ) parsed
  WHERE parsed.DatCasPocatek IS NOT NULL
    AND parsed.DatCasKonec IS NOT NULL
  ORDER BY SequenceNo;

  /* 5. Naklady z radku vyuctovani a dokladu */
  ;WITH line_expenses AS (
    SELECT
      CAST(TRY_CONVERT(datetimeoffset(0), line.StartAtText) AS datetime) AS Datum,
      expense.idNaklKod,
      expense.Popis,
      COALESCE(NULLIF(line.Mena, N''), N'CZK') AS Mena,
      CAST(1 AS decimal(19, 6)) AS Kurz,
      expense.Castka AS CenaVal,
      expense.Castka AS CenaKc
    FROM OPENJSON(@Payload, '$.routeLines')
    WITH (
      SequenceNo int '$.sequenceNo',
      StartAtText nvarchar(50) '$.startAt',
      Odkud nvarchar(100) '$.from',
      Kam nvarchar(100) '$.to',
      Mena nvarchar(3) '$.helios.values.Mena',
      FareAmount decimal(19, 6) '$.fareAmount',
      LodgingAmount decimal(19, 6) '$.lodgingAmount',
      OtherAmount decimal(19, 6) '$.otherAmount'
    ) line
    CROSS APPLY (VALUES
      (6, N'Jizdne ' + COALESCE(line.Odkud, N'') + N' - ' + COALESCE(line.Kam, N''), line.FareAmount),
      (1, N'Ubytovani ' + COALESCE(line.Kam, N''), line.LodgingAmount),
      (17, N'Ostatni vydaj ' + COALESCE(line.Kam, N''), line.OtherAmount)
    ) expense(idNaklKod, Popis, Castka)
    WHERE COALESCE(expense.Castka, 0) <> 0
  ),
  attachment_expenses AS (
    SELECT
      COALESCE(TRY_CONVERT(datetime, DocumentDateText), @Now) AS Datum,
      COALESCE(HeliosExpenseCode, 17) AS idNaklKod,
      LEFT(COALESCE(NULLIF(Description, N''), FileName, N'Doklad'), 255) AS Popis,
      COALESCE(NULLIF(CurrencyCode, N''), NULLIF(JSON_VALUE(@Payload, '$.trip.currencyCode'), N''), N'CZK') AS Mena,
      CASE
        WHEN COALESCE(NULLIF(CurrencyCode, N''), NULLIF(JSON_VALUE(@Payload, '$.trip.currencyCode'), N''), N'CZK') = N'CZK' THEN 1
        ELSE COALESCE(NULLIF(ExchangeRate, 0), 1)
      END AS Kurz,
      Amount AS CenaVal,
      COALESCE(
        AmountCzk,
        Amount * CASE
          WHEN COALESCE(NULLIF(CurrencyCode, N''), NULLIF(JSON_VALUE(@Payload, '$.trip.currencyCode'), N''), N'CZK') = N'CZK' THEN 1
          ELSE COALESCE(NULLIF(ExchangeRate, 0), 1)
        END
      ) AS CenaKc
    FROM OPENJSON(@Payload, '$.attachments')
    WITH (
      HeliosExpenseCode int '$.heliosExpenseCode',
      Description nvarchar(255) '$.description',
      FileName nvarchar(255) '$.fileName',
      DocumentDateText nvarchar(50) '$.documentDate',
      Amount decimal(19, 6) '$.amount',
      CurrencyCode nvarchar(3) '$.currencyCode',
      ExchangeRate decimal(19, 6) '$.exchangeRate',
      AmountCzk decimal(19, 6) '$.amountCzk'
    )
    WHERE COALESCE(Amount, 0) <> 0
  )
  INSERT INTO dbo.TabICestaNakl (
    idCestak,
    Datum,
    DatumKurz,
    idNaklKod,
    Popis,
    Mena,
    Kurz,
    CenaVal,
    CenaKc,
    JednotkaMeny,
    ZpusobKurzu,
    KurzPrepocet,
    CisloZakazky,
    Stredisko,
    CenaKcBezDPH,
    CenaValBezDPH,
    FixKurz
  )
  SELECT
    @CestakId,
    COALESCE(Datum, @Now),
    COALESCE(Datum, @Now),
    idNaklKod,
    Popis,
    Mena,
    Kurz,
    CenaVal,
    CenaKc,
    1,
    0,
    Kurz,
    @CisloZakazky,
    @Stredisko,
    CenaKc,
    CenaVal,
    0
  FROM (
    SELECT * FROM line_expenses
    UNION ALL
    SELECT * FROM attachment_expenses
  ) expenses;

  /* 6. Staging oznaceni */
  UPDATE dbo.vok_CPImportCestaky
  SET ImportStartedAt = COALESCE(ImportStartedAt, @Now),
      ImportFinishedAt = getdate(),
      HeliosCestakId = @CestakId,
      ExportStatus = N'exported',
      ImportError = NULL,
      IsActive = 0
  WHERE ImportId = @ImportId;

  IF @DryRun = 1
  BEGIN
    ROLLBACK TRANSACTION;
    SELECT
      @ImportId AS ImportId,
      @OrderNo AS CisloCestovnihoPrikazu,
      @HeliosCisDok AS CisDokHelios,
      @ZakazkaId AS TabZakazkaId,
      @VozidloId AS TabIVozidloId,
      @VehicleEvCislo AS VozidloEvCislo,
      @VehicleCreated AS VozidloZalozeno,
      @CestakId AS TabICestakId,
      N'DRY RUN - rollback proveden' AS StavImportu;
  END
  ELSE
  BEGIN
    COMMIT TRANSACTION;
    SELECT
      @ImportId AS ImportId,
      @OrderNo AS CisloCestovnihoPrikazu,
      @HeliosCisDok AS CisDokHelios,
      @ZakazkaId AS TabZakazkaId,
      @VozidloId AS TabIVozidloId,
      @VehicleEvCislo AS VozidloEvCislo,
      @VehicleCreated AS VozidloZalozeno,
      @CestakId AS TabICestakId,
      N'Import dokoncen' AS StavImportu;
  END;
END TRY
BEGIN CATCH
  IF @@TRANCOUNT > 0
    ROLLBACK TRANSACTION;

  UPDATE dbo.vok_CPImportCestaky
  SET ImportError = ERROR_MESSAGE(),
      ImportStartedAt = COALESCE(ImportStartedAt, @Now)
  WHERE ImportId = @ImportId;

  THROW;
END CATCH;
