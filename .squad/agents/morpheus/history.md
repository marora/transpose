# Morpheus — Lead History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Stilgar (Dune cast) — see .squad/agents/_alumni/stilgar/history.md for accumulated knowledge

## Learnings
(Recast from Stilgar — Matrix universe. All prior knowledge preserved in alumni archive.)
- 2026-05-20: Current pipeline is book-centric in PostgreSQL + Blob, not workspace-centric. `books` carries only core identity/status (`title`, `author`, `source_language`, `source_hash`, `source_blob_uri`, `status`, `page_count`) while stage artifacts live across `pages`, `chunks`, `translations`, `glossaries`, `manuscripts`, `pipeline_state`, and `pipeline_jobs`; there is no first-class per-book artifact manifest or source URL field.
- 2026-05-20: Repo still contains ad hoc sample and generated artifacts at the root (`Osho - विज्ञान भैरव तंत्र 1.pdf`, `Test_Hindi_Book.pdf`, `Osho_VBT_translated.pdf`, `Test_Hindi_Book_final.pdf`, etc.), and validation/export scripts also write outputs to repo root. Good for fixtures and demos; wrong as the long-term archive/storage primitive.
- 2026-05-20: Decision — add a first-class Book Workspace abstraction backed by storage, with a folder/object-prefix layout as one materialization. Use hybrid storage: keep code plus small reviewable metadata/reports in Git, but store heavy binaries (source PDFs, translated PDFs/ePubs, OCR raw, future audio) in Azure Blob/ADLS Gen2. Public archive, if desired, should be delivered via a static index/front end over blob assets, not by bloating the source repo.
- 2026-05-20: Niobe (Product Manager) joined the team. Product framing for the workspace question is now Niobe's first task before any build. Architecture recommendation is complete; implementation gated on product brief (audience, success metrics, MVP scope).
