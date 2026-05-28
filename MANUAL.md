# Uživatelský manuál - Aplikace Cestovní příkazy

**Verze:** 1.2
**Datum:** 27. 5. 2026
**Organizace:** Oresi United Kitchens

---

## Obsah

1. [Přehled aplikace](#1-přehled-aplikace)
2. [Začínáme – registrace, přihlášení a profil](#2-začínáme--registrace-přihlášení-a-profil)
   - [2.1 Registrace nového účtu](#21-registrace-nového-účtu)
   - [2.2 Přihlášení](#22-přihlášení)
   - [2.3 Nastavení profilu](#23-nastavení-profilu-první-přihlášení)
   - [2.4 Synchronizace profilu s Heliosem](#24-synchronizace-profilu-s-heliosem-erp)
   - [2.5 Přidání vozidla](#25-přidání-vozidla)
3. [Pro zaměstnance](#3-pro-zaměstnance)
4. [Pro schvalovatele](#4-pro-schvalovatele)
5. [Pro účetní](#5-pro-účetní)
6. [Pro administrátory](#6-pro-administrátory)
7. [Stavy cestovních příkazů](#7-stavy-cestovních-příkazů)
8. [Vyhledávání a filtrování](#8-vyhledávání-a-filtrování)
9. [Často kladené otázky](#9-často-kladené-otázky)

---

## 1. Přehled aplikace

### 1.1 Co je to aplikace Cestovní příkazy?

Aplikace Cestovní příkazy je webová aplikace pro správu služebních cest zaměstnanců. Umožňuje:

- Vytváření žádostí o vycestování
- Schvalování žádostí nadřízenými
- Zakládání cestovních příkazů ze schválených žádostí
- Vyúčtování nákladů na služební cestu (tuzemskou i zahraniční)
- Export dat do účetního systému Helios

### 1.2 Hlavní rozhraní

Po přihlášení uvidíte:

- **Horní lišta** - navigace mezi sekcemi aplikace
- **Levý panel** - seznam cestovních příkazů/žádostí
- **Hlavní panel** - detail vybraného příkazu/žádosti
- **Ikony nápovědy (?)** - klikněte pro zobrazení kontextové nápovědy

### 1.3 Kontextová nápověda

U většiny polí formuláře je ikona **?** (otazník). Kliknutím se zobrazí vysvětlení k danému poli. Nápovědu lze zavřít kliknutím mimo panel nebo na tlačítko zavřít.

### 1.4 Oznámení (notifikace)

Aplikace zobrazuje barevná oznámení (tzv. toast notifikace) v rohu obrazovky:
- **Zelené** - úspěšná akce
- **Modré** - informace
- **Oranžové** - varování
- **Červené** - chyba

Oznámení zmizí automaticky po 5 sekundách nebo je lze zavřít ručně kliknutím na **×**.

---

## 2. Začínáme – registrace, přihlášení a profil

### 2.1 Registrace nového účtu

Pokud ještě nemáte přístup do aplikace, musíte si vytvořit účet.

1. Otevřete aplikaci v prohlížeči
2. Na přihlašovací obrazovce klikněte na **Vytvořit účet**
3. Vyplňte registrační formulář:
   - **Jméno** - vaše celé jméno (zobrazuje se ostatním uživatelům)
   - **E-mail** - bude sloužit jako přihlašovací jméno
   - **Heslo** - minimálně 8 znaků
   - **Heslo znovu** - zopakujte heslo pro ověření
4. Klikněte na **Registrovat**

Po úspěšné registraci:
- Obdržíte e-mail s ověřovacím odkazem
- Klikněte na odkaz v e-mailu pro aktivaci účtu
- Teprve po aktivaci se lze přihlásit

**Upozornění:** Bez kliknutí na ověřovací odkaz nelze účet použít. Zkontrolujte i složku Spam.

**Tip:** Pokud vám administrátor vytvořil účet přímo v systému, registraci přeskočte – přihlaste se e-mailem a heslem, které vám sdělil.

### 2.2 Přihlášení

1. Otevřete aplikaci v prohlížeči
2. Zadejte svůj **e-mail** (přihlašovací jméno)
3. Zadejte **heslo**
4. Klikněte na **Přihlásit**

Pokud zadáte špatné přihlašovací údaje, zobrazí se chybová zpráva. Zkontrolujte e-mail a heslo. Pokud heslo neznáte, kontaktujte administrátora aplikace.

### 2.3 Nastavení profilu (první přihlášení)

Po prvním přihlášení je důležité vyplnit svůj profil. Bez správně vyplněného profilu nelze vytvářet cestovní příkazy.

1. Klikněte na **Profil** v horní liště (ikona osoby)
2. Vyplňte osobní údaje:
   - **Jméno** - celé jméno jak se zobrazí na příkazech
   - **E-mail** - kontaktní e-mail (předvyplněn z registrace)
   - **Osobní číslo** - evidenční číslo zaměstnance (nutné pro synchronizaci s Heliosem)
   - **Středisko – kód** - kód organizační jednotky
   - **Středisko – název** - název organizační jednotky
   - **Útvar** - název útvaru
   - **Telefon** - kontaktní telefon
   - **Pracovní doba od / do** - výchozí pracovní hodiny (používají se pro výpočet stravného)
   - **Výchozí doprava** - předvyplní se automaticky při vytváření nových úseků trasy
   - **Bydliště** - adresa bydliště (používá se jako výchozí místo odjezdu)

3. Nastavte **výchozího schvalovatele**:
   - Ze seznamu vyberte svého přímého nadřízeného
   - Tento schvalovatel se automaticky předvyplní do každé nové žádosti

4. Klikněte na **Uložit profil**

**Tip:** Všechna pole profilu lze kdykoli změnit. Změny se projeví až v nově vytvořených příkazech, nikoliv v již odeslaných.

### 2.4 Synchronizace profilu s Heliosem (ERP)

Pokud vaše firma používá Helios, lze osobní údaje, středisko a vozidla načíst automaticky.

**Podmínka:** Musí být vyplněno vaše **Osobní číslo** v profilu – podle něj aplikace hledá záznamy v Heliosu.

Postup synchronizace:

1. Přejděte do **Profilu**
2. Klikněte na **Synchronizace s ERP**
3. Aplikace načte z Heliosu:
   - Jméno, osobní číslo, středisko, útvar, adresu
   - Přidělená vozidla (automaticky přidá do seznamu vozidel)
   - Příznak schvalovatele (pokud jste v Heliosu vedeni jako schvalovatel, získáte tuto roli)
4. Po úspěšné synchronizaci se zobrazí zpráva s počtem načtených vozidel

**Možné chyby při synchronizaci:**
- *"V ERP Helios nebyl nalezen zaměstnanec s tímto osobním číslem"* – zkontrolujte osobní číslo v profilu
- *"ERP Helios teď nelze načíst"* – dočasný výpadek spojení, zkuste znovu

**Poznámka:** Synchronizace přepíše aktuální údaje profilu daty z Heliosu. Pokud máte v profilu jiné údaje než v Heliosu, budou nahrazeny heliosovými daty.

### 2.5 Přidání vozidla

Pokud jezdíte na služební cesty vlastním vozem, přidejte vozidlo do profilu.

1. V profilu přejděte do sekce **Vozidla**
2. Klikněte na **+ Přidat vozidlo**
3. Vyplňte:
   - **SPZ** - registrační značka
   - **Značka/model** - např. "Škoda Octavia"
   - **Objem motoru** - v cm³ (určuje základní km sazbu)
   - **Druh paliva** - benzín, nafta, CNG, elektro atd.
   - **Spotřeba** - průměrná spotřeba v l/100km
   - **Cena paliva** - zvolte **Podle vyhlášky** (automaticky) nebo **Vlastní cena** (zadáte sami)
4. Klikněte na **Uložit profil**

Vozidla přidaná z Heliosu (přes ERP sync) se zobrazují automaticky.

#### Dokumenty vozidla

K vozidlu lze přiložit doklady (OTP, pojistka, technický průkaz):

1. V detailu vozidla klikněte na **+ Přidat dokument**
2. Vyberte soubor ze svého počítače
3. Pojmenujte dokument
4. Klikněte na **Uložit profil**

Dokumenty lze kdykoli otevřít nebo stáhnout kliknutím na příslušnou ikonu.

### 2.6 Odhlášení

Pro odhlášení klikněte na svou ikonu nebo jméno v horní liště a vyberte **Odhlásit**.

---

## 3. Pro zaměstnance

Jako zaměstnanec můžete vytvářet žádosti o vycestování a po jejich schválení zakládat cestovní příkazy.

### 3.1 Vytvoření žádosti o vycestování

#### Krok 1: Přejděte do sekce Žádosti

1. Klikněte na tlačítko **Žádosti** v horní liště
2. Zobrazí se seznam vašich žádostí

#### Krok 2: Vytvořte novou žádost

1. Klikněte na tlačítko **Nová žádost**
2. Vyplňte základní údaje:
   - **Cíl cesty** - kam jedete (např. "Praha", "Brno")
   - **Odjezd** - datum odjezdu
   - **Příjezd** - datum příjezdu
   - **Doprava** - způsob dopravy (vlastní vozidlo, vlak, letadlo, atd.)
   - **Účel cesty** - proč jedete (např. "Schůzka s klientem")
   - **Schvalovatel** - vyberte nadřízeného který žádost schválí

#### Krok 3: Uložte žádost

1. Klikněte na **Uložit žádost**
2. Žádost se uloží ve stavu **Rozpracováno**

#### Krok 4: Odešlete žádost ke schválení

1. Zkontrolujte že jsou všechny údaje správně
2. Klikněte na **Odeslat ke schválení**
3. Žádost je odeslána schvalovateli
4. Obdržíte e-mail s potvrzením

**Tip:** Ikony s otazníkem (?) u jednotlivých polí zobrazí nápovědu k vyplnění.

### 3.2 Založení cestovního příkazu

Po schválení žádosti můžete založit cestovní příkaz.

#### Krok 1: Najděte schválenou žádost

1. Přejděte do sekce **Žádosti**
2. Vyberte žádost se stavem **Schváleno**
3. Klikněte na tlačítko **+ Založit cestovní příkaz**

**Poznámka:** Pokud už pro žádost existuje cestovní příkaz, tlačítko se nezobrazí a uvidíte text "Cestovní příkaz již existuje".

#### Krok 2: Vyplňte základní údaje cesty

Automaticky se předvyplní údaje ze žádosti:

- **Počátek cesty** - datum a čas zahájení
- **Konec cesty** - datum a čas ukončení
- **Cíl cesty** - místo
- **Účel cesty** - důvod služební cesty

**Tip:** Pro zadání data a času klikněte na pole - zobrazí se kalendář s možností výběru.

#### Krok 3: Vyberte vozidlo (pokud jedete vlastním vozem)

1. V sekci **Vozidlo** klikněte na **Vybrat**
2. Vyberte vozidlo ze seznamu nebo přidejte nové
3. Zkontrolujte:
   - SPZ vozidla
   - Spotřebu (l/100km)
   - Cenu pohonných hmot (automaticky podle vyhlášky)

#### Krok 4: Přidejte úseky trasy

Pro každý úsek cesty (tam, zpět, případné další):

1. Klikněte na **+ Přidat úsek**
2. Zvolte **typ úseku**:
   - **Tuzemský** - cesta v ČR, počítá se tuzemské stravné
   - **Zahraniční** - cesta do zahraničí, počítá se zahraniční stravné v cizí měně
   - **Soukromý** - soukromá část cesty, nezapočítává se do náhrad
3. Vyplňte:
   - **Odjezd** - datum a čas odjezdu
   - **Odkud** - místo odjezdu (např. "Březí")
   - **Kam** - místo příjezdu (např. "Praha")
   - **Příjezd** - datum a čas příjezdu
   - **Firma / místo** - název firmy kterou jste navštívili
   - **Účel** - účel návštěvy
   - **Doprava** - způsob dopravy (vlastní vozidlo, vlak, atd.)
   - **Km** - počet ujetých kilometrů (pouze pro vlastní vozidlo)

4. U **zahraničního úseku** navíc vyplňte:
   - **Země** - výběrem se automaticky načtou příslušné sazby stravného a kurz
   - **Výdaje v cizí měně** - jízdné, ubytování, ostatní v měně dané země

5. Vyplňte náklady (pokud byly):
   - **Jízdné** - vstupenky (vlak, autobus, atd.)
   - **Ubytování** - náklady na hotel
   - **Ostatní** - parkovné, dálniční známka, atd.

**Automatický výpočet stravného:**
- Aplikace automaticky vypočítá stravné podle délky úseku
- Pokud měl zaměstnanec jídlo zdarma, zaškrtněte **Jídlo zdarma**
- U zahraničních úseků se stravné počítá v cizí měně a přepočítává kurzem na CZK

#### Krok 5: Přiložte doklady

1. Přejděte na záložku **Doklady**
2. Klikněte na **+ Přidat doklad**
3. Vyberte soubor z počítače (PDF, JPG, PNG, max. 10 MB)
4. Zadejte:
   - **Druh dokladu** - účtenka, faktura, jízdenka, jiný
   - **Popis** - co je na dokladu (např. "Tankování")
   - **Částka** - výše nákladů (u zahraničních dokladů i v cizí měně)
5. Pro **zobrazení dokladu** klikněte na ikonu oka (náhled) nebo stáhněte kliknutím na ikonu stahování
6. Pro **odebrání dokladu** klikněte na ikonu koše

**Tip:** Doklady se ukládají na server - jsou dostupné i z jiného počítače.

#### Krok 6: Zkontrolujte výpočet

1. Přejděte na záložku **Souhrn**
2. Zkontrolujte vypočtené částky:
   - **Stravné celkem**
   - **Kilometry celkem**
   - **Náhrada za km** (základní + pohonné hmoty)
   - **Jízdné celkem**
   - **Ubytování celkem**
   - **Celkem k výplatě**
3. U zahraničních cest uvidíte souhrn i pro jednotlivé záložky měn (EUR, USD, atd.) s přepočtem na CZK

#### Krok 7: Odešlete ke schválení

1. Klikněte na **Odeslat**
2. Cestovní příkaz je odeslán schvalovateli
3. Obdržíte e-mail s potvrzením

### 3.3 Zahraniční cestovní příkazy

Zahraniční cestovní příkaz se liší od tuzemského tím, že obsahuje výdaje v cizí měně a zahraniční stravné.

#### Stravné v zahraničí

- Stravné se počítá v měně příslušné země (EUR, USD, atd.)
- Sazby stravného jsou načteny automaticky z Heliosu podle zvolené země a data
- Výpočet probíhá ve stejných pásmech jako tuzemský (5-12h, 12-18h, nad 18h), ale v cizí měně
- Celková částka je na záložce **Souhrn** přepočtena kurzem na CZK

#### Kurzy měn

- Aplikace automaticky načítá aktuální kurzy z Heliosu
- Kurz se načítá vždy k datu konkrétního úseku cesty
- Kurzy jsou zobrazeny v souhrnu příkazu

#### Výdaje v cizí měně

- Jízdné, ubytování a ostatní výdaje lze zadat přímo v cizí měně
- Při přidání dokladu lze uvést částku v cizí měně - aplikace ji přepočítá na CZK
- V souhrnu jsou uvedeny jak částky v cizí měně, tak přepočet na CZK

### 3.4 Duplikace cestovního příkazu

Pokud jedete na podobnou cestu opakovaně, můžete zkopírovat existující příkaz.

1. Otevřete existující cestovní příkaz
2. Klikněte na **Duplikovat**
3. Vyberte schválenou žádost ze seznamu
4. Zkontrolujte a upravte údaje
5. Odešlete ke schválení

**Poznámka:** Duplikace vytvoří nový příkaz s předvyplněnými údaji, ale neuloží se automaticky.

### 3.5 Tisk nebo uložení do PDF

1. Otevřete cestovní příkaz
2. Klikněte na **Tisk / PDF** v horní liště
3. Zobrazí se náhled pro tisk
4. V prohlížeči:
   - **Ctrl+P** (Windows) nebo **Cmd+P** (Mac)
   - Vyberte **Uložit jako PDF** jako tiskárnu
   - Klikněte na **Uložit**

---

## 4. Pro schvalovatele

Jako schvalovatel schvalujete žádosti o vycestování a cestovní příkazy podřízených.

### 4.1 Přístup k dashboardu schvalování

1. Klikněte na **Schvalování** v horní liště
2. Zobrazí se seznam žádostí a příkazů čekajících na schválení
3. Červené číslo u tlačítka "Schvalování" ukazuje počet čekajících položek

### 4.2 Schvalování žádostí o vycestování

#### Krok 1: Otevřete žádost

1. V sekci **Schvalování** najděte žádost se stavem **Ke schválení**
2. Klikněte na žádost pro zobrazení detailů

#### Krok 2: Zkontrolujte údaje

Zkontrolujte:
- **Cíl cesty** - je cesta opodstatněná?
- **Datum odjezdu a příjezdu** - jsou datumy v pořádku?
- **Doprava** - je zvolený způsob dopravy vhodný?
- **Účel cesty** - je účel jasně popsán?

#### Krok 3: Schvalte nebo zamítněte

**Pro schválení:**
1. Klikněte na **Schválit**
2. Žádost se označí jako **Schváleno**
3. Zaměstnanec obdrží e-mail s potvrzením

**Pro zamítnutí:**
1. Klikněte na **Zamítnout**
2. Zadejte důvod zamítnutí
3. Zaměstnanec obdrží e-mail s důvodem

### 4.3 Schvalování cestovních příkazů

#### Krok 1: Otevřete cestovní příkaz

1. V sekci **Schvalování** najděte příkaz se stavem **Ke schválení**
2. Klikněte na příkaz pro zobrazení detailů

#### Krok 2: Zkontrolujte údaje

Zkontrolujte:
- **Základní údaje** - datum, cíl, účel cesty
- **Trasa** - jednotlivé úseky a km (včetně zahraničních úseků a použité měny)
- **Náklady** - stravné, jízdné, ubytování (v CZK i v cizích měnách)
- **Doklady** - jsou přiloženy všechny potřebné doklady? Kliknutím na doklad jej zobrazíte
- **Výpočet** - je celková částka v pořádku?

#### Krok 3: Schvalte, zamítněte nebo vraťte

**Pro schválení:**
1. Klikněte na **Schválit**
2. Příkaz se označí jako **Schváleno**
3. Zaměstnanec obdrží e-mail s potvrzením

**Pro zamítnutí:**
1. Klikněte na **Zamítnout**
2. Zadejte důvod zamítnutí
3. Zaměstnanec obdrží e-mail s důvodem

**Pro vrácení k doplnění:**
1. Klikněte na **Vrátit k doplnění**
2. Zadejte co je třeba opravit
3. Příkaz se vrátí zaměstnanci ve stavu **Vráceno k doplnění**

### 4.4 Fáze schvalování

Cestovní příkaz prochází těmito fázemi (záleží na konfiguraci firmy):

1. **Manažer** - přímý nadřízený zaměstnance
2. **Účetní** - kontrola formálních náležitostí (pokud je v systému)
3. **Finální schvalovatel** - konečné schválení

Jako schvalovatel vidíte vždy jen příkazy ve své fázi. Po vašem schválení postupuje příkaz do další fáze.

### 4.5 E-mailová notifikace

Obdržíte e-mail když:
- Zaměstnanec odešle žádost ke schválení
- Zaměstnanec odešle cestovní příkaz ke schválení
- Zaměstnanec upraví a znovu odešle vrácený příkaz

---

## 5. Pro účetní

Jako účetní kontrolujete schválené cestovní příkazy před exportem do Heliosu.

### 5.1 Přístup k dashboardu účetní

1. Klikněte na **Schvalování** v horní liště
2. Zobrazí se příkazy čekající na kontrolu účetní

### 5.2 Kontrola cestovního příkazu

#### Krok 1: Otevřete příkaz ke kontrole

1. Najděte příkaz se stavem **Ke schválení** nebo fází **Účetní**
2. Klikněte na příkaz

#### Krok 2: Zkontrolujte formální náležitosti

Zkontrolujte:
- **Doklady** - jsou přiloženy všechny účtenky? Kliknutím doklad otevřete nebo stáhněte
- **Částky** - souhlasí částky na dokladech s vyúčtováním?
- **Výpočet stravného** - je správně vypočteno (včetně zahraničního)?
- **Výpočet km náhrady** - je správně vypočteno?
- **Středisko** - je správně přiřazeno?
- **Účel cesty** - je jasně uveden pro účely Helios?
- **Kurzy měn** - u zahraničních cest zkontrolujte použité kurzy

#### Krok 3: Schvalte nebo vraťte

**Pro schválení:**
1. Klikněte na **Schválit**
2. Příkaz postupuje finálnímu schvalovateli
3. Po finálním schválení se příkaz označí jako **Připraveno k exportu**

**Pro vrácení:**
1. Klikněte na **Vrátit k doplnění**
2. Zadejte co je třeba opravit
3. Příkaz se vrátí zaměstnanci

### 5.3 Export do Heliosu

#### Krok 1: Najděte příkazy k exportu

1. Použijte filtr **Stav** → **Schváleno**
2. Najděte příkazy se stavem exportu **Připraveno**

#### Krok 2: Exportujte do Heliosu

1. Otevřete příkaz
2. Klikněte na **Exportovat do Heliosu**
3. Aplikace:
   - Odešle data do Heliosu
   - Vytvoří PDF s cestovním příkazem
   - Přiloží ho jako přílohu do Heliosu
   - Označí příkaz jako **Naimportováno**

#### Krok 3: Zkontrolujte v Heliosu

1. Přihlaste se do Heliosu
2. Najděte vytvořený doklad (číslo dokladu je zobrazeno v aplikaci)
3. Zkontrolujte že:
   - Data jsou správně přenesena
   - PDF příloha je přiložena
   - Částky souhlasí

**Poznámka:** Export je jednosměrný - změny v Heliosu se nepromítnou zpět do aplikace.

#### Krok 4: Reset importu (opakování exportu)

Pokud byl export neúspěšný nebo je třeba příkaz opakovaně exportovat:

1. Otevřete naimportovaný příkaz
2. Klikněte na **Reset importu**
3. Příkaz se vrátí do stavu **Připraveno k exportu**
4. Export lze provést znovu

**Upozornění:** Reset importu smaže vazbu na původní doklad v Heliosu. Zkontrolujte stav v Heliosu před resetem.

### 5.4 Náhled příkazu pro Helios

Před exportem si můžete prohlédnout jak bude příkaz vypadat v Heliosu:

1. Otevřete příkaz
2. Klikněte na **Náhled Helios** (nebo použijte URL náhledu)
3. Zobrazí se HTML náhled cestovního příkazu ve formátu pro Helios
4. Náhled obsahuje i přiložené doklady

### 5.5 Úprava cizích příkazů

Účetní může upravovat příkazy jiných zaměstnanců:

1. Najděte příkaz v seznamu
2. Otevřete ho
3. Upravte údaje (km, částky, doklady)
4. Změny se automaticky ukládají
5. Můžete příkaz odeslat ke schválení

**Upozornění:** Buďte opatrní při úpravách - změny jsou trvalé.

---

## 6. Pro administrátory

Jako administrátor spravujete uživatele a nastavení aplikace.

### 6.1 Správa uživatelů

#### Krok 1: Přejděte do správy uživatelů

1. Klikněte na **Uživatelé** v horní liště
2. Zobrazí se seznam všech uživatelů

#### Krok 2: Přidejte nového uživatele

1. Klikněte na **+ Nový uživatel**
2. Vyplňte údaje:
   - **Jméno** - celé jméno (např. "Jan Novák")
   - **E-mail** - přihlašovací e-mail
   - **Heslo** - počáteční heslo (uživatel si ho změní po přihlášení)
   - **Osobní číslo** - evidenční číslo zaměstnance
   - **Středisko** - organizační jednotka
   - **Adresa** - adresa bydliště
   - **Telefon** - kontaktní telefon

3. Přiřaďte role:
   - ☐ **Schvalovatel** - může schvalovat žádosti a příkazy
   - ☐ **Účetní** - může kontrolovat a exportovat do Heliosu
   - ☐ **Administrátor** - může spravovat uživatele

4. Nastavte schvalovatele:
   - **Nadřízený schvalovatel** - schvaluje žádosti a první fázi příkazů
   - **Finální schvalovatel** - schvaluje finální fázi příkazů

5. Klikněte na **Uložit**

#### Krok 3: Upravte existujícího uživatele

1. V seznamu uživatelů najděte uživatele
2. Klikněte na něj
3. Upravte údaje
4. Klikněte na **Uložit**

#### Krok 4: Deaktivujte uživatele

1. Otevřete uživatele
2. Odškrtněte **Aktivní**
3. Uživatel se nebude moci přihlásit
4. Jeho příkazy zůstanou v systému

**Tip:** Nemazejte uživatele - raději je deaktivujte. Zachováte historii jejich příkazů.

### 6.2 Správa vozidel

Administrátor může spravovat vozidla všech uživatelů:

1. V profilu uživatele přejděte na **Vozidla**
2. Přidejte nebo upravte vozidlo:
   - **SPZ** - registrační značka
   - **Značka/model** - např. "Škoda Octavia"
   - **Objem motoru** - v cm³
   - **Druh paliva** - benzín, nafta, CNG, atd.
   - **Spotřeba** - průměrná spotřeba v l/100km
   - **Cena paliva** - podle vyhlášky nebo vlastní

### 6.3 Správa sazeb

#### Základní sazby (pro celou firmu)

1. Přejděte do **Nastavení** (ikona ozubeného kola)
2. Upravte:
   - **Tuzemské stravné** - základní sazba na den
   - **Zahraniční stravné** - podle zemí (načítá se z Heliosu)
   - **Základní km sazba** - náhrada za km pro osobní vozy
   - **Ceny pohonných hmot** - podle vyhlášky MF

3. Změny se projeví u všech nových příkazů

**Poznámka:** Změna sazeb neovlivní již vytvořené příkazy - ty si uchovávají původní sazby.

### 6.4 Monitor sazeb

Aplikace automaticky sleduje platnost zákonných sazeb (stravné, km náhrady, ceny paliv). Pokud jsou sazby zastaralé nebo se změní vyhláška, zobrazí se upozornění.

1. Přejděte do **Nastavení** → **Monitor sazeb**
2. Uvidíte stav kontroly sazeb:
   - Datum poslední kontroly
   - Zda jsou sazby aktuální
   - Případné změny oproti předchozím sazbám
3. Pro ruční spuštění kontroly klikněte na **Zkontrolovat sazby**

**Poznámka:** Automatická kontrola sazeb probíhá při každém načtení aplikace.

### 6.5 Synchronizace s ERP (Helios)

Administrátor může spustit synchronizaci dat z Heliosu:

#### Synchronizace uživatelů a vozidel

1. Přejděte do **Nastavení** → **ERP synchronizace**
2. Klikněte na **Synchronizovat z Heliosu**
3. Aplikace načte:
   - Aktuální údaje zaměstnanců (jméno, středisko, osobní číslo)
   - Přidělená vozidla
   - Role a oprávnění

#### Synchronizace sazeb a kurzů

- Sazby zahraničního stravného jsou načítány automaticky z Heliosu při každém použití
- Kurzy měn se načítají vždy k datu úseku zahraniční cesty
- Ruční obnovení: **Nastavení** → **Monitor sazeb** → **Zkontrolovat sazby**

---

## 7. Stavy cestovních příkazů

### 7.1 Životní cyklus žádosti

```
Rozpracováno → Ke schválení → Schváleno/Zamítnuto
```

**Rozpracováno** - žádost je vytvořena ale ještě neodeslána
**Ke schválení** - žádost čeká na schválení nadřízeným
**Schváleno** - žádost byla schválena, lze založit cestovní příkaz
**Zamítnuto** - žádost byla zamítnuta

### 7.2 Životní cyklus cestovního příkazu

```
Rozpracováno → Ke schválení → [Kontrola účetní] → [Finální schválení] → Schváleno → Naimportováno → Uzavřeno
                    ↓
              Vráceno k doplnění → Rozpracováno
                    ↓
                Zamítnuto
```

**Rozpracováno** - příkaz je vytvořen ale ještě neodeslán

**Ke schválení** - příkaz čeká na schválení v jedné z fází:
- **Manažer** - schvaluje přímý nadřízený
- **Účetní** - kontroluje účetní (pokud je v systému)
- **Finální schvalovatel** - konečné schválení

**Vráceno k doplnění** - příkaz byl vrácen k opravě, zaměstnanec může upravit a znovu odeslat

**Schváleno** - příkaz prošel všemi schvalovacími fázemi

**Naimportováno** - příkaz byl exportován do Heliosu

**Uzavřeno** - příkaz je finálně uzavřen (po výplatě zaměstnanci)

**Zamítnuto** - příkaz byl zamítnut schvalovatelem

### 7.3 Barevné označení stavů

- 🟡 **Žlutá** - Rozpracováno (draft)
- 🔵 **Modrá** - Ke schválení (submitted)
- 🟠 **Oranžová** - Vráceno k doplnění (returned)
- 🟢 **Zelená** - Schváleno (approved)
- 🟣 **Fialová** - Naimportováno (imported)
- ⚫ **Šedá** - Uzavřeno (closed)
- 🔴 **Červená** - Zamítnuto (rejected)

---

## 8. Vyhledávání a filtrování

### 8.1 Vyhledávání v seznamu cestovních příkazů

V levém panelu se seznamem příkazů je dostupné vyhledávání:

1. Klikněte do pole **Hledat...**
2. Zadejte hledaný text - prohledávají se:
   - Číslo příkazu
   - Jméno zaměstnance
   - Účel cesty
   - Cíl cesty
   - Středisko

Vyhledávání pracuje bez ohledu na velikost písmen a diakritiku.

### 8.2 Filtrování podle stavu

1. Nad seznamem příkazů vyberte filtr **Stav**
2. Zvolte stav:
   - **Vše** - zobrazí všechny příkazy
   - **Rozpracováno**
   - **Ke schválení**
   - **Vráceno k doplnění**
   - **Schváleno**
   - **Naimportováno**
   - **Uzavřeno**
   - **Zamítnuto**

### 8.3 Řazení

Příkazy jsou automaticky řazeny od nejnovějšího. Schvalovací dashboard zobrazuje maximálně 50 čekajících položek.

---

## 9. Často kladené otázky

### 9.1 Registrace a přihlášení

**Q: Jak se zaregistruji?**
A: Na přihlašovací obrazovce klikněte na **Vytvořit účet**, vyplňte jméno, e-mail a heslo (min. 8 znaků) a potvrďte heslo. Po odeslání formuláře obdržíte ověřovací e-mail.

**Q: Nedostal jsem ověřovací e-mail, co mám dělat?**
A: Zkontrolujte složku **Spam / Nevyžádaná pošta**. Pokud e-mail není ani tam, kontaktujte administrátora – ten může účet aktivovat ručně.

**Q: Ověřovací odkaz mi nefunguje (vypršel).**
A: Ověřovací odkaz má omezenou platnost 24 hodin. Pokud vypršel, kontaktujte administrátora, který vám zašle nový nebo účet aktivuje přímo.

**Q: Zapomněl jsem heslo.**
A: Kontaktujte administrátora aplikace – ten vám nastaví nové heslo.

**Q: Dostanu účet automaticky nebo se musím registrovat?**
A: Záleží na nastavení firmy. Administrátor může účet vytvořit přímo, v takovém případě vám sdělí přihlašovací údaje a registraci přeskočte. Pokud účet nemáte, použijte tlačítko **Vytvořit účet** na přihlašovací obrazovce.

### 9.3 Obecné otázky

**Q: Mohu vytvořit cestovní příkaz bez schválené žádosti?**
A: Ne. Cestovní příkaz lze vytvořit pouze ze schválené žádosti o vycestování. Nejdřív musíte vytvořit a nechat schválit žádost.

**Q: Mohu upravit cestovní příkaz po odeslání?**
A: Ne. Po odeslání ke schválení nemůžete příkaz upravovat. Pokud je třeba něco opravit, požádejte schvalovatele o vrácení k doplnění.

**Q: Jak dlouho trvá schválení?**
A: Záleží na schvalovateli. Ten obdrží e-mail s notifikací. Průměrně 1-2 dny.

**Q: Kam se ukládají data?**
A: Data se ukládají na serveru. Jsou dostupná z jakéhokoli počítače po přihlášení.

**Q: Jak poznám v jaké fázi schvalování je můj příkaz?**
A: V detailu příkazu je zobrazen aktuální stav a fáze schvalování. Při každé změně fáze obdržíte e-mail.

### 9.4 Výpočet náhrad

**Q: Jak se počítá stravné?**
A: Stravné se počítá automaticky podle délky úseku cesty:
- 5-12 hodin: částečné stravné (1/3 denní sazby)
- 12-18 hodin: zvýšené stravné (2/3 denní sazby)
- Nad 18 hodin: plné stravné (100% denní sazby)

**Q: Jak se počítá zahraniční stravné?**
A: Zahraniční stravné se počítá ve stejných pásmech jako tuzemské, ale v měně příslušné země. Sazby jsou přebírány z Heliosu a jsou specifické pro každou zemi. Výsledná částka se přepočítá na CZK aktuálním kurzem.

**Q: Co když mi zaměstnavatel poskytl jídlo zdarma?**
A: Zaškrtněte "Jídlo zdarma" u příslušného úseku. Stravné se automaticky sníží.

**Q: Jak se počítá náhrada za použití osobního vozidla?**
A: Náhrada se skládá ze dvou částí:
- **Základní sazba** - podle objemu motoru (např. 5,90 Kč/km)
- **Pohonné hmoty** - podle spotřeby a ceny paliva

**Q: Můžu si zadat vlastní cenu paliva?**
A: Ano, ve vozidlu můžete změnit režim z "Podle vyhlášky" na "Vlastní cena" a zadat aktuální cenu za kterou jste tankovali.

**Q: Jaký kurz se použije pro přepočet zahraničních výdajů?**
A: Kurz se načítá z Heliosu vždy k datu příslušného úseku cesty.

### 9.5 Doklady

**Q: Jaké doklady musím přiložit?**
A: Všechny doklady prokazující náklady:
- Účtenky za ubytování
- Jízdenky (vlak, autobus, letadlo)
- Účtenky za parkovné
- Dálniční známky
- Ostatní náklady související s cestou

**Q: V jakém formátu můžu nahrát doklady?**
A: PDF, JPG, PNG. Maximální velikost 10 MB na soubor.

**Q: Co když nemám účtenku?**
A: Pokud nemáte doklad, napište do poznámky důvod. Schvalovatel rozhodne zda náklad uzná.

**Q: Mohu doklad smazat po odeslání příkazu?**
A: Ne, po odeslání ke schválení nelze doklady mazat. Požádejte schvalovatele o vrácení k doplnění.

**Q: Jak zobrazím přiložený doklad?**
A: V záložce **Doklady** klikněte na ikonu oka (náhled) pro zobrazení přímo v aplikaci, nebo na ikonu stahování pro uložení souboru.

### 9.6 Zahraniční cesty

**Q: Jak nastavím zahraniční úsek trasy?**
A: Při přidávání úseku trasy zvolte typ **Zahraniční** a vyberte příslušnou zemi. Aplikace automaticky načte sazby stravného a kurz měny.

**Q: Co je soukromý úsek?**
A: Soukromý úsek označuje část cesty, která není pracovní (např. návštěva rodiny v rámci pracovní cesty). Za soukromý úsek se neposkytují žádné náhrady.

**Q: Kde vidím přepočet zahraničních výdajů na CZK?**
A: V záložce **Souhrn** je přehled výdajů v CZK. U příkazů s zahraničními úseky jsou navíc zobrazeny souhrny pro jednotlivé měny (EUR, USD, atd.).

### 9.7 Technické problémy

**Q: Aplikace mi nefunguje, co mám dělat?**
A: Zkuste:
1. Obnovit stránku (Ctrl+F5)
2. Vymazat cache prohlížeče
3. Zkusit jiný prohlížeč
4. Kontaktovat IT podporu

**Q: Ztratil jsem rozpracovaný příkaz, kde ho najdu?**
A: Data se ukládají na serveru. Příkaz najdete v seznamu příkazů ve stavu "Rozpracováno" na jakémkoli počítači po přihlášení.

**Q: Nemohu se přihlásit, co mám dělat?**
A: Zkontrolujte:
1. Správnost e-mailu a hesla
2. Kontaktujte administrátora - možná je účet deaktivovaný
3. Zkuste reset hesla (pokud je funkce dostupná)

**Q: Export do Heliosu selhal, co mám dělat?**
A: Kontaktujte účetní nebo administrátora. Ti mohou provést reset importu a export zopakovat.

### 9.8 Nápověda v aplikaci

**Q: Kde najdu nápovědu přímo v aplikaci?**
A: U většiny polí je ikona **?** (otazník). Klikněte na ni a zobrazí se kontextová nápověda pro dané pole.

---

## Kontakt a podpora

**IT podpora:**
E-mail: it@oresi.cz
Telefon: +420 XXX XXX XXX

**Administrátor aplikace:**
Jméno: [Administrátor]
E-mail: [e-mail]

**Vývojář aplikace:**
Zynaptec
Web: www.zynaptec.cz

---

**Konec manuálu**

_Verze 1.2 | © 2026 Oresi United Kitchens | Vytvořil: Zynaptec_
