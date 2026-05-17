# Factură / Invoice

## Structură document
- **Antet:** Logo stânga, nume companie, CIF, adresă, contact
- **Meta factură:** Număr factură, dată emitere, scadență, stare (originală/copie)
- **Billing:** Două coloane — Furnizor (stânga) și Client (dreapta) cu denumire + adresă completă + CIF
- **Tabel produse:** Coloane — #, Descriere, U.M., Cantitate, Preț unitar (fără TVA), Valoare (fără TVA)
- **Totaluri:** Subtotal, TVA (cota + valoare per cotă), Total de plată (cu TVA)
- **Footer:** Termeni de plată, cont bancar, semnătură, mentiune legală

## Typografie
- Titlu "FACTURĂ" / "INVOICE": 22pt, 700 weight, #1A252F, centrat, spațiu după 0.8em
- Antet companie: 11pt, regular, #333333, aliniat stânga
- Etichete meta factură: 9pt, 600 weight, #7F8C8D, uppercase
- Valori meta factură: 11pt, regular, #2C3E50
- Header tabel produse: 10pt, 700 weight, text alb (#FFFFFF) pe fundal #2C3E50
- Rânduri tabel: 10pt, regular, #333333; rândurile alternează cu #F8F9FA
- Totaluri: 11pt, 700 weight, #1A252F, aliniat dreapta
- Footer: 8pt, regular, #95A5A6, centrat

## Layout
- Dimensiune pagină: A4
- Margini: 2cm toate laturile
- Tabel produse: 100% lățime, bordură 1px solid #BDC3C7, padding celule 8pt 10pt
- Spațiere secțiuni: 0.8em între secțiuni
- Separator linie subțire (#BDC3C7, 1px) între antet și corp

## Reguli
- Nu modifica textul utilizatorului
- Suport Unicode complet (diacritice, simboluri valutare)
- Numerotează paginile "Page X of Y" jos centrat
- Dacă tabelul depășește o pagină, repetă header-ul tabelului (thead)
- Cota TVA implicită: 19% (dacă nu se specifică altfel)
- Moneda implicită: RON (dacă nu se specifică altfel)
