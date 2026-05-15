/*
  Uprava procedury pro import jizd - pridava soukrome jizdy mezi sluzebnimi jízdami.

  Helios potrebuje kompletni zaznamy vcetne soukromych useku (cesta domu/zpet).

  Priklad:
    Data z aplikace (3 jizdy):
      1. Sluzebni 12.5. 7:00-22:00 Brezi -> Zlin
      2. Sluzebni 16.5. 8:00-18:00 Brezi -> Brno
      3. Sluzebni 20.5. 6:00-21:00 Brezi -> Ostrava

    Import do Heliosu (6 jizd):
      1. Sluzebni 12.5. 7:00 Brezi -> Zlin
      2. Soukroma 12.5. 22:00 (cesta domu)
      3. Sluzebni 16.5. 8:00 Brezi -> Brno
      4. Soukroma 16.5. 18:00 (cesta domu)
      5. Sluzebni 20.5. 6:00 Brezi -> Ostrava
      6. Soukroma 20.5. 21:00 (cesta domu)
*/

-- Nejprve musime upravit cast, kde se vkladaji jizdy do TabICestaUsek
-- Tim, ze mezi kazdou sluzebni jizdu vlozime i soukromou jizdu

-- Tato uprava se tyka radku cca 520-567 v puvodni procedure
-- Musime zmenit INSERT INTO TabICestaUsek, aby pouzival CTE s rozsirenym seznamem jizd

-- Zde je upravena cast INSERT INTO TabICestaUsek:

INSERT INTO dbo.TabICestaUsek (
  [idcestak], [Autor], [DatPorizeni], [TypUseku], [DatCasPocatek], [DatCasKonec],
  [odkud], [kam], [Mena], [Stravne], [CelkemStravne], [CelkemKC],
  [PHMZahrpo], [Hod1], [Hod2], [ProcStrav], [RucProc], [CisloZakazky],
  [Stredisko], [Obed], [Vecere], [Snidane], [Dny]
)
SELECT
  @CestakId,
  N'CestovniPrikazy',
  @Now,
  expanded.TypUseku,
  expanded.DatCasPocatek,
  expanded.DatCasKonec,
  LEFT(COALESCE(expanded.odkud, N''), 100),
  LEFT(COALESCE(expanded.kam, N''), 100),
  COALESCE(expanded.Mena, N'CZK'),
  COALESCE(expanded.Stravne, 0),
  COALESCE(expanded.CelkemStravne, expanded.Stravne, 0),
  COALESCE(expanded.CelkemKC, expanded.Stravne, 0),
  0,
  COALESCE(expanded.Hod1, 0),
  0,
  COALESCE(expanded.ProcStrav, 0),
  0,
  @CisloZakazky,
  @Stredisko,
  0,
  0,
  0,
  CASE WHEN COALESCE(expanded.FreeMeals, 0) = 0 THEN 1 ELSE 0 END
FROM (
  -- Sluzebni jizdy z aplikace
  SELECT
    SequenceNo * 2 - 1 AS SortOrder, -- 1, 3, 5, 7...
    COALESCE(NULLIF(TypUseku, N''), N'T') AS TypUseku,
    parsed.DatCasPocatek,
    parsed.DatCasKonec,
    odkud,
    kam,
    Mena,
    Stravne,
    CelkemStravne,
    CelkemKC,
    Hod1,
    ProcStrav,
    FreeMeals
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

  UNION ALL

  -- Soukrome jizdy (cesta domu po kazde sluzebni jizde)
  SELECT
    SequenceNo * 2 AS SortOrder, -- 2, 4, 6, 8...
    N'S' AS TypUseku, -- S = Soukromá
    parsed.DatCasKonec AS DatCasPocatek, -- Zacina koncem sluzebni jizdy
    NULL AS DatCasKonec, -- Konec neni specifikovan
    kam AS odkud, -- Odkud = kam sluzebni jizdy (otevrena logika)
    NULL AS kam, -- Kam neni specifikovano
    NULL AS Mena,
    0 AS Stravne,
    0 AS CelkemStravne,
    0 AS CelkemKC,
    0 AS Hod1,
    0 AS ProcStrav,
    0 AS FreeMeals
  FROM OPENJSON(@Payload, '$.routeLines')
  WITH (
    SequenceNo int '$.sequenceNo',
    DatCasKonecText nvarchar(50) '$.endAt',
    kam nvarchar(100) '$.to'
  )
  CROSS APPLY (
    SELECT
      CAST(TRY_CONVERT(datetimeoffset(0), DatCasKonecText) AS datetime) AS DatCasKonec
  ) parsed
  WHERE parsed.DatCasKonec IS NOT NULL
) expanded
ORDER BY expanded.SortOrder;

/*
  POZNAMKA: Tento SQL snippet je nutné vlozit do puvodni procedury
  dbo.vok_CPImportCestak misto staveho INSERT INTO TabICestaUsek
  (radky cca 520-567).

  Zbytek procedury zustava stejny.
*/
