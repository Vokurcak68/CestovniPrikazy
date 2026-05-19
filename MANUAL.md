# Uživatelský manuál - Aplikace Cestovní příkazy

**Verze:** 1.0
**Datum:** 15. 5. 2026
**Organizace:** Oresi United Kitchens

---

## Obsah

1. [Přehled aplikace](#1-přehled-aplikace)
2. [Pro zaměstnance](#2-pro-zaměstnance)
3. [Pro schvalovatele](#3-pro-schvalovatele)
4. [Pro účetní](#4-pro-účetní)
5. [Pro administrátory](#5-pro-administrátory)
6. [Stavy cestovních příkazů](#6-stavy-cestovních-příkazů)
7. [Často kladené otázky](#7-často-kladené-otázky)

---

## 1. Přehled aplikace

### 1.1 Co je to aplikace Cestovní příkazy?

Aplikace Cestovní příkazy je webová aplikace pro správu služebních cest zaměstnanců. Umožňuje:

- Vytváření žádostí o vycestování
- Schvalování žádostí nadřízenými
- Zakládání cestovních příkazů ze schválených žádostí
- Vyúčtování nákladů na služební cestu
- Export dat do účetního systému Helios

### 1.2 Přihlášení

1. Otevřete aplikaci v prohlížeči
2. Zadejte své **přihlašovací jméno** (e-mail)
3. Zadejte **heslo**
4. Klikněte na **Přihlásit**

### 1.3 Hlavní rozhraní

Po přihlášení uvidíte:

- **Horní lišta** - navigace mezi sekcemi aplikace
- **Levý panel** - seznam cestovních příkazů/žádostí
- **Hlavní panel** - detail vybraného příkazu/žádosti
- **Ikony nápovědy (?)** - klikněte pro zobrazení kontextové nápovědy

---

## 2. Pro zaměstnance

Jako zaměstnanec můžete vytvářet žádosti o vycestování a po jejich schválení zakládat cestovní příkazy.

### 2.1 Vytvoření žádosti o vycestování

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

### 2.2 Založení cestovního příkazu

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
2. Vyplňte:
   - **Odjezd** - datum a čas odjezdu
   - **Odkud** - místo odjezdu (např. "Březí")
   - **Kam** - místo příjezdu (např. "Praha")
   - **Příjezd** - datum a čas příjezdu
   - **Firma / místo** - název firmy kterou jste navštívili
   - **Účel** - účel návštěvy
   - **Doprava** - způsob dopravy (vlastní vozidlo, vlak, atd.)
   - **Km** - počet ujetých kilometrů (pouze pro vlastní vozidlo)

3. Vyplňte náklady (pokud byly):
   - **Jízdné** - vstupenky (vlak, autobus, atd.)
   - **Ubytování** - náklady na hotel
   - **Ostatní** - parkovné, dálniční známka, atd.

**Automatický výpočet stravného:**
- Aplikace automaticky vypočítá stravné podle délky úseku
- Pokud měl zaměstnanec jídlo zdarma, zaškrtněte **Jídlo zdarma**

#### Krok 5: Přiložte doklady

1. Přejděte na záložku **Doklady**
2. Klikněte na **+ Přidat doklad**
3. Vyberte soubor z počítače (PDF, JPG, PNG)
4. Zadejte:
   - **Popis** - co je na dokladu (např. "Tankování")
   - **Částka** - výše nákladů

#### Krok 6: Zkontrolujte výpočet

1. Přejděte na záložku **Souhrn**
2. Zkontrolujte vypočtené částky:
   - **Stravné celkem**
   - **Kilometry celkem**
   - **Náhrada za km** (základní + pohonné hmoty)
   - **Jízdné celkem**
   - **Ubytování celkem**
   - **Celkem k výplatě**

#### Krok 7: Odešlete ke schválení

1. Klikněte na **Odeslat**
2. Cestovní příkaz je odeslán schvalovateli
3. Obdržíte e-mail s potvrzením

### 2.3 Duplikace cestovního příkazu

Pokud jedete na podobnou cestu opakovaně, můžete zkopírovat existující příkaz.

1. Otevřete existující cestovní příkaz
2. Klikněte na **Duplikovat**
3. Vyberte schválenou žádost ze seznamu
4. Zkontrolujte a upravte údaje
5. Odešlete ke schválení

**Poznámka:** Duplikace vytvoří nový příkaz s předvyplněnými údaji, ale neuloží se automaticky.

### 2.4 Tisk nebo uložení do PDF

1. Otevřete cestovní příkaz
2. Klikněte na **Tisk / PDF** v horní liště
3. Zobrazí se náhled pro tisk
4. V prohlížeči:
   - **Ctrl+P** (Windows) nebo **Cmd+P** (Mac)
   - Vyberte **Uložit jako PDF** jako tiskárnu
   - Klikněte na **Uložit**

---

## 3. Pro schvalovatele

Jako schvalovatel schvalujete žádosti o vycestování a cestovní příkazy podřízených.

### 3.1 Přístup k dashboardu schvalování

1. Klikněte na **Schvalování** v horní liště
2. Zobrazí se seznam žádostí a příkazů čekajících na schválení
3. Červené číslo u tlačítka "Schvalování" ukazuje počet čekajících položek

### 3.2 Schvalování žádostí o vycestování

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

### 3.3 Schvalování cestovních příkazů

#### Krok 1: Otevřete cestovní příkaz

1. V sekci **Schvalování** najděte příkaz se stavem **Ke schválení**
2. Klikněte na příkaz pro zobrazení detailů

#### Krok 2: Zkontrolujte údaje

Zkontrolujte:
- **Základní údaje** - datum, cíl, účel cesty
- **Trasa** - jednotlivé úseky a km
- **Náklady** - stravné, jízdné, ubytování
- **Doklady** - jsou přiloženy všechny potřebné doklady?
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

### 3.4 E-mailová notifikace

Obdržíte e-mail když:
- Zaměstnanec odešle žádost ke schválení
- Zaměstnanec odešle cestovní příkaz ke schválení
- Zaměstnanec upraví a znovu odešle vrácený příkaz

---

## 4. Pro účetní

Jako účetní kontrolujete schválené cestovní příkazy před exportem do Heliosu.

### 4.1 Přístup k dashboardu účetní

1. Klikněte na **Schvalování** v horní liště
2. Zobrazí se příkazy čekající na kontrolu účetní

### 4.2 Kontrola cestovního příkazu

#### Krok 1: Otevřete příkaz ke kontrole

1. Najděte příkaz se stavem **Ke schválení** nebo fází **Účetní**
2. Klikněte na příkaz

#### Krok 2: Zkontrolujte formální náležitosti

Zkontrolujte:
- **Doklady** - jsou přiloženy všechny účtenky?
- **Částky** - souhlasí částky na dokladech s vyúčtováním?
- **Výpočet stravného** - je správně vypočteno?
- **Výpočet km náhrady** - je správně vypočteno?
- **Středisko** - je správně přiřazeno?
- **Účel cesty** - je jasně uveden pro účely Helios?

#### Krok 3: Schvalte nebo vraťte

**Pro schválení:**
1. Klikněte na **Schválit**
2. Příkaz postupuje finálnímu schvalovateli
3. Po finálním schválení se příkaz označí jako **Připraveno k exportu**

**Pro vrácení:**
1. Klikněte na **Vrátit k doplnění**
2. Zadejte co je třeba opravit
3. Příkaz se vrátí zaměstnanci

### 4.3 Export do Heliosu

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

### 4.4 Úprava cizích příkazů

Účetní může upravovat příkazy jiných zaměstnanců:

1. Najděte příkaz v seznamu
2. Otevřete ho
3. Upravte údaje (km, částky, doklady)
4. Změny se automaticky ukládají
5. Můžete příkaz odeslat ke schválení

**Upozornění:** Buďte opatrní při úpravách - změny jsou trvalé.

---

## 5. Pro administrátory

Jako administrátor spravujete uživatele a nastavení aplikace.

### 5.1 Správa uživatelů

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

### 5.2 Správa vozidel

Administrátor může spravovat firemní vozidla:

1. V profilu uživatele přejděte na **Vozidla**
2. Přidejte nebo upravte vozidlo:
   - **SPZ** - registrační značka
   - **Značka/model** - např. "Škoda Octavia"
   - **Objem motoru** - v cm³
   - **Druh paliva** - benzín, nafta, CNG, atd.
   - **Spotřeba** - průměrná spotřeba v l/100km
   - **Cena paliva** - podle vyhlášky nebo vlastní

### 5.3 Správa sazeb

#### Základní sazby (pro celou firmu)

1. Přejděte do **Nastavení** (ikona ozubeného kola)
2. Upravte:
   - **Tuzemské stravné** - základní sazba na den
   - **Zahraniční stravné** - podle zemí
   - **Základní km sazba** - náhrada za km pro osobní vozy
   - **Ceny pohonných hmot** - podle vyhlášky MF

3. Změny se projeví u všech nových příkazů

**Poznámka:** Změna sazeb neovlivní již vytvořené příkazy - ty si uchovávají původní sazby.

---

## 6. Stavy cestovních příkazů

### 6.1 Životní cyklus žádosti

```
Rozpracováno → Ke schválení → Schváleno/Zamítnuto
```

**Rozpracováno** - žádost je vytvořena ale ještě neodeslána
**Ke schválení** - žádost čeká na schválení nadřízeným
**Schváleno** - žádost byla schválena, lze založit cestovní příkaz
**Zamítnuto** - žádost byla zamítnuta

### 6.2 Životní cyklus cestovního příkazu

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

### 6.3 Barevné označení stavů

- 🟡 **Žlutá** - Rozpracováno (draft)
- 🔵 **Modrá** - Ke schválení (submitted)
- 🟠 **Oranžová** - Vráceno k doplnění (returned)
- 🟢 **Zelená** - Schváleno (approved)
- 🟣 **Fialová** - Naimportováno (imported)
- ⚫ **Šedá** - Uzavřeno (closed)
- 🔴 **Červená** - Zamítnuto (rejected)

---

## 7. Často kladené otázky

### 7.1 Obecné otázky

**Q: Mohu vytvořit cestovní příkaz bez schválené žádosti?**
A: Ne. Cestovní příkaz lze vytvořit pouze ze schválené žádosti o vycestování. Nejdřív musíte vytvořit a nechat schválit žádost.

**Q: Mohu upravit cestovní příkaz po odeslání?**
A: Ne. Po odeslání ke schválení nemůžete příkaz upravovat. Pokud je třeba něco opravit, požádejte schvalovatele o vrácení k doplnění.

**Q: Jak dlouho trvá schválení?**
A: Záleží na schvalovateli. Ten obdrží e-mail s notifikací. Průměrně 1-2 dny.

**Q: Kam se ukládají data?**
A: Data se ukládají lokálně v prohlížeči (localStorage) a synchronizují se se serverem. Nezapomeňte odeslat příkaz ke schválení, aby se uložil na server.

### 7.2 Výpočet náhrad

**Q: Jak se počítá stravné?**
A: Stravné se počítá automaticky podle délky úseku cesty:
- 5-12 hodin: částečné stravné (1/3 denní sazby)
- 12-18 hodin: zvýšené stravné (2/3 denní sazby)
- Nad 18 hodin: plné stravné (100% denní sazby)

**Q: Co když mi zaměstnavatel poskytl jídlo zdarma?**
A: Zaškrtněte "Jídlo zdarma" u příslušného úseku. Stravné se automaticky sníží.

**Q: Jak se počítá náhrada za použití osobního vozidla?**
A: Náhrada se skládá ze dvou částí:
- **Základní sazba** - podle objemu motoru (např. 5,90 Kč/km)
- **Pohonné hmoty** - podle spotřeby a ceny paliva

**Q: Můžu si zadat vlastní cenu paliva?**
A: Ano, ve vozidlu můžete změnit režim z "Podle vyhlášky" na "Vlastní cena" a zadat aktuální cenu za kterou jste tankovali.

### 7.3 Doklady

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

### 7.4 Technické problémy

**Q: Aplikace mi nefunguje, co mám dělat?**
A: Zkuste:
1. Obnovit stránku (Ctrl+F5)
2. Vymazat cache prohlížeče
3. Zkusit jiný prohlížeč
4. Kontaktovat IT podporu

**Q: Ztratil jsem rozpracovaný příkaz, kde ho najdu?**
A: Příkaz se ukládá automaticky v prohlížeči. Zkontrolujte:
1. Seznam příkazů - je tam ve stavu "Rozpracováno"
2. Pokud jste přihlášen na jiném počítači/prohlížeči, data tam nejsou (ukládá se lokálně)
3. Pokud jste vymazal cache, data jsou ztracena

**Q: Nemohu se přihlásit, co mám dělat?**
A: Zkontrolujte:
1. Správnost e-mailu a hesla
2. Kontaktujte administrátora - možná je účet deaktivovaný
3. Zkuste reset hesla (pokud je funkce dostupná)

### 7.5 Nápověda v aplikaci

**Q: Kde najdu nápovědu přímo v aplikaci?**
A: U většiny polí je ikona **?** (otazník). Klikněte na ni a zobrazí se kontextová nápověda.

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

_Verze 1.0 | © 2026 Oresi United Kitchens | Vytvořil: Zynaptec_
