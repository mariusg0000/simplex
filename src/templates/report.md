# Report / Raport

## Structură document
- **Copertă (prima pagină):** Titlu raport, subtitlu (dacă există), autor, dată, versiune
- **Cuprins** (opțional, doar dacă documentul depășește 3 pagini)
- **Rezumat executiv:** 2-3 paragrafe cu concluziile principale
- **Capitole numerotate:** Fiecare capitol cu titlu, paragrafe, subcapitole (numerotare 1, 1.1, 1.1.1)
- **Tabele și figuri:** numerotate, cu titlu deasupra (Table 1: ...) sau dedesubt (Figure 1: ...)
- **Concluzii:** secțiune separată înainte de anexe
- **Anexe:** numerotate (Anexa A, Anexa B...)

## Typografie
- Titlu copertă: 26pt, 700 weight, #1A252F, centrat
- Subtitlu: 16pt, 400 weight, #7F8C8D, centrat
- Autor/dată: 11pt, regular, #95A5A6, centrat
- Headere capitole (h1): 18pt, 700 weight, #1A252F, cu linie subțire dedesubt
- Subheadere (h2): 14pt, 600 weight, #2C3E50
- Sub-subheadere (h3): 12pt, 600 weight, #2C3E50
- Body text: 11pt, 400 weight, #333333, line-height 1.6
- Rezumat executiv: 11pt, 400 weight, #555555, fundal #F8F9FA, padding 1em
- Header tabel: 10pt, 700 weight, #2C3E50 pe #ECF0F1
- Body tabel: 10pt, 400 weight, #333333

## Layout
- Dimensiune pagină: A4
- Margini: 2.5cm stânga-dreapta, 2cm sus-jos
- Primă pagină: margine sus 4cm (pentru copertă)
- Tabele: 100% lățime, 1px #BDC3C7, padding 6pt 8pt
- Liste: bullet numeric pentru capitole, disc pentru subliste
- Spațiere între paragrafe: 0.5em
- Page break înainte de fiecare capitol nou (h1)
- Numerotare pagini: "— X —" jos centrat, începând de la cuprins

## Reguli
- Nu modifica textul utilizatorului
- Suport Unicode complet
- Cuprinsul se generează doar la cerere explicită
- Graficele/figurile se plasează între paragrafe, nu se rup pe pagini
- Referințele bibliografice se formatează ca note de subsol

## Compatibilitate Office (DOCX)
- Font: Calibri (body 11pt). Headere: Calibri Bold (Heading 1: 18pt, Heading 2: 14pt, Heading 3: 12pt).
- Folosește stilurile native `Heading 1`, `Heading 2`, `Heading 3` din python-docx — nu raw XML.
- Cuprins: generabil din heading styles (Word automat).
- Copertă: `PageBreak` înainte de pagina 2, `first_page` header gol.
- Numerotare pagini: câmp `Page` / `SectionPages` în footer.
