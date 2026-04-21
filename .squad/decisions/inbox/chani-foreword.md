### Decision: No AI-Generated Content Posing as Author Text
**Author:** Chani  
**Date:** 2026-04-18  
**Status:** Active  
**Issue:** #64

The pipeline must never use the LLM to generate content that could be mistaken for author-written material (forewords, prefaces, introductions, etc.). The former `_generate_foreword()` function was removed. Instead, a factual "Translator's Note" is stored in `manuscript.metadata["translator_note"]` — this is a short, honest disclosure about the AI translation process. Both ePub and PDF export stages render this note under the heading "Translator's Note".

**Key principle:** AI-generated text must always be clearly distinguishable from original source content. Fabricating literary-style front matter is a content integrity violation.
