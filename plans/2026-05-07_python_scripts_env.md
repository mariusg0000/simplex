# Mediu Python Scripting — ~/.simplexai/python/

## Motiv
Folder dedicat pentru scripturi Python personale, separat de proiectul Simplex.

## Setup realizat (2026-05-07)

### Structură
```
~/.simplexai/python/
├── .venv/               ← venv Python 3.11.15 (prin `uv venv --python 3.11`)
├── .python-version      ← "3.11"
└── activate.sh          ← source activate.sh
```

### Comenzi utilizare

```bash
# Activare
source ~/.simplexai/python/activate.sh

# Instalare pachete
uv pip install <pachet>

# Rulare directă (fără activare)
~/.simplexai/python/.venv/bin/python script.py
```

## Decizii
- **Python 3.11** — aceeași versiune ca proiectul Simplex
- **uv** ca package manager — rapid, deja disponibil pe sistem
- **Fără pip** în venv — uv pip înlocuiește pip-ul standard
