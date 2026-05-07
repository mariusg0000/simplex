# Plan: System Environment Detection in System Prompt

## Obiectiv
La fiecare pornire a aplicației, detectează utilitare moderne instalate pe sistem și injectează reguli de folosire în system prompt, interzicând echivalentele clasice.

## Tabelul utilitarelor

| Comandă | Descriere | Regulă | Interzice |
|---------|-----------|--------|-----------|
| `rg` | Fast text search in plain-text files | Use rg | grep |
| `fd` | Fast file/directory search by name | Use fd | find |
| `sd` | Find & Replace text | Use sd | sed |
| `bat` | File reader with line numbers and syntax highlighting | Use bat -n | cat |
| `mlr` | Structured CSV/TSV data processing | Use mlr --csv | awk, cut |
| `trash-put` | Move files to Recycle Bin | Use trash-put | rm |

## Logică
1. Definiți tabelul ca listă de tuple `(comandă, descriere, regulă, interzise)`
2. Startup: `shutil.which()` pentru fiecare comandă
3. Doar cele găsite apar în prompt — câte o linie
4. Cele negăsite sunt ignorate (nu se menționează)

## Structura finală a promptului
```
You are Simplex AI, a helpful office assistant.

SYSTEM ENVIRONMENT:
rg — Fast text search in plain-text files — Use rg. Forbidden: grep.
sd — Find & Replace text — Use sd. Forbidden: sed.

STRATEGIC GUIDELINES:
...
```

## Fișiere modificate
`src/ui/state.py` — singurul fișier. Adăugat `shutil`, tabelul, funcția `_build_env_section()`, cache.

## Cache
`_system_env_cache: Optional[str]` — populat la prima apelare. Un `refresh_env()` ulterior (comandă viitoare) invalidează.
