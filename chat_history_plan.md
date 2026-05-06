# Plan Implementare: Istoric Conversații cu SQLite și Sidebar (v2 - Dynamic Prompt)

## 1. Obiectiv
Implementarea unui sistem persistent de stocare a conversațiilor (chat history) folosind o bază de date SQLite, alături de un meniu lateral (sidebar) în interfața NiceGUI care să permită crearea de conversații noi și reluarea celor vechi.

## 2. Fișiere Afectate & Context
- **`src/db.py` (Nou)**: Logica de interacțiune cu baza de date SQLite (`chats.db`).
- **`main.py`**: Actualizare interfață (drawer lateral), managementul sesiunii (`current_session_id`) și logica de salvare/încărcare.

## 3. Pași de Implementare

### Pasul 3.1: Stratul de Bază de Date (SQLite)
- Crearea `src/db.py` pentru a gestiona tabela `sessions`.
- **Schema BD**: 
  - Tabela `sessions` (`id` TEXT PK, `title` TEXT, `messages` TEXT (JSON), `updated_at` DATETIME).
- **Logica de Filtrare**: Metoda de salvare va filtra/elimina mesajele cu `role: "system"` înainte de serializare.

### Pasul 3.2: Managementul Sesiunilor în `main.py`
- Variabila globală `current_session_id`.
- `start_new_chat()`: Creează o sesiune nouă, resetează UI-ul și inițializează `messages` cu promptul de sistem actual.
- `load_chat(session_id)`: Încarcă dialogul din BD, **injectează la început promptul de sistem actual** și redesenează chat-ul.
- `save_current_chat()`: Salvează istoricul curent (fără system prompt) după fiecare răspuns AI.

### Pasul 3.3: Actualizarea Interfeței (UI)
- Adăugarea `ui.left_drawer()` cu:
  - Buton **"+ New Chat"**.
  - Listă cronologică a chaturilor vechi.
- Adăugarea unui buton "hamburger" în header pentru toggle la drawer.

## 4. Validare & Testare
- Verificarea creării `chats.db`.
- Testarea reluării unei conversații după restartul aplicației.
- Verificarea faptului că modificarea promptului de sistem se aplică și pe conversațiile vechi.
