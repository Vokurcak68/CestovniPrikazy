# RUNBOOK

## 1) Kdyz se "ztraci" data cestaku na jinem PC
1. Otevrit detail cestaku a overit API odpoved v prohlizeci (`routeLines`, `trip`, `employee`).
2. Zkontrolovat, zda uzivatel nema stary lokalni draft jineho uzivatele.
3. Udelat odhlaseni/prihlaseni a znovu nacist detail.
4. Pokud stav nesedi mezi DB a UI, zkontrolovat callback/import logiku.

## 2) Kdyz jsou duplicity cisla cestaku
1. Spustit `python tools/check_data_integrity.py`.
2. Najit duplicity v reportu.
3. U starsich koliznich zaznamu provest rucni renumber v DB podle roku.
4. Overit novy submit - backend ma cislo automaticky narovnat.

## 3) Kdyz se rozbije cestina
1. Overit DB kodovani textu notifikaci.
2. Overit odpoved API.
3. Overit frontend normalizaci textu v notifikacich.
4. U historickych dat provest jednorazovou opravu textu.

## 4) Kdyz nefunguje callback z ERP
1. Overit DNS a dostupnost callback URL.
2. Otestovat endpoint callbacku lokalne i pres domenu.
3. Overit, ze ERP vola spravnou verejnou adresu.
4. Overit zapis zmeny stavu do DB aplikace.

## 5) Kdyz admin nemuze mazat uzivatele
1. Overit roli `admin`.
2. Overit, zda uzivatel nema ERP vazbu (`helios_user_id`/`source_system`).
3. U ERP vazby je mazani zamerne blokovane.
4. Bez ERP vazby ma mazani projit.
