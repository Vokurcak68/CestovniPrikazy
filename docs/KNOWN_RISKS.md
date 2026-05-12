# Known Risks

## R1: Lokalni stav muze prebit serverova data
- Riziko: stary lokalni draft pod jinym uzivatelem.
- Mitigace: izolace localStorage podle user identity + server snapshot hydration.

## R2: Duplicitni cisla cestaku
- Riziko: dve objednavky se stejnym `order_no`.
- Mitigace: backend kontrola a automaticke prectislovani pri kolizi.

## R3: Slabe validace pred odeslanim
- Riziko: "schvaleny" cestak bez smysluplnych udaju.
- Mitigace: backend i frontend validace povinnych business poli.

## R4: Mojibake v cestine
- Riziko: rozbite znaky v notifikacich.
- Mitigace: oprava zdroje textu + normalizace na frontendu pro historicka data.

## R5: ERP callback nedorazi
- Riziko: ERP import probehne, app zustane ve starem stavu.
- Mitigace: provozni test callbacku po kazde sitove/DNS zmene + monitoring endpointu.
