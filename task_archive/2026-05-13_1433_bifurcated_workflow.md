# Create_doc: bifurcat INLINE / TEMPLATE workflow

## Changes
- agent_description: Two modes — INLINE (descriere + text inline) / TEMPLATE (cale PDF + text nou)
- role_prompt: MODE 1 INLINE (3 bash calls max: write → weasyprint → done)
- role_prompt: MODE 2 TEMPLATE (5 bash calls max: 1 fitz extract → write HTML → weasyprint → verify → done)
- state.py: regula #5 simplificata pentru ambele moduri

## Rationale
Previous attempts to forbid fitz failed because main agent couldn't provide
sufficient layout detail inline. Solution: let create_doc use fitz BUT in a
single combined script (no piecemeal analysis).
