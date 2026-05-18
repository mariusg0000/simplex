# Certificate / Certificat

## Structură document
- **Fundal:** Chenar decorativ (border dublu sau linie groasă aurie #C9A93C) pe toată pagina
- **Sigiliu/Logo sus centrat** (opțional — imagine base-64)
- **Titlu:** "CERTIFICAT" / "CERTIFICATE"
- **Linie decorativă** sub titlu (aurie #C9A93C)
- **Corp certificare:** "Se certifică prin prezenta că" + nume persoană + text descriptiv
- **Detalii:** Dată eliberare, număr înregistrare, valabilitate (dacă e cazul)
- **Linie semnături:** Două coloane — stânga: semnătură emitent, dreapta: ștampilă
- **Footer:** Organism emitent, adresă, contact

## Typografie
- Titlu "CERTIFICAT": 28pt, 700 weight, #1A252F, centrat, letter-spacing 4pt
- Linie decorativă: 2px solid #C9A93C, lățime 60%, centrată
- Corp certificare: 13pt, 400 weight, #2C3E50, centrat, line-height 1.6
- Nume persoană: 18pt, 700 weight, #C9A93C (auriu), centrat
- Text descriptiv: 12pt, 400 weight, #555555, centrat
- Detalii (data, nr. înregistrare): 10pt, 400 weight, #7F8C8D, centrat
- Etichete semnături: 10pt, 400 weight, #7F8C8D (sub linia de semnătură)
- Footer: 9pt, 400 weight, #95A5A6, centrat

## Layout
- Dimensiune pagină: A4 landscape (opțional, default portrait)
- Margini: 1.5cm toate laturile
- Chenar: border 3px solid #C9A93C, padding 1cm, border-radius 4pt
- Spațiere titlu-corp: 1.5cm
- Linii semnătură: 5cm lățime fiecare, border-bottom 1.5px solid #333333, spațiu între coloane 3cm
- Tot conținutul pe o singură pagină (page-break-inside: avoid)
- Centrare verticală a conținutului pe pagină
- Padding interior al chenarului: 1.5cm

## Reguli
- Nu modifica textul utilizatorului
- Suport Unicode complet
- O SINGURĂ PAGINĂ — certificatul nu trebuie să se întindă pe mai multe pagini
- Chenarul auriu (#C9A93C) este esențial pentru aspectul formal
- Se evită culorile închise pe fundal (doar text, nu fundaluri pline)

## Compatibilitate Office (DOCX)
- Font: Times New Roman (ceremonial). Titlu: 28pt Bold. Corp: 13pt.
- Chenar: tabel cu o celulă, bordură 3pt #C9A93C, padding 1cm.
- Titlu "CERTIFICAT": centrat, `letter-spacing` aproximat cu spații între caractere.
- Nume persoană: 18pt Bold #C9A93C (direct Run.color.rgb).
- Linii semnătură: tabel 2 coloane cu `bottom_border`.
- O singură pagină: setează `section.page_height = section.page_width` (landscape).
