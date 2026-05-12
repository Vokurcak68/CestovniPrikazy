/*
  Schvalene zadosti o vycestovani, ke kterym neexistuje cestovni prikaz.
  Poznamka:
  - Tento dotaz pocita s tim, ze data z app DB jsou zrcadlena do MSSQL tabulek
    se stejnou logikou identifikatoru (request_id).
  - Pokud mate jine nazvy tabulek/sloupcu ve stagingu, upravte jen FROM/JOIN cast.
*/

SELECT
    r.id,
    r.request_no,
    r.owner_user_id,
    r.approver_user_id,
    r.destination,
    r.start_at,
    r.end_at,
    r.purpose,
    r.approved_at
FROM travel_request r
LEFT JOIN travel_order o
    ON o.travel_request_id = r.id
WHERE r.status = 'approved'
  AND o.id IS NULL
ORDER BY r.approved_at, r.request_no;
