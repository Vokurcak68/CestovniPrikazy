# Stabilization Checklist

## Pred kazdym releasem
1. Projit login, registraci, odhlaseni.
2. Projit role `employee`, `approver`, `admin`.
3. Otestovat vytvoreni, odeslani, schvaleni, vraceni k doplneni.
4. Otestovat mazani uzivatele:
   - bez ERP vazby: povolit
   - s ERP vazbou: zakazat
5. Otestovat import callback z ERP (zmena stavu v aplikaci).
6. Otestovat zobrazeni cestaku ze dvou ruznych PC/prohlizecu.
7. Otestovat cestinu v sekci Upozorneni.

## Automaticke kontroly pred nasazenim
1. Spustit kontrolu integrity databaze: `python tools/check_data_integrity.py`.
2. Zkontrolovat, ze nejsou duplicitni cisla cestaku.
3. Zkontrolovat, ze `submitted/approved` cestaky maji povinne udaje.
4. Zkontrolovat, ze v notifikacich nejsou znaky mojibake (`Ă`, `Ĺ`, `ďż˝`).

## Bezpecnostni pojistky v kodu
1. Unikatni cislo cestaku je hlidane backendem (`ensure_unique_order_number`).
2. Pri submitu se validuji povinna business pole:
   - ucel cesty
   - Od/Do na kazdem useku
   - ucel useku
3. Frontend drzi lokalni data oddelene podle prihlaseneho uzivatele.
