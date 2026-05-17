# Plan — Template Generation Skill (2026-05-17)

## Obiectiv

Un skill/sistem care generează `.md` template-uri în `src/templates/` din:
1. **Documente existente** (DOCX, XLSX, PDF) — reverse-engineer layout + style
2. **Discuții cu utilizatorul** — extrage preferințe conversational
3. **Vision** (faza 2) — analiză vizuală din screenshot-uri

Template-urile generate sunt `.md` semi-universale, reutilizabile de `create_pdf`, viitorul `create_doc`, etc.

---

## Arhitectură

### Locație template-uri
```
src/templates/
  invoice.md         ← generat manual sau automat
  report.md
  letter.md
  certificate.md
  simple.md
```

### Tool-uri implicate
- `load_template(name)` → citește `src/templates/{name}.md`
- Future: `create_template(source, ...)` → scrie în `src/templates/`

---

## Faza 1 — Skill pentru main agent (ghidare manuală)

**Tip:** Skill `.md` în `src/skills/` — main agentul primește instrucțiuni pas cu pas.

**Workflow:**
1. Main agentul discută cu userul despre document: tip, structură, culori, fonturi
2. Skill-ul îl ghidează să scrie manual un `.md` template în `src/templates/<name>.md`
3. Template-ul e scris cu `write_file` (main agent are acces direct)
4. Verificare: main agentul invocă `create_pdf` cu noul template

**Când se activează skill-ul:**
- Userul spune "creează un template nou", "adaugă un stil nou", "vreau să personalizez"
- Userul spune "generează template din documentul X"

**Structură `.md` cerută de skill:**

```markdown
# Nume Template

## Structură document
- Sectiunile documentului (antet, meta, tabel, footer)
- Ordinea și ierarhia

## Typografie
- Font sizes, weights, culori per element
- Heading hierarchy

## Layout
- Margini, dimensiune pagină
- Aliniamente, spațieri

## Reguli
- Instrucțiuni specifice template-ului
- Placeholder-uri de înlocuit
```

---

## Faza 2 — Sub-agent `create_template` (automat)

**Tip:** Agent `.md` în `src/agents/create_template.md`

**Workflow din document existent:**
1. Primește calea unui fișier: DOCX, XLSX, PDF
2. Folosește `run_python` + `python-docx`/`openpyxl`/`pypdf` pentru a extrage:
   - Fonturi (nume, size, bold/italic)
   - Culori (hex/rgb)
   - Structură (sections, headings, tables, columns)
   - Margini și layout
3. Rulează analiza statistică: ce font apare cel mai des, dimensiunea body text-ului
4. Generează `.md` template
5. Salvează fișierul (necesită acces la `src/templates/` — vezi secțiunea sandbox)

**Problemă sandbox:** Sub-agentul nu poate scrie direct în `src/templates/`. Soluții:
- Opțiunea A: Output prin `task_done(result="...")` → main agentul scrie template-ul
- Opțiunea B: Tool `write_template(name, content)` care scrie în `src/templates/` bypassînd sandbox-ul (similar cu `load_template`)
- Opțiunea C: Agentul scrie în session folder, main agentul copiază după terminare

Recomand: **Opțiunea B** — tool simetric cu `load_template`, scrie în path fix.

**Workflow din discuție:**
1. Main agentul discută preferințele cu userul
2. Trimite un sumar structurat către `create_template`:
   ```
   create_template(task="Creează un template invoice cu:
   - Header: logo stânga, info factură dreapta
   - Tabel cu coloanele: Nume, Qty, Preț, Total
   - Culori: #2C3E50 headere, #ECF0F1 rânduri alternante
   - Font: Calibri 11pt body, 16pt titlu")
   ```
3. Agentul generează `.md` și îl scrie în `src/templates/<name>.md`

---

## Faza 3 — Vision-based (future)

**Când:** După ce Faza 2 funcționează stabil.

**Workflow:**
1. Userul încarcă o imagine cu un document (fotografie, screenshot)
2. Main agentul trimite imaginea către un model cu vision (GPT-4o, Claude)
3. Modelul extrage layout, culori, fonturi, structură
4. Rezultatul e trimis la `create_template` care generează `.md`
5. Sau: skill-ul main agentului face totul direct cu vision

**Tool-uri necesare:**
- `read_file` (suport imagini) sau un tool `read_image` specializat
- Model LLM cu suport vision activat

---

## Stack tehnic

| Component | Tehnologie |
|---|---|
| Document parsing (DOCX) | `python-docx` |
| Document parsing (XLSX) | `openpyxl` |
| Document parsing (PDF) | `pypdf` |
| Color extraction | `PIL` / `colorthief` (opțional) |
| Template files | `.md` în `src/templates/` |
| Template loading | `load_template(name)` tool |
| Template creation | `write_template(name, content)` tool (Faza 2) |

---

## Dependințe între faze

```
Faza 1 (skill manual)
  │
  ├── Produce template-uri inițiale
  │
  └── Oferă specificația pentru Faza 2
         │
         ├── Faza 2 (agent automat)
         │     │
         │     ├── Poate genera orice template
         │     │
         │     └── Fundație pentru Faza 3
         │
         └── Faza 3 (vision) → consumă același output format
```

---

## Task breakdown

### Faza 1 — Skill main agent
- [ ] Creare `src/skills/create_template.md` (ghidare pas cu pas)
- [ ] Testare: generează un template nou din discuție
- [ ] Testare: creează PDF cu template-ul nou

### Faza 2 — Sub-agent + tool
- [ ] Tool `write_template(name, content)` — scrie în `src/templates/`
- [ ] Agent `src/agents/create_template.md` — analiză document → `.md`
- [ ] Verificare: template generat automat din DOCX existent
- [ ] Verificare: template generat din specificații

### Faza 3 — Vision
- [ ] Identificare model vision disponibil
- [ ] Adaptare workflow pentru imagini
- [ ] Testare: template din screenshot de document

---

## Riscuri

| Risc | Impact | Mitigare |
|---|---|---|
| Extrația fonturilor/culorilor din DOCX e incompletă | Mediu | Fallback la default-uri, raportare ce n-a putut fi extras |
| Template-ul generat nu produce același layout ca originalul | Scăzut | Template-ul e un starting point, nu o replică exactă |
| Vision face halucinații pe layout | Mediu | Verificare umană + regenerare din descriere |
| Sandbox blochează scrierea în `src/templates/` | Scăzut | Tool dedicat sau write prin main agent |
