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
_MAX_FAILED_CHUNK_RATIO = 0.10
_MIN_FOREWORD_WORDS = 50
_MIN_ARTIFACT_SIZE = 1024  # 1 KB


# ---------------------------------------------------------------------------
# Gate 1: OCR Sanity (after OCR, before chunk)
# ---------------------------------------------------------------------------

def ocr_sanity_gate(ocr_output) -> GateResult:
    """Validate OCR output quality before chunking.

    Checks:
      - Garbled Unicode (excessive U+FFFD replacement characters)
      - Devanagari codepoint density for Hindi source text
      - OCR confidence scores (reject pages below threshold)
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
        if confidence is not None and confidence < _MIN_CONFIDENCE:
            page_issues.append(
                f"page {page_num}: confidence {confidence:.2f} "
                f"below threshold {_MIN_CONFIDENCE}"
            )

        if page_issues:
            failing_pages.append(page_num)
            failures.extend(page_issues)

    details["failing_pages"] = failing_pages
    details["checks"] = {
        "replacement_char_threshold": _MAX_REPLACEMENT_RATIO,
        "devanagari_density_threshold": _DEVANAGARI_DENSITY_THRESHOLD,
        "min_confidence": _MIN_CONFIDENCE,
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
    if total > 0 and failed_count / total > _MAX_FAILED_CHUNK_RATIO:
        msg = (
            f"{failed_count}/{total} chunks failed translation "
            f"({failed_count / total:.0%}, threshold {_MAX_FAILED_CHUNK_RATIO:.0%})"
        )
        failures.append(msg)

    # Check 2: Scan translations for TRANSLATION FAILED markers and Devanagari passthrough
    marker_count = 0
    passthrough_count = 0
    for tr in translations:
        text = getattr(tr, "translated_text", "") or ""
        chunk_id = str(getattr(tr, "chunk_id", "unknown"))

        if _TRANSLATION_FAILED_MARKER in text:
            marker_count += 1
            failing_chunks.append(chunk_id)

        # Detect raw Devanagari passthrough — if >30% of non-space chars
        # are Devanagari in the *translated* output, source likely leaked
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

    if total > 0 and marker_count / total > _MAX_FAILED_CHUNK_RATIO:
        failures.append(
            f"{marker_count}/{total} chunks contain TRANSLATION FAILED marker "
            f"({marker_count / total:.0%})"
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

    # Check 1: ToC count matches chapter count
    if toc and len(toc) != len(chapters):
        failures.append(
            f"ToC has {len(toc)} entries but manuscript has {len(chapters)} chapters"
        )

    # Check 2: Foreword present and non-empty
    if not foreword or len(foreword.split()) < _MIN_FOREWORD_WORDS:
        word_count = len(foreword.split()) if foreword else 0
        failures.append(
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

    # Check expected formats present
    for expected in ("pdf", "epub"):
        if expected not in found_formats:
            details["missing"].append(expected)
            failures.append(f"{expected} artifact missing from export output")

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
