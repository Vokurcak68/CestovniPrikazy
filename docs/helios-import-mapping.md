# Helios import cestovnich prikazu

## Nalezene tabulky v Heliosu

Jadro modulu cestovnich prikazu v Heliosu:

- `dbo.TabICestak` - hlavicka cestovniho prikazu
- `dbo.TabICestaUsek` - useky / dny vyuctovani cesty
- `dbo.TabICestaNakl` - naklady k cestovnimu prikazu
- `dbo.TabZakazka` - zakazka pro prenos cestovnich prikazu, pred insert hlavicky
- `dbo.TabIVozidlo` - vozidla
- `dbo.TabCisZam` - zamestnanci, vazba pres `Cislo`
- `dbo.TabDokumenty`, `dbo.TabDokumVazba` - dokumenty a vazby dokumentu

Overene vazby:

- `TabICestaUsek.idCestak -> TabICestak.id`
- `TabICestaNakl.idCestak -> TabICestak.id`
- `TabICestak.idVozidlo -> TabIVozidlo.id`
- `TabIVozidlo.CisloRidic -> TabCisZam.Cislo`
- `TabZakazka.Stredisko -> TabStrom.Cislo`
- `TabZakazka.Zodpovida -> TabCisZam.Cislo`
- `Stredisko` v hlavicce/useku/nakladu/vozidle vede na `TabStrom.Cislo`

## Observovane hodnoty v Heliosu

- `TabICestak.Stav`: `O` = otevreny/neexportovany, `U` = uzavreny/zaexportovany do pokladny nebo dalsi agendy.
- `TabICestak.TypCesty`: `T` = tuzemska, `Z` = zahranicni.
- `TabICestaUsek.TypUseku`: `T` = tuzemsky, `Z` = zahranicni, `S` = soukromy.
- `TabICestak.TypDopravy`: pozorovano `S`, `A`, `V`, `J`; pro vlastni/sluzebni vozidlo navrhuji `S`, pro verejnou dopravu `V`, pro ostatni `J`.
- `TabICestaNakl.idNaklKod`: `1` ubytovani, `2` PHM, `5` parkovne, `6` jizdne vlak/BUS, `10` obcerstveni/stravovani, `11` taxi, `12` dalnicni/silnicni poplatek, `17` ostatni/vstupenka.

## Navrh mapovani

### Zakazka `TabZakazka`

Pred zalozenim hlavicky cestovniho prikazu se v Heliosu musi zajistit zakazka:

- hledat podle `Rada = 'CPR'` a `CisloZakazky = travel_order.order_no`
- pokud neexistuje, zalozit novy radek do `TabZakazka`
- cislo cestovniho prikazu musi byt maximalne 15 znaku, protoze `TabZakazka.CisloZakazky` je `nvarchar(15)`

Zakladni mapovani:

| Aplikace | Helios |
| --- | --- |
| konstanta | `Rada = CPR` |
| `travel_order.order_no` | `CisloZakazky` |
| `purpose` / `order_no` | `Nazev` |
| `cost_center_code` | `Stredisko` |
| `planned_start_at` | `DatumStartPlan`, `DatumStartReal` |
| `planned_end_at` | `DatumKonecPlan`, `DatumKonecReal` |
| konstanta | `Ukonceno = 0` |
| konstanta | `Stav = 1` |
| konstanta | `Priorita = Normal` |
| konstanta | `VynosPlan = 0` |
| konstanta | `JeProjekt = 0`, `JeServis = 0`, `VerejnaZakazka = 0` |
| `travel_order.id` | `AVAReferenceID` |
| konstanta | `AVAExternalID = ''`, `AVAOutputFlag = 0` |

Povinna prazdna pole pri insertu: `DruhyNazev`, `Identifikator`, `CisloObjednavky`, `CisloNabidky`, `CisloSmlouvy`, `Upozorneni`.

### Hlavicka `TabICestak`

| Aplikace | Helios |
| --- | --- |
| `travel_order.order_no` | `CisDok` |
| `employee_profile.personal_number` | `CisloZamestnance` |
| `approved_at` nebo `updated_at` | `DatVystDokl`, `DatPorizeni` |
| `planned_start_at` | `DatCasPocatek` |
| `planned_end_at` | `DatCasKonec` |
| `destination` | `CilCesty` |
| `purpose` | `UcelCesty` |
| `cost_center_code` | `Stredisko` |
| `travel_order.order_no` | `CisloZakazky` |
| existuje zahranicni usek | `TypCesty = Z`, jinak `T` |
| doprava vlastni/sluzebni auto | `TypDopravy = S` |
| verejna doprava | `TypDopravy = V` |
| jina doprava | `TypDopravy = J` |
| vozidlo SPZ | `SPZ` |
| spotreba vozidla | `Spotreba` |
| cena PHM | `CenaL` |
| zakladni sazba / km | `SazbaKM` |
| vypocet PHM | `PHMKc`, `CelkemPHM` |
| `total_km` | `KMCelkem` |
| soucet zahranicnich km | `KMZahr` |
| stravne celkem | `CelkemDiety` |
| ubytovani + ostatni vydaje | `CelkemNaklady` |
| cestovne / nahrady | `CelkemNahrady` |
| castka celkem | `CelkemPrepocet` |

Povinne hodnoty doplnovane konstantou: `Autor`, `VratkaTuz = 1`, `FixKurz = 0`, `JeNovaVetaEditor = 0`, `CestakJakHledatKurz = 1`, `ZpusobKurzu = 0`.

### Useky `TabICestaUsek`

| Aplikace | Helios |
| --- | --- |
| hlavicka po insertu | `idCestak` |
| `route_line.segment_type` | `TypUseku`: `domestic -> T`, `foreign -> Z`, `private -> S` |
| `start_at` | `DatCasPocatek` |
| `end_at` | `DatCasKonec` |
| `from_place` | `odkud` |
| `to_place` | `kam` |
| `currency_code` | `Mena` |
| `calculated_meal_amount` | `Stravne`, `CelkemStravne`, `CelkemKC` |
| `calculated_hours` | `Hod1` |
| `mealReduction / mealBase` | `ProcStrav` |
| `cost_center_code` | `Stredisko` |
| `travel_order.order_no` | `CisloZakazky` |

Otevreny bod: aplikace ma zatim jen pocet jidel zdarma, Helios ma samostatne `Snidane`, `Obed`, `Vecere`. Pro presny import je lepsi upravit UI na tri checkboxy; jinak se da prenest jen vysledek kraceni pres `ProcStrav`.

### Naklady `TabICestaNakl`

Navrhuji generovat naklady z financnich poli a doklady pouzit jako prilohy/validaci:

| Aplikace | Helios |
| --- | --- |
| hlavicka po insertu | `idCestak` |
| vazba na usek, pokud ji budeme drzet | `idUsek` |
| datum dokladu / zacatek useku | `Datum` |
| druh vydaje | `idNaklKod` |
| popis vydaje/dokladu | `Popis` |
| mena | `Mena` |
| castka | `CenaKc`, `CenaVal`, `CenaKcBezDPH` |
| `travel_order.order_no` | `CisloZakazky` |
| `cost_center_code` | `Stredisko` |

Mapovani druhu vydaju: `lodging -> 1`, `fuel -> 2`, `parking -> 5`, `fare -> 6`, `meal -> 10`, `other -> 17`.

### Dokumenty

Doklady z aplikace jsou dnes v `travel.travel_attachment`. Pro Helios je vhodny dalsi krok:

- nahrat binarni soubor do `TabDokumenty`
- vytvorit vazbu v `TabDokumVazba` na `TabICestak.id`
- zachovat SHA256 a puvodni nazev souboru pro dohledatelnost

## Hotovy API vyber

Endpoint:

```http
GET /api/helios/import-candidates?limit=100
```

Vyber:

- jen `travel_order.status = approved`
- jen zaznamy bez `helios_document_id`
- jen zaznamy, kde `export_status <> exported`
- jen cestovni prikazy schvalene jinym uzivatelem nez zadatelem
- jen zaznamy s osobnim cislem overenym synchronizaci z ERP: ciselne `employee_profile.personal_number`, vyplnene `helios_employee_id`, vyplnene `last_synced_at` a shoda s `app_user.helios_personal_number`

Autorizace:

- bud prihlaseny uzivatel s roli `admin` nebo `accountant`
- nebo hlavicka `X-Helios-Import-Token`, pokud bude na serveru nastavena promenna `HELIOS_IMPORT_API_TOKEN`

Endpoint vraci seznam polozek s bloky `employee`, `trip`, `zakazka`, `totals`, `routeLines`, `attachments`, `helios.zakazkaValues` a `helios.headerValues`.

## Dalsi krok

Pred ostrym insertem do Heliosu jeste doplnit:

- potvrzeni hodnot `TypDopravy` pro `A`, `V`, `J`
- pravidlo pro `idRada` a cislovani `CisDok`, pokud Helios nechce prevzit cislo z aplikace
- potvrzeni, zda `TabZakazka.Stav = 1` a `Priorita = Normal` plati i pro radu `CPR`
- presny insert dokumentu do `TabDokumenty` a `TabDokumVazba`
- callback API po zalozeni hlavicky: `POST /api/helios/import-results`
  - vstup: `importId`, volitelne `orderNo`, a `project.code = TabICestak.id`
  - aplikace ulozi `project.code` do `travel_order.helios_document_id`, nastavi `helios_exported_at` a `export_status = exported`
  - dalsi volani `GET /api/helios/import-candidates` uz takovy cestak nevrati
