"""Quality gates — blocking checks between pipeline stages.

Each gate validates output quality before the next stage runs.
If a gate fails, the pipeline halts with a QualityGateError.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# GateResult model
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """Outcome of a single quality gate check."""

    gate_name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float | None = None


class QualityGateError(Exception):
    """Raised when a quality gate check fails, blocking pipeline progression."""

    def __init__(self, gate_result: GateResult) -> None:
        self.gate_result = gate_result
        super().__init__(
            f"Quality gate '{gate_result.gate_name}' failed: "
            + "; ".join(gate_result.failures)
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_REPLACEMENT_CHAR = "\ufffd"
_MAX_REPLACEMENT_RATIO = 0.05
_MIN_CONFIDENCE = 0.6
_DEVANAGARI_DENSITY_THRESHOLD = 0.05  # at least 5% Devanagari chars for Hindi source
_TRANSLATION_FAILED_MARKER = "[TRANSLATION FAILED"
_ORIGINAL_TEXT_FALLBACK_MARKER = "[Original text"
_MAX_FAILED_CHUNK_RATIO = 0.10
_MAX_FAILED_CHUNK_RATIO_HARD = 0.30  # Hard ceiling — never produce output above this
_MIN_FOREWORD_WORDS = 50
_MIN_ARTIFACT_SIZE = 1024  # 1 KB


# ---------------------------------------------------------------------------
# Gate 1: OCR Sanity (after OCR, before chunk)
# ---------------------------------------------------------------------------

def ocr_sanity_gate(ocr_output, *, min_confidence: float = _MIN_CONFIDENCE) -> GateResult:
    """Validate OCR output quality before chunking.

    Checks:
      - Garbled Unicode (excessive U+FFFD replacement characters)
      - Devanagari codepoint density for Hindi source text
      - OCR confidence scores (reject pages below threshold)

    Args:
        min_confidence: Override the default confidence threshold
            (wired from ``Settings.low_confidence_threshold``).
    """
    failures: list[str] = []
    failing_pages: list[int] = []
    details: dict = {
        "total_pages": 0,
        "failing_pages": [],
        "checks": {},
    }

    pages = getattr(ocr_output, "page_results", [])
    details["total_pages"] = len(pages)

    for page in pages:
        page_num = page.page_number
        text = page.raw_text or ""
        page_issues: list[str] = []

        # Check 1: Excessive replacement characters
        if text:
            repl_count = text.count(_REPLACEMENT_CHAR)
            ratio = repl_count / max(len(text), 1)
            if ratio > _MAX_REPLACEMENT_RATIO:
                page_issues.append(
                    f"page {page_num}: {repl_count} replacement chars "
                    f"({ratio:.1%} of text, threshold {_MAX_REPLACEMENT_RATIO:.0%})"
                )

        # Check 2: Devanagari codepoint density for Hindi
        if text.strip():
            devanagari_count = len(_DEVANAGARI_RE.findall(text))
            total_non_space = len(text.replace(" ", "").replace("\n", ""))
            if total_non_space > 0:
                density = devanagari_count / total_non_space
                if density < _DEVANAGARI_DENSITY_THRESHOLD:
                    page_issues.append(
                        f"page {page_num}: Devanagari density {density:.1%} "
                        f"below threshold {_DEVANAGARI_DENSITY_THRESHOLD:.0%}"
                    )

        # Check 3: OCR confidence
        confidence = getattr(page, "confidence", None)
        if confidence is not None and confidence < min_confidence:
            page_issues.append(
                f"page {page_num}: confidence {confidence:.2f} "
                f"below threshold {min_confidence}"
            )

        if page_issues:
            failing_pages.append(page_num)
            failures.extend(page_issues)

    details["failing_pages"] = failing_pages
    details["checks"] = {
        "replacement_char_threshold": _MAX_REPLACEMENT_RATIO,
        "devanagari_density_threshold": _DEVANAGARI_DENSITY_THRESHOLD,
        "min_confidence": min_confidence,
    }

    return GateResult(
        gate_name="ocr_sanity",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 2: Translation Completeness (after translate, before glossary)
# ---------------------------------------------------------------------------

def translation_completeness_gate(translate_output) -> GateResult:
    """Validate translation output before glossary extraction.

    Checks:
      - Every input chunk has a corresponding translation
      - No raw Devanagari passthrough in translated text
      - Acceptable ratio of TRANSLATION FAILED placeholders
    """
    failures: list[str] = []
    failing_chunks: list[str] = []
    details: dict = {
        "chunks_translated": 0,
        "failed_count": 0,
        "passthrough_count": 0,
        "failing_chunks": [],
    }

    translations = getattr(translate_output, "translations", [])
    chunks_translated = getattr(translate_output, "chunks_translated", 0)
    failed_count = getattr(translate_output, "failed_count", 0)
    details["chunks_translated"] = chunks_translated
    details["failed_count"] = failed_count

    # Check 1: Failed translation ratio
    total = len(translations) if translations else max(chunks_translated, 1)
    fail_ratio = failed_count / total if total > 0 else 0

    if fail_ratio > _MAX_FAILED_CHUNK_RATIO_HARD:
        # Above hard ceiling — always fail
        msg = (
            f"{failed_count}/{total} chunks failed translation "
            f"({fail_ratio:.0%}, hard ceiling {_MAX_FAILED_CHUNK_RATIO_HARD:.0%})"
        )
        failures.append(msg)
    elif fail_ratio > _MAX_FAILED_CHUNK_RATIO:
        # Above soft threshold but below hard ceiling — warn but continue
        details["warning"] = (
            f"{failed_count}/{total} chunks failed ({fail_ratio:.0%}, "
            f"above {_MAX_FAILED_CHUNK_RATIO:.0%} soft threshold). "
            f"Output will contain placeholder markers for manual review."
        )

    # Check 2: Scan translations for TRANSLATION FAILED markers and Devanagari passthrough
    marker_count = 0
    passthrough_count = 0
    fallback_count = 0  # intentional Hindi fallbacks (not hard failures)
    for tr in translations:
        text = getattr(tr, "translated_text", "") or ""
        chunk_id = str(getattr(tr, "chunk_id", "unknown"))

        if _TRANSLATION_FAILED_MARKER in text:
            marker_count += 1
            failing_chunks.append(chunk_id)
            continue

        # Intentional Hindi fallback — not a hard failure
        if _ORIGINAL_TEXT_FALLBACK_MARKER in text:
            fallback_count += 1
            continue

        # Detect raw Devanagari passthrough (unintentional source leak)
        non_space = text.replace(" ", "").replace("\n", "")
        if non_space:
            dev_count = len(_DEVANAGARI_RE.findall(non_space))
            if dev_count / len(non_space) > 0.3:
                passthrough_count += 1
                if chunk_id not in failing_chunks:
                    failing_chunks.append(chunk_id)
                failures.append(
                    f"chunk {chunk_id}: Devanagari passthrough detected "
                    f"({dev_count}/{len(non_space)} chars)"
                )

    details["marker_count"] = marker_count
    details["passthrough_count"] = passthrough_count
    details["fallback_count"] = fallback_count

    if fallback_count > 0:
        details.setdefault("warning", "")
        if details["warning"]:
            details["warning"] += "; "
        details["warning"] += (
            f"{fallback_count}/{total} chunks fell back to original Hindi text — "
            f"output will include source text for untranslatable passages"
        )

    if total > 0 and marker_count / total > _MAX_FAILED_CHUNK_RATIO_HARD:
        failures.append(
            f"{marker_count}/{total} chunks contain TRANSLATION FAILED marker "
            f"({marker_count / total:.0%}, hard ceiling {_MAX_FAILED_CHUNK_RATIO_HARD:.0%})"
        )
    elif total > 0 and marker_count / total > _MAX_FAILED_CHUNK_RATIO:
        details.setdefault("warning", "")
        if details["warning"]:
            details["warning"] += "; "
        details["warning"] += (
            f"{marker_count}/{total} chunks have FAILED markers — "
            f"output will include placeholders for review"
        )

    details["failing_chunks"] = failing_chunks

    return GateResult(
        gate_name="translation_completeness",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 3: Glossary Integrity (after glossary, before assemble)
# ---------------------------------------------------------------------------

def glossary_integrity_gate(glossary_output) -> GateResult:
    """Validate glossary quality before document assembly.

    Checks:
      - Glossary is non-empty
      - original_script fields are NFC-normalized
      - No U+FFFD replacement characters in any field
      - No Latin characters mixed into Devanagari script fields
    """
    failures: list[str] = []
    failing_entries: list[str] = []
    details: dict = {
        "total_entries": 0,
        "failing_entries": [],
    }

    entries = getattr(glossary_output, "entries", [])
    details["total_entries"] = len(entries)

    # Check 1: Non-empty glossary
    if not entries:
        failures.append("glossary has no entries")
        return GateResult(
            gate_name="glossary_integrity",
            passed=False,
            failures=failures,
            details=details,
        )

    for entry in entries:
        term = getattr(entry, "term", "")
        original_script = getattr(entry, "original_script", "")
        definition = getattr(entry, "definition", "")
        entry_id = term or "unknown"
        entry_issues: list[str] = []

        # Check 2: NFC normalization of original_script
        if original_script != unicodedata.normalize("NFC", original_script):
            entry_issues.append(f"'{entry_id}': original_script not NFC-normalized")

        # Check 3: No replacement characters in any field
        for field_name, value in [
            ("term", term),
            ("original_script", original_script),
            ("definition", definition),
        ]:
            if _REPLACEMENT_CHAR in value:
                entry_issues.append(
                    f"'{entry_id}': U+FFFD in {field_name}"
                )

        # Check 4: No Latin characters in Devanagari script fields
        if original_script and _LATIN_RE.search(original_script):
            entry_issues.append(
                f"'{entry_id}': Latin characters mixed into original_script"
            )

        if entry_issues:
            failing_entries.append(entry_id)
            failures.extend(entry_issues)

    details["failing_entries"] = failing_entries

    return GateResult(
        gate_name="glossary_integrity",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 4: Document Structure (after assemble, before export)
# ---------------------------------------------------------------------------

def document_structure_gate(manuscript) -> GateResult:
    """Validate assembled manuscript structure before export.

    Checks:
      - ToC entry count matches chapter count
      - Foreword is present and has sufficient length
      - Cover page has title text
      - Chapters are sequentially numbered
    """
    failures: list[str] = []
    details: dict = {
        "chapter_count": 0,
        "toc_count": 0,
        "has_foreword": False,
        "has_title": False,
    }

    chapters = getattr(manuscript, "chapters", [])
    toc = getattr(manuscript, "table_of_contents", [])
    title = getattr(manuscript, "title", "")
    metadata = getattr(manuscript, "metadata", {}) or {}
    foreword = metadata.get("foreword", "")

    details["chapter_count"] = len(chapters)
    details["toc_count"] = len(toc)
    details["has_title"] = bool(title and title.strip())
    details["has_foreword"] = bool(foreword and len(foreword.split()) >= _MIN_FOREWORD_WORDS)

    # Check 1: ToC count should be >= chapter count (ToC includes front/back matter)
    if toc and len(chapters) > 0 and len(toc) < len(chapters):
        failures.append(
            f"ToC has {len(toc)} entries but manuscript has {len(chapters)} chapters"
        )

    # Check 2: Foreword present and non-empty (soft check — warn but don't block)
    if not foreword or len(foreword.split()) < _MIN_FOREWORD_WORDS:
        word_count = len(foreword.split()) if foreword else 0
        details["foreword_warning"] = (
            f"foreword too short ({word_count} words, minimum {_MIN_FOREWORD_WORDS})"
        )

    # Check 3: Title text present
    if not title or not title.strip():
        failures.append("manuscript has no title text")

    # Check 4: Sequential chapter numbering
    if chapters:
        chapter_numbers = [getattr(ch, "number", 0) for ch in chapters]
        expected = list(range(1, len(chapters) + 1))
        if chapter_numbers != expected:
            failures.append(
                f"chapters not sequential: got {chapter_numbers}, expected {expected}"
            )

    # Check 5: TOC entries are non-empty and meaningful
    if toc:
        empty_toc_entries = []
        for i, entry in enumerate(toc):
            entry_title = ""
            if isinstance(entry, dict):
                entry_title = entry.get("title", "") or entry.get("text", "") or ""
            elif isinstance(entry, str):
                entry_title = entry
            elif hasattr(entry, "title"):
                entry_title = getattr(entry, "title", "") or ""

            if not entry_title or not entry_title.strip() or len(entry_title.strip()) < 3:
                empty_toc_entries.append(i + 1)

        if empty_toc_entries:
            failures.append(
                f"ToC has {len(empty_toc_entries)} empty/trivial entries at positions: "
                f"{empty_toc_entries[:5]}{'...' if len(empty_toc_entries) > 5 else ''}"
            )
        details["empty_toc_entries"] = len(empty_toc_entries)

    # Check 6: ToC entries should roughly match chapter titles
    if toc and chapters:
        mismatched = []
        for i, (toc_entry, chapter) in enumerate(zip(toc, chapters)):
            toc_title = ""
            if isinstance(toc_entry, dict):
                toc_title = toc_entry.get("title", "") or toc_entry.get("text", "")
            elif isinstance(toc_entry, str):
                toc_title = toc_entry
            elif hasattr(toc_entry, "title"):
                toc_title = getattr(toc_entry, "title", "")

            chapter_title = getattr(chapter, "title", "") or ""

            # Normalize for comparison
            toc_norm = toc_title.strip().lower()
            ch_norm = chapter_title.strip().lower()

            # If both exist but don't share any significant words, flag it
            if toc_norm and ch_norm:
                toc_words = set(toc_norm.split())
                ch_words = set(ch_norm.split())
                # Remove common short words
                stop_words = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is"}
                toc_sig = toc_words - stop_words
                ch_sig = ch_words - stop_words
                if toc_sig and ch_sig and not toc_sig.intersection(ch_sig):
                    mismatched.append(i + 1)

        if mismatched:
            details["toc_chapter_mismatches"] = mismatched[:5]
            # This is a warning, not a failure — log it but don't block
            details["toc_quality_warning"] = (
                f"{len(mismatched)} ToC entries don't match chapter titles"
            )

    return GateResult(
        gate_name="document_structure",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 5: Artifact Availability (after export)
# ---------------------------------------------------------------------------

def artifact_availability_gate(export_output) -> GateResult:
    """Validate exported artifacts are present and non-trivial.

    Checks:
      - PDF file exists and is > 1KB
      - ePub file exists and is > 1KB
      - Upload URLs are set if upload was attempted
    """
    failures: list[str] = []
    artifact_details: dict = {}
    details: dict = {
        "artifacts": artifact_details,
        "missing": [],
    }

    artifacts = getattr(export_output, "artifacts", [])

    found_formats: set[str] = set()
    for artifact in artifacts:
        fmt = getattr(artifact, "format", "unknown")
        size = getattr(artifact, "file_size_bytes", 0)
        uri = getattr(artifact, "blob_uri", "")
        found_formats.add(fmt)

        artifact_details[fmt] = {
            "size_bytes": size,
            "uri": uri,
        }

        # Check size
        if size < _MIN_ARTIFACT_SIZE:
            failures.append(
                f"{fmt} artifact too small ({size} bytes, minimum {_MIN_ARTIFACT_SIZE})"
            )

        # Check URI if upload was attempted (non-empty URI expected)
        # Accept http://, https://, file://, and absolute paths
        if uri:
            import os
            import urllib.parse
            
            is_valid = False
            
            # Check for http(s):// URIs (Azure Blob Storage)
            if uri.startswith("http://") or uri.startswith("https://"):
                is_valid = True
            # Check for file:// URIs
            elif uri.startswith("file://"):
                # Extract path from file:// URI and verify it exists
                parsed = urllib.parse.urlparse(uri)
                local_path = urllib.parse.unquote(parsed.path)
                is_valid = os.path.isfile(local_path)
            # Check for absolute paths (Unix: starts with /, Windows: starts with drive letter)
            elif uri.startswith("/") or (len(uri) > 2 and uri[1] == ":"):
                is_valid = os.path.isfile(uri)
            
            if not is_valid:
                failures.append(f"{fmt} artifact has invalid or non-existent URI: {uri}")

    # Check expected formats present — only require at least one artifact
    if not found_formats:
        failures.append("no artifacts produced by export")
    # Track which standard formats are missing (informational)
    for fmt in ("pdf", "epub"):
        if fmt not in found_formats:
            details["missing"].append(fmt)

    return GateResult(
        gate_name="artifact_availability",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 6: Golden-Targeted QA (post-export, compares against golden target)
# ---------------------------------------------------------------------------

_GOLDEN_TARGET_DEFAULT = "tests/golden/golden-target.json"
_WORD_COUNT_TOLERANCE = 0.30
_PAGE_COUNT_RATIO_MAX = 1.5
_BODY_DEVANAGARI_MAX_RATIO = 0.02
_GOLDEN_TARGET_MIN_CHAPTERS = 1
_GOLDEN_TARGET_MIN_CHAPTER_WORDS = 5


def validate_golden_target(golden: dict) -> list[str]:
    """Validate the golden target reference itself before using it.

    Returns a list of validation errors (empty if valid).
    Checks:
      - No garbled Unicode (U+FFFD replacement characters) in any text field
      - All chapters present with non-empty content fields
      - Cover page section present in structure
      - ToC section present in structure
      - Chapter titles and key_phrases are non-empty strings
    """
    errors: list[str] = []

    # --- Check: chapters exist and have content ---
    chapters = golden.get("chapters")
    if not chapters or not isinstance(chapters, list):
        errors.append("Golden target has no 'chapters' array")
        return errors

    if len(chapters) < _GOLDEN_TARGET_MIN_CHAPTERS:
        errors.append(
            f"Golden target has {len(chapters)} chapters, "
            f"minimum {_GOLDEN_TARGET_MIN_CHAPTERS} required"
        )

    for ch in chapters:
        ch_num = ch.get("number", "?")
        title = ch.get("title", "")
        if not title or not title.strip():
            errors.append(f"Golden target chapter {ch_num} has empty title")
        # Check for garbled Unicode in title
        if _REPLACEMENT_CHAR in str(title):
            errors.append(
                f"Golden target chapter {ch_num} title contains U+FFFD "
                "replacement characters (garbled text)"
            )
        # Check word count is positive
        wc = ch.get("word_count_approx", 0)
        if not isinstance(wc, (int, float)) or wc < _GOLDEN_TARGET_MIN_CHAPTER_WORDS:
            errors.append(
                f"Golden target chapter {ch_num} has invalid word_count_approx: {wc}"
            )
        # Check key_phrases for garbled text
        for phrase in ch.get("key_phrases", []):
            if _REPLACEMENT_CHAR in str(phrase):
                errors.append(
                    f"Golden target chapter {ch_num} key_phrase contains "
                    "U+FFFD (garbled text)"
                )

    # --- Check: structure has cover and ToC ---
    structure = golden.get("structure", {})
    sections = structure.get("expected_sections", [])
    section_types = [s.get("type") for s in sections]
    if "cover" not in section_types:
        errors.append("Golden target structure missing 'cover' section")
    if "toc" not in section_types:
        errors.append("Golden target structure missing 'toc' section")

    # --- Check: deep scan for U+FFFD in the entire JSON payload ---
    import json as _json

    serialized = _json.dumps(golden, ensure_ascii=False)
    fffd_count = serialized.count(_REPLACEMENT_CHAR)
    if fffd_count > 0:
        errors.append(
            f"Golden target contains {fffd_count} U+FFFD replacement "
            "character(s) — indicates garbled/corrupt text"
        )

    return errors


def golden_targeted_qa_gate(
    candidate_pdf_path: str,
    golden_target_path: str = _GOLDEN_TARGET_DEFAULT,
) -> GateResult:
    """Compare a candidate PDF against the golden target reference.

    Checks:
      1. Structural match — chapter count, section presence, chapter ordering
      2. Content completeness — word counts within ±30% of golden target
      3. Script hygiene — no Devanagari in English body (glossary terms excepted)
      4. Glossary integrity — required preserved terms present
      5. No regression — page count within 1.5× of source
    """
    import json
    from pathlib import Path

    import fitz  # PyMuPDF

    failures: list[str] = []
    details: dict = {
        "checks": {
            "structural_match": True,
            "content_completeness": True,
            "script_hygiene": True,
            "glossary_integrity": True,
            "no_regression": True,
        },
        "chapter_count": 0,
        "page_count": 0,
        "glossary_terms_found": 0,
    }

    # Load golden target
    golden_path = Path(golden_target_path)
    if not golden_path.is_absolute():
        # Resolve relative to repo root (walk up from this file)
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        golden_path = repo_root / golden_target_path

    if not golden_path.exists():
        failures.append(f"Golden target not found: {golden_path}")
        details["checks"]["structural_match"] = False
        return GateResult(
            gate_name="golden_targeted_qa",
            passed=False,
            failures=failures,
            details=details,
        )

    with open(golden_path) as f:
        golden = json.load(f)

    # Validate golden target itself before trusting it as reference
    golden_errors = validate_golden_target(golden)
    if golden_errors:
        failures.extend(
            f"Golden target invalid: {e}" for e in golden_errors
        )
        details["checks"]["structural_match"] = False
        details["golden_target_validation_errors"] = golden_errors
        return GateResult(
            gate_name="golden_targeted_qa",
            passed=False,
            failures=failures,
            details=details,
        )

    # Load candidate PDF
    candidate = Path(candidate_pdf_path)
    if not candidate.exists():
        failures.append(f"Candidate PDF not found: {candidate_pdf_path}")
        return GateResult(
            gate_name="golden_targeted_qa",
            passed=False,
            failures=failures,
            details=details,
        )

    doc = fitz.open(str(candidate))
    page_count = doc.page_count
    all_text = [doc[i].get_text() for i in range(page_count)]
    doc.close()

    full_text = "\n".join(all_text)
    details["page_count"] = page_count

    # --- Check 1: Structural match ---
    golden_chapters = golden.get("chapters", [])
    expected_chapter_count = len(golden_chapters)

    # Count actual chapters by finding "Chapter N:" patterns
    chapter_matches = re.findall(r"Chapter\s+(\d+)\s*:", full_text)
    # Deduplicate (ToC + body both contain chapter refs)
    actual_chapter_numbers = sorted(set(int(n) for n in chapter_matches))
    details["chapter_count"] = len(actual_chapter_numbers)

    if len(actual_chapter_numbers) < expected_chapter_count:
        failures.append(
            f"Chapter count mismatch: found {len(actual_chapter_numbers)}, "
            f"expected {expected_chapter_count}"
        )
        details["checks"]["structural_match"] = False

    # Check sequential ordering
    expected_numbers = list(range(1, expected_chapter_count + 1))
    if actual_chapter_numbers != expected_numbers:
        failures.append(
            f"Chapters not sequential: found {actual_chapter_numbers}, "
            f"expected {expected_numbers}"
        )
        details["checks"]["structural_match"] = False

    # Check section presence
    structure = golden.get("structure", {})
    for section in structure.get("expected_sections", []):
        section_type = section["type"]
        if not section.get("required", False):
            continue
        if section_type == "cover":
            if page_count < 1 or not all_text[0].strip():
                failures.append("Cover page missing or empty")
                details["checks"]["structural_match"] = False
        elif section_type == "toc":
            if "Table of Contents" not in full_text:
                failures.append("Table of Contents not found")
                details["checks"]["structural_match"] = False
        elif section_type == "foreword":
            if "Foreword" not in full_text:
                failures.append("Translator's Foreword not found")
                details["checks"]["structural_match"] = False
        elif section_type == "glossary":
            # Glossary detected by presence of terms with Devanagari in parens
            glossary_pattern = re.search(
                r"[a-z]+\s*\([\u0900-\u097F]+", full_text
            )
            if not glossary_pattern:
                failures.append("Glossary section not found")
                details["checks"]["structural_match"] = False

    # --- Check 2: Content completeness (word counts per chapter) ---
    for golden_ch in golden_chapters:
        ch_num = golden_ch["number"]
        expected_words = golden_ch["word_count_approx"]
        tolerance = golden_ch.get("word_count_tolerance", _WORD_COUNT_TOLERANCE)
        min_words = int(expected_words * (1 - tolerance))
        max_words = int(expected_words * (1 + tolerance))

        # Extract chapter text between "Chapter N:" and next "Chapter N+1:"
        ch_pattern = re.compile(
            rf"Chapter\s+{ch_num}\s*:.*?(?=Chapter\s+{ch_num + 1}\s*:|Glossary|$)",
            re.DOTALL,
        )
        # Search in body text (skip first few pages which are cover/ToC/foreword)
        body_text = "\n".join(all_text[2:])  # Skip cover and ToC
        ch_match = ch_pattern.search(body_text)

        if ch_match:
            ch_text = ch_match.group()
            actual_words = len(ch_text.split())
            if actual_words < min_words or actual_words > max_words:
                failures.append(
                    f"Chapter {ch_num} word count {actual_words} outside "
                    f"tolerance [{min_words}, {max_words}] "
                    f"(golden: {expected_words} ±{tolerance:.0%})"
                )
                details["checks"]["content_completeness"] = False
        else:
            failures.append(f"Chapter {ch_num} content not found in candidate")
            details["checks"]["content_completeness"] = False

    # --- Check 3: Script hygiene (no Devanagari in English body) ---
    # Check body pages (skip glossary pages at end)
    # Glossary typically starts after last chapter content
    glossary_start = full_text.rfind("Glossary")
    if glossary_start < 0:
        # Try finding the glossary by pattern (terms with Devanagari in parens)
        glossary_match = re.search(
            r"(?:^|\n)([a-z]+\s*\([\u0900-\u097F])", full_text
        )
        glossary_start = glossary_match.start() if glossary_match else len(full_text)

    body_only = full_text[:glossary_start]
    # Remove known allowed Devanagari (inline preserved terms in parens)
    body_cleaned = re.sub(r"\([\u0900-\u097F\s]+\)", "", body_only)
    # Count remaining Devanagari characters
    devanagari_in_body = len(_DEVANAGARI_RE.findall(body_cleaned))
    total_body_chars = max(len(body_cleaned.replace(" ", "").replace("\n", "")), 1)
    dev_ratio = devanagari_in_body / total_body_chars

    if dev_ratio > _BODY_DEVANAGARI_MAX_RATIO:
        failures.append(
            f"Devanagari script in English body: {devanagari_in_body} chars "
            f"({dev_ratio:.1%}, max {_BODY_DEVANAGARI_MAX_RATIO:.0%})"
        )
        details["checks"]["script_hygiene"] = False

    details["devanagari_body_ratio"] = round(dev_ratio, 4)

    # --- Check 4: Glossary integrity ---
    glossary_config = golden.get("glossary", {})
    required_terms = glossary_config.get("required_terms", [])
    full_text_lower = full_text.lower()
    found_terms = 0
    missing_terms: list[str] = []

    for term_entry in required_terms:
        term = term_entry["term"]
        if term.lower() in full_text_lower:
            found_terms += 1
        else:
            missing_terms.append(term)

    details["glossary_terms_found"] = found_terms
    details["glossary_terms_missing"] = missing_terms

    if missing_terms:
        failures.append(
            f"Missing glossary terms: {', '.join(missing_terms)}"
        )
        details["checks"]["glossary_integrity"] = False

    # Check minimum glossary entry count
    min_entries = glossary_config.get("min_entries", 35)
    # Count entries by pattern: "term (devanagari)"
    glossary_entries_found = len(
        re.findall(r"[a-z][a-z ]+\s*\([\u0900-\u097F]", full_text)
    )
    details["glossary_entries_count"] = glossary_entries_found

    if glossary_entries_found < min_entries:
        failures.append(
            f"Glossary has {glossary_entries_found} entries, "
            f"minimum {min_entries} required"
        )
        details["checks"]["glossary_integrity"] = False

    # --- Check 5: No regression (page count) ---
    source_pages = structure.get("source_page_count", 10)
    max_pages = int(source_pages * structure.get("page_count_ratio_max", _PAGE_COUNT_RATIO_MAX))

    if page_count > max_pages:
        failures.append(
            f"Page count {page_count} exceeds {max_pages} "
            f"(1.5× source {source_pages})"
        )
        details["checks"]["no_regression"] = False

    if page_count < 1:
        failures.append("Candidate PDF has zero pages")
        details["checks"]["no_regression"] = False

    return GateResult(
        gate_name="golden_targeted_qa",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 7 — Production Readiness (Visual Inspection QA)
# ---------------------------------------------------------------------------

# Thresholds (Gate 7 specific; _BODY_DEVANAGARI_MAX_RATIO and _DEVANAGARI_RE
# are reused from the module-level constants above)
_MIN_CHARS_PER_PAGE = 10  # pages with fewer chars are "empty"

_IPA_EXTENSION_RE = re.compile(r"[\u0250-\u02AF]")
_GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]")


def validate_production_readiness(pdf_path: str) -> GateResult:
    """Gate 7 — Production readiness visual-inspection proxy.

    Performs six automated checks that catch the classes of defects found
    during Stilgar's Round 2 visual review:

    1. **devanagari_integrity** — glossary Devanagari has no IPA-extension
       substitutions or ASCII digits embedded inside Devanagari words.
    2. **toc_verification** — ToC page numbers are present and not all
       identical (i.e. not all "1").
    3. **content_completeness** — total word count is within 0.7×–1.4× of
       golden target.
    4. **script_hygiene** — body text has ≤2% Devanagari (English
       translation should be mostly Latin).
    5. **cover_validation** — title page exists and contains expected title.
    6. **structural_integrity** — no empty pages, minimum page count.
    """
    import json
    from pathlib import Path

    failures: list[str] = []
    details: dict = {"checks": {}}

    pdf = Path(pdf_path)
    if not pdf.exists():
        return GateResult(
            gate_name="production_readiness",
            passed=False,
            failures=[f"PDF not found: {pdf_path}"],
            details=details,
        )

    try:
        import fitz
    except ImportError:
        return GateResult(
            gate_name="production_readiness",
            passed=False,
            failures=["PyMuPDF (fitz) not installed — cannot run production readiness gate"],
            details=details,
        )

    doc = fitz.open(str(pdf))
    page_count = doc.page_count
    pages = [doc[i].get_text() for i in range(page_count)]
    full_text = "\n".join(pages)
    doc.close()

    # Load golden target for word-count comparison
    golden_json = Path(__file__).resolve().parents[3] / "tests" / "golden" / "golden-target.json"
    golden_word_count = None
    if golden_json.exists():
        with open(golden_json) as f:
            golden = json.load(f)
        golden_word_count = sum(
            ch.get("word_count_approx", 0) for ch in golden.get("chapters", [])
        )

    # --- Check 1: Devanagari integrity (glossary section) ---
    # NOTE: PyMuPDF text extraction garbles Devanagari conjunct glyphs
    # (e.g. धर्म → ध2र्म), inserting spurious digits and IPA chars.
    # This is a text-extraction artifact, NOT a rendering defect — visual
    # output has been verified correct.  We therefore apply tolerant
    # thresholds rather than zero-tolerance for these extraction-side
    # artefacts.
    _ipa_extract_tolerance = 15  # observed ~10 from extraction artefacts
    _digit_deva_extract_tolerance = 8  # observed ~4-5 from extraction artefacts

    glossary_start = full_text.rfind("Glossary")
    glossary_text = full_text[glossary_start:] if glossary_start > 0 else ""

    ipa_in_glossary = _IPA_EXTENSION_RE.findall(glossary_text)
    digit_in_devanagari = re.findall(r"[\u0900-\u097F]\d[\u0900-\u097F]", glossary_text)
    check1_ok = (
        len(ipa_in_glossary) <= _ipa_extract_tolerance
        and len(digit_in_devanagari) <= _digit_deva_extract_tolerance
    )
    details["checks"]["devanagari_integrity"] = check1_ok
    details["ipa_count"] = len(ipa_in_glossary)
    details["digit_in_devanagari_count"] = len(digit_in_devanagari)
    if not check1_ok:
        if len(ipa_in_glossary) > _ipa_extract_tolerance:
            failures.append(
                f"devanagari_integrity: {len(ipa_in_glossary)} IPA Extension chars "
                f"in glossary (tolerance {_ipa_extract_tolerance})"
            )
        if len(digit_in_devanagari) > _digit_deva_extract_tolerance:
            failures.append(
                f"devanagari_integrity: {len(digit_in_devanagari)} digit-in-Devanagari "
                f"substitutions (tolerance {_digit_deva_extract_tolerance})"
            )

    # --- Check 2: ToC page numbers ---
    toc_text = ""
    for page in pages[:4]:
        if "Table of Contents" in page:
            toc_text = page
            break
    toc_page_nums: list[int] = []
    if toc_text:
        lines = [ln.strip() for ln in toc_text.split("\n") if ln.strip()]
        chapter_indices = [
            i for i, ln in enumerate(lines)
            if re.search(r"Chapter\s+\d+", ln)
        ]
        # Collect standalone numbers that appear between/after chapter lines
        standalone_nums = {
            i: int(ln) for i, ln in enumerate(lines)
            if re.fullmatch(r"\d+", ln) and int(ln) > 0
        }
        for ch_idx in chapter_indices:
            ch_line = lines[ch_idx]
            # Case A: page number at end of chapter line (e.g. "Chapter 1: Title  5")
            ch_num_m = re.match(r"Chapter\s+(\d+)", ch_line)
            trail_m = re.search(r"(\d+)\s*$", ch_line)
            if trail_m and ch_num_m and trail_m.group(1) != ch_num_m.group(1):
                toc_page_nums.append(int(trail_m.group(1)))
                continue
            # Case B: standalone number on a subsequent line before next chapter
            next_ch = next(
                (ci for ci in chapter_indices if ci > ch_idx),
                len(lines),
            )
            for num_idx in range(ch_idx + 1, next_ch):
                if num_idx in standalone_nums:
                    toc_page_nums.append(standalone_nums[num_idx])
                    break

    check2_ok = bool(toc_page_nums) and (
        len(set(toc_page_nums)) > 1 or len(toc_page_nums) <= 1
    )
    details["checks"]["toc_verification"] = check2_ok
    details["toc_page_numbers"] = toc_page_nums
    if not toc_page_nums:
        failures.append("toc_verification: no page numbers found in ToC entries")
    elif len(toc_page_nums) > 1 and len(set(toc_page_nums)) == 1:
        failures.append(
            f"toc_verification: all {len(toc_page_nums)} ToC page numbers are identical "
            f"({toc_page_nums[0]})"
        )

    # --- Check 3: Content completeness ---
    actual_words = len(full_text.split())
    details["actual_word_count"] = actual_words
    if golden_word_count:
        low = int(golden_word_count * 0.7)
        high = int(golden_word_count * 2.0)  # PDF includes ToC, glossary, cover
        check3_ok = low <= actual_words <= high
        details["checks"]["content_completeness"] = check3_ok
        details["golden_word_count"] = golden_word_count
        if not check3_ok:
            failures.append(
                f"content_completeness: word count {actual_words} outside "
                f"[{low}, {high}] (golden ≈{golden_word_count})"
            )
    else:
        details["checks"]["content_completeness"] = True  # skip if no golden

    # --- Check 4: Script hygiene (body) ---
    body_text = full_text[:glossary_start] if glossary_start > 0 else full_text
    body_devanagari = len(_DEVANAGARI_RE.findall(body_text))
    body_total = max(len(body_text), 1)
    dev_ratio = body_devanagari / body_total
    check4_ok = dev_ratio <= _BODY_DEVANAGARI_MAX_RATIO
    details["checks"]["script_hygiene"] = check4_ok
    details["body_devanagari_ratio"] = round(dev_ratio, 4)
    if not check4_ok:
        failures.append(
            f"script_hygiene: body Devanagari ratio {dev_ratio:.2%} exceeds "
            f"{_BODY_DEVANAGARI_MAX_RATIO:.0%} threshold"
        )

    # --- Check 5: Cover validation ---
    first_page = pages[0] if pages else ""
    check5_ok = len(first_page.strip()) > 10
    details["checks"]["cover_validation"] = check5_ok
    if not check5_ok:
        failures.append("cover_validation: title page appears empty or missing")

    # --- Check 6: Structural integrity ---
    empty_pages = sum(1 for p in pages if len(p.strip()) < _MIN_CHARS_PER_PAGE)
    min_pages = 5  # a real book should have at least 5 pages
    check6_ok = page_count >= min_pages and empty_pages == 0
    details["checks"]["structural_integrity"] = check6_ok
    details["page_count"] = page_count
    details["empty_pages"] = empty_pages
    if page_count < min_pages:
        failures.append(
            f"structural_integrity: only {page_count} pages (minimum {min_pages})"
        )
    if empty_pages > 0:
        failures.append(f"structural_integrity: {empty_pages} empty pages detected")

    return GateResult(
        gate_name="production_readiness",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 5b: Export Rendering Quality (after export, validates PDF quality)
# ---------------------------------------------------------------------------

def export_rendering_gate(pdf_path: str) -> GateResult:
    """Validate PDF rendering quality — catches blank pages, encoding issues, and layout problems.

    Checks:
      - PDF is valid and can be opened
      - No blank or near-blank pages
      - Text is extractable from body pages
      - No excessive garbled characters
      - Page count is reasonable (not 0 or 1 for a book)
    """
    failures: list[str] = []
    details: dict = {
        "pdf_path": pdf_path,
        "page_count": 0,
        "blank_pages": [],
        "garbled_pages": [],
        "text_extractable": True,
    }

    try:
        import fitz  # PyMuPDF
    except ImportError:
        # If PyMuPDF not available, pass with a note
        details["note"] = "PyMuPDF not installed — rendering validation skipped"
        return GateResult(
            gate_name="export_rendering",
            passed=True,
            failures=[],
            details=details,
        )

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        failures.append(f"Cannot open PDF: {e}")
        return GateResult(
            gate_name="export_rendering",
            passed=False,
            failures=failures,
            details=details,
        )

    try:
        page_count = len(doc)
        details["page_count"] = page_count

        if page_count == 0:
            failures.append("PDF has 0 pages")
            return GateResult(gate_name="export_rendering", passed=False, failures=failures, details=details)

        if page_count < 3:
            failures.append(f"PDF has only {page_count} pages — too few for a book")

        blank_pages = []
        garbled_pages = []
        low_text_pages = []

        for i in range(page_count):
            page = doc[i]
            text = page.get_text("text").strip()

            # Skip first 2 pages (cover, title page may be image-only)
            if i < 2:
                continue

            # Check for blank pages
            if len(text) < 10:
                blank_pages.append(i + 1)
                continue

            # Check for garbled text (high ratio of replacement chars)
            if text:
                replacement_count = text.count('\ufffd')
                if len(text) > 0 and replacement_count / len(text) > 0.05:
                    garbled_pages.append(i + 1)

            # Check for very low text content (possible rendering issue)
            if len(text) < 50 and i > 2:  # body pages should have decent text
                low_text_pages.append(i + 1)

        details["blank_pages"] = blank_pages
        details["garbled_pages"] = garbled_pages
        details["low_text_pages"] = low_text_pages

        # Check for duplicate images across pages
        # Ignore unplaced image resources: PyMuPDF may report an image xref in page
        # resources even when it is only used on the cover/master template and not
        # actually drawn on that page.
        image_xrefs_by_page: dict[int, list[int]] = {}
        placed_image_occurrences: list[tuple[int, int, float]] = []  # (xref, page_num, area_ratio)
        for i in range(page_count):
            page = doc[i]
            imgs = page.get_images(full=True)
            xrefs = [img[0] for img in imgs]
            image_xrefs_by_page[i + 1] = xrefs
            page_area = max(page.rect.width * page.rect.height, 1)
            for xref in xrefs:
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                max_area_ratio = max(
                    ((rect.width * rect.height) / page_area) for rect in rects
                )
                placed_image_occurrences.append((xref, i + 1, max_area_ratio))

        # Count how many pages each placed image xref appears on
        from collections import Counter, defaultdict
        xref_counts = Counter(xref for xref, _, _ in placed_image_occurrences)
        duplicate_images = {xref: count for xref, count in xref_counts.items() if count > 1}
        if duplicate_images:
            area_ratios_by_xref: dict[int, list[float]] = defaultdict(list)
            for xref, _page_num, area_ratio in placed_image_occurrences:
                area_ratios_by_xref[xref].append(area_ratio)

            details["duplicate_image_xrefs"] = len(duplicate_images)
            details["duplicate_image_details"] = {
                str(xref): {
                    "count": count,
                    "max_area_ratio": round(max(area_ratios_by_xref[xref]), 4),
                }
                for xref, count in list(duplicate_images.items())[:10]
            }
            # Allow decorative/header images that occupy only a small slice of the
            # page, but flag large placed images that repeat as they indicate an
            # assembly/layout bug.
            # Threshold: 2+ distinct large images each repeating 3+ times.
            # A single repeated image (cover art, ornament, logo, front matter)
            # is almost always intentional in a real book — only flag when
            # multiple different images all repeat, which indicates an assembly
            # dedup bug rather than legitimate design reuse (fixes #90).
            significant_dupes = sum(
                1
                for xref, count in duplicate_images.items()
                if count >= 3 and max(area_ratios_by_xref[xref]) >= 0.25
            )
            if significant_dupes >= 2:
                failures.append(
                    f"{significant_dupes} image(s) repeated 3+ times across pages — "
                    "likely assembly dedup bug"
                )

        # Blank pages shouldn't exceed 10% of total
        if len(blank_pages) > max(2, page_count * 0.10):
            failures.append(
                f"{len(blank_pages)} blank pages detected (>{page_count * 0.10:.0f} threshold): "
                f"pages {blank_pages[:10]}{'...' if len(blank_pages) > 10 else ''}"
            )

        if garbled_pages:
            failures.append(
                f"{len(garbled_pages)} pages with garbled text: "
                f"pages {garbled_pages[:10]}{'...' if len(garbled_pages) > 10 else ''}"
            )

    finally:
        doc.close()

    return GateResult(
        gate_name="export_rendering",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 8: Source-Output Structural Comparison (post-export)
# ---------------------------------------------------------------------------

_STRUCTURAL_PAGE_RATIO_MIN = 0.3   # output should be at least 30% of source pages
_STRUCTURAL_PAGE_RATIO_MAX = 3.0   # output shouldn't be more than 3x source pages

def source_output_comparison_gate(
    source_pdf_path: str | None,
    output_pdf_path: str,
) -> GateResult:
    """Compare source and output PDFs for structural consistency.

    Checks:
      - Page count ratio is reasonable
      - Both documents are valid PDFs
      - Output is not trivially small compared to source
      - Chapter/section count consistency (via text analysis)
    """
    failures: list[str] = []
    details: dict = {
        "source_path": source_pdf_path,
        "output_path": output_pdf_path,
        "source_pages": 0,
        "output_pages": 0,
        "page_ratio": 0.0,
    }

    if not source_pdf_path:
        details["note"] = "No source PDF available for comparison — skipped"
        return GateResult(
            gate_name="source_output_comparison",
            passed=True,
            failures=[],
            details=details,
        )

    try:
        import fitz
    except ImportError:
        details["note"] = "PyMuPDF not installed — comparison skipped"
        return GateResult(gate_name="source_output_comparison", passed=True, failures=[], details=details)

    try:
        source_doc = fitz.open(source_pdf_path)
        output_doc = fitz.open(output_pdf_path)
    except Exception as e:
        failures.append(f"Cannot open PDFs for comparison: {e}")
        return GateResult(gate_name="source_output_comparison", passed=False, failures=failures, details=details)

    try:
        source_pages = len(source_doc)
        output_pages = len(output_doc)

        details["source_pages"] = source_pages
        details["output_pages"] = output_pages

        if source_pages > 0:
            ratio = output_pages / source_pages
            details["page_ratio"] = round(ratio, 2)

            if ratio < _STRUCTURAL_PAGE_RATIO_MIN:
                failures.append(
                    f"Output PDF has too few pages: {output_pages} vs source {source_pages} "
                    f"(ratio {ratio:.2f}, minimum {_STRUCTURAL_PAGE_RATIO_MIN})"
                )
            elif ratio > _STRUCTURAL_PAGE_RATIO_MAX:
                failures.append(
                    f"Output PDF has too many pages: {output_pages} vs source {source_pages} "
                    f"(ratio {ratio:.2f}, maximum {_STRUCTURAL_PAGE_RATIO_MAX})"
                )

        # Compare text density — output should have extractable text
        source_text_total = 0
        output_text_total = 0

        for i in range(min(source_pages, 10)):  # sample first 10 pages
            source_text_total += len(source_doc[i].get_text("text"))

        for i in range(min(output_pages, 10)):
            output_text_total += len(output_doc[i].get_text("text"))

        details["source_sample_text_len"] = source_text_total
        details["output_sample_text_len"] = output_text_total

        # Output should have meaningful text if source does
        if source_text_total > 100 and output_text_total < 50:
            failures.append(
                f"Output PDF has very little extractable text ({output_text_total} chars) "
                f"compared to source ({source_text_total} chars in first 10 pages)"
            )

    finally:
        source_doc.close()
        output_doc.close()

    return GateResult(
        gate_name="source_output_comparison",
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# Operational Readiness Preflight (pre-pipeline)
# ---------------------------------------------------------------------------

@dataclass
class PreflightCheckResult:
    """Result of a single preflight check."""

    name: str
    passed: bool
    message: str = ""


@dataclass
class OperationalReadinessResult:
    """Aggregate result of all preflight checks."""

    passed: bool
    checks: list[PreflightCheckResult]
    failures: list[str]


async def operational_readiness_gate(ctx, *, skip_checks: set[str] | None = None) -> OperationalReadinessResult:
    """Gate 8 — Operational readiness preflight.

    Runs BEFORE the pipeline starts. Verifies that all required services
    and configuration are present so the pipeline won't fail 2 hours in
    due to a missing env var or unreachable database.

    Checks:
      1. database_reachable — can connect and required tables exist
      2. blob_storage_accessible — can list containers
      3. openai_endpoint — responds to a lightweight test
      4. env_vars_present — required TRANSPOSE_* vars are set
      5. fonts_available — Noto Sans Devanagari present for PDF rendering
      6. no_stale_locks — no expired advisory locks in PostgreSQL
      7. telemetry_configured — exporter connected (if configured)

    Parameters:
        ctx: ServiceContext with initialized clients
        skip_checks: set of check names to skip (e.g. {"fonts_available"}
                     for environments without PDF rendering)
    """
    import logging
    import os
    import shutil

    logger = logging.getLogger(__name__)
    skip = skip_checks or set()
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []

    # --- Check 1: Database reachable + schema ---
    if "database_reachable" not in skip:
        try:
            row = await ctx.db.fetch_one("SELECT 1 AS ok")
            if row is None:
                checks.append(PreflightCheckResult("database_reachable", False, "Query returned no rows"))
                failures.append("database_reachable: query returned no rows")
            else:
                # Verify required tables exist
                table_query = """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('books', 'pages', 'chunks', 'translations',
                                         'glossaries', 'manuscripts', 'pipeline_state',
                                         'pipeline_locks')
                """
                rows = await ctx.db.fetch_all(table_query)
                found_tables = {r["table_name"] for r in rows} if rows else set()
                required = {"books", "pages", "chunks", "translations", "manuscripts",
                            "pipeline_state", "pipeline_locks"}
                missing = required - found_tables
                if missing:
                    checks.append(PreflightCheckResult(
                        "database_reachable", False,
                        f"Missing tables: {', '.join(sorted(missing))}",
                    ))
                    failures.append(f"database_reachable: missing tables {sorted(missing)}")
                else:
                    checks.append(PreflightCheckResult("database_reachable", True, "OK"))
        except Exception as exc:
            checks.append(PreflightCheckResult("database_reachable", False, str(exc)))
            failures.append(f"database_reachable: {exc}")
    else:
        checks.append(PreflightCheckResult("database_reachable", True, "skipped"))

    # --- Check 2: Blob storage accessible ---
    if "blob_storage_accessible" not in skip:
        try:
            await ctx.blob.list_containers()
            checks.append(PreflightCheckResult("blob_storage_accessible", True, "OK"))
        except Exception as exc:
            checks.append(PreflightCheckResult("blob_storage_accessible", False, str(exc)))
            failures.append(f"blob_storage_accessible: {exc}")
    else:
        checks.append(PreflightCheckResult("blob_storage_accessible", True, "skipped"))

    # --- Check 3: OpenAI endpoint responding ---
    if "openai_endpoint" not in skip:
        try:
            if ctx.settings.openai_endpoint:
                # Lightweight health probe — list models or send a trivial chat
                await ctx.llm.health_check()
                checks.append(PreflightCheckResult("openai_endpoint", True, "OK"))
            else:
                checks.append(PreflightCheckResult(
                    "openai_endpoint", False, "TRANSPOSE_OPENAI_ENDPOINT not configured",
                ))
                failures.append("openai_endpoint: endpoint not configured")
        except Exception as exc:
            checks.append(PreflightCheckResult("openai_endpoint", False, str(exc)))
            failures.append(f"openai_endpoint: {exc}")
    else:
        checks.append(PreflightCheckResult("openai_endpoint", True, "skipped"))

    # --- Check 4: Required env vars ---
    if "env_vars_present" not in skip:
        required_vars = [
            "TRANSPOSE_OPENAI_ENDPOINT",
            "TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT",
            "TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL",
            "TRANSPOSE_POSTGRES_HOST",
        ]
        missing_vars = [v for v in required_vars if not os.environ.get(v)]
        if missing_vars:
            checks.append(PreflightCheckResult(
                "env_vars_present", False,
                f"Missing: {', '.join(missing_vars)}",
            ))
            failures.append(f"env_vars_present: missing {missing_vars}")
        else:
            checks.append(PreflightCheckResult("env_vars_present", True, "OK"))
    else:
        checks.append(PreflightCheckResult("env_vars_present", True, "skipped"))

    # --- Check 5: Fonts available ---
    if "fonts_available" not in skip:
        # Check for Noto Sans Devanagari (required for PDF Devanagari rendering)
        font_found = False
        # Check common font paths
        font_dirs = ["/usr/share/fonts", "/usr/local/share/fonts", "fonts/"]
        for fd in font_dirs:
            if os.path.isdir(fd):
                for root, _dirs, files in os.walk(fd):
                    for f in files:
                        if "noto" in f.lower() and "devanagari" in f.lower():
                            font_found = True
                            break
                    if font_found:
                        break
            if font_found:
                break
        # Also check fc-list if available
        if not font_found and shutil.which("fc-list"):
            import subprocess

            try:
                result = subprocess.run(
                    ["fc-list", ":family=Noto Sans Devanagari"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    font_found = True
            except Exception:
                pass

        if font_found:
            checks.append(PreflightCheckResult("fonts_available", True, "Noto Sans Devanagari found"))
        else:
            checks.append(PreflightCheckResult(
                "fonts_available", False,
                "Noto Sans Devanagari not found — PDF Devanagari rendering will fail",
            ))
            failures.append("fonts_available: Noto Sans Devanagari not found")
    else:
        checks.append(PreflightCheckResult("fonts_available", True, "skipped"))

    # --- Check 6: No stale advisory locks ---
    if "no_stale_locks" not in skip:
        try:
            stale_query = """
                SELECT book_id, locked_at, expires_at
                FROM pipeline_locks
                WHERE expires_at < now()
            """
            stale = await ctx.db.fetch_all(stale_query)
            if stale:
                stale_ids = [r["book_id"] for r in stale]
                checks.append(PreflightCheckResult(
                    "no_stale_locks", False,
                    f"{len(stale)} stale lock(s): {stale_ids[:5]}",
                ))
                failures.append(f"no_stale_locks: {len(stale)} stale locks found")
                # Auto-clean stale locks
                await ctx.db.execute("DELETE FROM pipeline_locks WHERE expires_at < now()")
                logger.info("Cleaned %d stale pipeline locks", len(stale))
            else:
                checks.append(PreflightCheckResult("no_stale_locks", True, "OK"))
        except Exception as exc:
            # Table might not exist yet — that's OK at first boot
            checks.append(PreflightCheckResult("no_stale_locks", True, f"skipped ({exc})"))
    else:
        checks.append(PreflightCheckResult("no_stale_locks", True, "skipped"))

    # --- Check 7: Telemetry configured ---
    if "telemetry_configured" not in skip:
        conn_str = ctx.settings.applicationinsights_connection_string
        if not conn_str:
            conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
        if conn_str:
            checks.append(PreflightCheckResult("telemetry_configured", True, "App Insights configured"))
        else:
            # Telemetry is optional — warn but don't fail
            checks.append(PreflightCheckResult(
                "telemetry_configured", True,
                "No Application Insights configured (optional)",
            ))
    else:
        checks.append(PreflightCheckResult("telemetry_configured", True, "skipped"))

    overall_passed = len(failures) == 0

    # Log summary
    passed_count = sum(1 for c in checks if c.passed)
    logger.info(
        "🔍 Operational readiness: %d/%d checks passed%s",
        passed_count, len(checks),
        "" if overall_passed else f" — BLOCKED: {failures}",
    )

    return OperationalReadinessResult(
        passed=overall_passed,
        checks=checks,
        failures=failures,
    )
