"""Tests for pipeline quality gates.

Validates all 5 quality gate functions with passing and failing scenarios.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from uuid import UUID, uuid4

from transpose.pipeline.gates import (
    GateResult,
    QualityGateError,
    artifact_availability_gate,
    document_structure_gate,
    glossary_integrity_gate,
    ocr_sanity_gate,
    translation_completeness_gate,
)

# Sample Hindi text for tests (Devanagari script)
_HINDI_LONG = (
    "धर्म और कर्म का अर्थ बहुत गहरा है। "
    "योग साधना से मोक्ष मिलता है।"
)
_HINDI_SHORT = "धर्म और कर्म का अर्थ है।"
_HINDI_PAGE2 = (
    "आत्मा अमर है। गीता में कृष्ण ने "
    "अर्जुन को यह ज्ञान दिया।"
)


# ---------------------------------------------------------------------------
# Lightweight stub dataclasses for gate inputs
# ---------------------------------------------------------------------------


@dataclass
class StubPage:
    page_number: int
    raw_text: str
    confidence: float = 0.95
    needs_review: bool = False
    ocr_metadata: dict = field(default_factory=dict)


@dataclass
class StubOcrOutput:
    book_id: UUID = field(default_factory=uuid4)
    pages_processed: int = 0
    pages_skipped: int = 0
    low_confidence_count: int = 0
    page_results: list[StubPage] = field(default_factory=list)


@dataclass
class StubTranslationResult:
    chunk_id: UUID = field(default_factory=uuid4)
    translated_text: str = ""
    cultural_terms: list = field(default_factory=list)
    prompt_tokens: int = 100
    completion_tokens: int = 50
    model_version: str = "gpt-4o"


@dataclass
class StubTranslateOutput:
    book_id: UUID = field(default_factory=uuid4)
    chunks_translated: int = 0
    chunks_skipped: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    cultural_terms_found: int = 0
    translations: list[StubTranslationResult] = field(default_factory=list)
    failed_count: int = 0


@dataclass
class StubGlossaryEntry:
    term: str = ""
    original_script: str = ""
    definition: str = ""
    source: str = "seed"
    occurrence_count: int = 1
    first_chapter: str | None = None
    needs_review: bool = False


@dataclass
class StubGlossaryOutput:
    book_id: UUID = field(default_factory=uuid4)
    glossary_id: UUID = field(default_factory=uuid4)
    total_terms: int = 0
    seed_terms: int = 0
    llm_detected_terms: int = 0
    needs_review_count: int = 0
    entries: list[StubGlossaryEntry] = field(default_factory=list)


@dataclass
class StubChapter:
    number: int = 1
    title: str = "Chapter 1"
    content_html: str = "<p>Content</p>"


@dataclass
class StubAssembleOutput:
    book_id: UUID = field(default_factory=uuid4)
    manuscript_id: UUID = field(default_factory=uuid4)
    title: str = "Test Book"
    author: str | None = "Author"
    chapters: list[StubChapter] = field(default_factory=list)
    glossary_id: UUID | None = None
    table_of_contents: list[dict] = field(default_factory=list)
    foreword: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class StubExportArtifact:
    format: str = "pdf"
    blob_uri: str = "https://storage.blob.core.windows.net/output/book.pdf"
    file_size_bytes: int = 50000


@dataclass
class StubExportOutput:
    book_id: UUID = field(default_factory=uuid4)
    artifacts: list[StubExportArtifact] = field(default_factory=list)


# ===================================================================
# GateResult dataclass
# ===================================================================


class TestGateResult:
    def test_passing_gate(self) -> None:
        r = GateResult(gate_name="test", passed=True)
        assert r.passed is True
        assert r.gate_name == "test"
        assert r.failures == []

    def test_failing_gate(self) -> None:
        r = GateResult(gate_name="test", passed=False, failures=["bad"])
        assert r.passed is False
        assert len(r.failures) == 1

    def test_serialization_to_dict(self) -> None:
        r = GateResult(gate_name="ocr_sanity", passed=True)
        d = asdict(r)
        assert d["gate_name"] == "ocr_sanity"
        assert d["passed"] is True

    def test_timestamp_present(self) -> None:
        r = GateResult(gate_name="test", passed=True)
        assert r.timestamp


# ===================================================================
# QualityGateError
# ===================================================================


class TestQualityGateError:
    def test_inherits_exception(self) -> None:
        result = GateResult(gate_name="test", passed=False, failures=["fail"])
        err = QualityGateError(result)
        assert isinstance(err, Exception)

    def test_gate_result_accessible(self) -> None:
        result = GateResult(gate_name="ocr_sanity", passed=False, failures=["fail"])
        err = QualityGateError(result)
        assert err.gate_result.gate_name == "ocr_sanity"

    def test_str_representation(self) -> None:
        result = GateResult(
            gate_name="glossary_integrity", passed=False, failures=["NFC mismatch"]
        )
        err = QualityGateError(result)
        assert "glossary_integrity" in str(err)
        assert "NFC mismatch" in str(err)


# ===================================================================
# OCR Sanity Gate
# ===================================================================


class TestOcrSanityGate:
    def test_passes_with_clean_hindi_text(self) -> None:
        pages = [
            StubPage(
                page_number=1,
                raw_text=_HINDI_LONG,
                confidence=0.92,
            ),
            StubPage(
                page_number=2,
                raw_text=_HINDI_PAGE2,
                confidence=0.88,
            ),
        ]
        output = StubOcrOutput(page_results=pages, pages_processed=2)
        result = ocr_sanity_gate(output)
        assert result.passed is True
        assert result.gate_name == "ocr_sanity"

    def test_fails_with_excessive_replacement_chars(self) -> None:
        garbled = "\ufffd" * 50 + "\u0927\u0930\u094d\u092e" * 5
        pages = [StubPage(page_number=1, raw_text=garbled, confidence=0.9)]
        output = StubOcrOutput(page_results=pages, pages_processed=1)
        result = ocr_sanity_gate(output)
        assert result.passed is False
        assert any("replacement" in f.lower() for f in result.failures)

    def test_fails_with_low_devanagari_density(self) -> None:
        pages = [
            StubPage(
                page_number=1,
                raw_text="This is all English text with no Hindi characters at all here.",
                confidence=0.95,
            )
        ]
        output = StubOcrOutput(page_results=pages, pages_processed=1)
        result = ocr_sanity_gate(output)
        assert result.passed is False
        assert any("devanagari" in f.lower() for f in result.failures)

    def test_fails_with_low_confidence(self) -> None:
        pages = [
            StubPage(
                page_number=1,
                raw_text=_HINDI_SHORT,
                confidence=0.4,
            )
        ]
        output = StubOcrOutput(page_results=pages, pages_processed=1)
        result = ocr_sanity_gate(output)
        assert result.passed is False
        assert any("confidence" in f.lower() for f in result.failures)

    def test_passes_with_empty_page_list(self) -> None:
        output = StubOcrOutput(page_results=[], pages_processed=0)
        result = ocr_sanity_gate(output)
        assert result.passed is True

    def test_multiple_failing_pages_reported(self) -> None:
        pages = [
            StubPage(page_number=1, raw_text="all english", confidence=0.95),
            StubPage(page_number=2, raw_text="still english", confidence=0.3),
        ]
        output = StubOcrOutput(page_results=pages, pages_processed=2)
        result = ocr_sanity_gate(output)
        assert result.passed is False
        assert len(result.details["failing_pages"]) >= 1


# ===================================================================
# Translation Completeness Gate
# ===================================================================


class TestTranslationCompletenessGate:
    def test_passes_with_clean_translations(self) -> None:
        translations = [
            StubTranslationResult(
                translated_text="The meaning of dharma and karma is profound."
            ),
            StubTranslationResult(
                translated_text="The soul is immortal, says the Gita."
            ),
        ]
        output = StubTranslateOutput(
            chunks_translated=2, translations=translations, failed_count=0
        )
        result = translation_completeness_gate(output)
        assert result.passed is True

    def test_fails_with_high_failure_count(self) -> None:
        translations = [
            StubTranslationResult(translated_text="Good translation"),
            StubTranslationResult(
                translated_text="[TRANSLATION FAILED \u2014 REVIEW REQUIRED]"
            ),
            StubTranslationResult(
                translated_text="[TRANSLATION FAILED \u2014 REVIEW REQUIRED]"
            ),
        ]
        output = StubTranslateOutput(
            chunks_translated=3, translations=translations, failed_count=2
        )
        result = translation_completeness_gate(output)
        assert result.passed is False

    def test_fails_with_devanagari_passthrough(self) -> None:
        translations = [
            StubTranslationResult(translated_text=_HINDI_LONG),
        ]
        output = StubTranslateOutput(
            chunks_translated=1, translations=translations, failed_count=0
        )
        result = translation_completeness_gate(output)
        assert result.passed is False
        assert any("passthrough" in f.lower() for f in result.failures)

    def test_passes_with_acceptable_failure_ratio(self) -> None:
        good = [
            StubTranslationResult(translated_text="Good translation") for _ in range(19)
        ]
        bad = [
            StubTranslationResult(
                translated_text="[TRANSLATION FAILED \u2014 REVIEW REQUIRED]"
            )
        ]
        output = StubTranslateOutput(
            chunks_translated=20, translations=good + bad, failed_count=1
        )
        result = translation_completeness_gate(output)
        assert result.passed is True

    def test_passes_with_empty_translations(self) -> None:
        output = StubTranslateOutput(
            chunks_translated=0, translations=[], failed_count=0
        )
        result = translation_completeness_gate(output)
        assert result.passed is True


# ===================================================================
# Glossary Integrity Gate
# ===================================================================


class TestGlossaryIntegrityGate:
    def test_passes_with_clean_entries(self) -> None:
        entries = [
            StubGlossaryEntry(
                term="dharma",
                original_script="\u0927\u0930\u094d\u092e",
                definition="Righteous duty",
            ),
            StubGlossaryEntry(
                term="karma",
                original_script="\u0915\u0930\u094d\u092e",
                definition="Action",
            ),
        ]
        output = StubGlossaryOutput(entries=entries, total_terms=2)
        result = glossary_integrity_gate(output)
        assert result.passed is True

    def test_fails_with_empty_glossary(self) -> None:
        output = StubGlossaryOutput(entries=[], total_terms=0)
        result = glossary_integrity_gate(output)
        assert result.passed is False
        assert any("no entries" in f for f in result.failures)

    def test_fails_with_non_nfc_script(self) -> None:
        # Use é (U+00E9) which decomposes to e + combining acute in NFD
        # This guarantees NFD != NFC
        nfd_script = unicodedata.normalize("NFD", "é") + "धर्म"
        entries = [
            StubGlossaryEntry(
                term="dharma", original_script=nfd_script, definition="Righteous duty"
            ),
        ]
        output = StubGlossaryOutput(entries=entries, total_terms=1)
        result = glossary_integrity_gate(output)
        assert result.passed is False
        assert any("NFC" in f for f in result.failures)

    def test_fails_with_replacement_chars(self) -> None:
        entries = [
            StubGlossaryEntry(
                term="dharma",
                original_script="\u0927\u0930\ufffd\u092e",
                definition="Righteous duty",
            ),
        ]
        output = StubGlossaryOutput(entries=entries, total_terms=1)
        result = glossary_integrity_gate(output)
        assert result.passed is False
        assert any("U+FFFD" in f for f in result.failures)

    def test_fails_with_latin_in_devanagari(self) -> None:
        entries = [
            StubGlossaryEntry(
                term="dharma",
                original_script="\u0927\u0930\u094d\u092eabc",
                definition="Righteous duty",
            ),
        ]
        output = StubGlossaryOutput(entries=entries, total_terms=1)
        result = glossary_integrity_gate(output)
        assert result.passed is False
        assert any("Latin" in f for f in result.failures)


# ===================================================================
# Document Structure Gate
# ===================================================================


class TestDocumentStructureGate:
    def _long_foreword(self) -> str:
        return " ".join(["word"] * 60)

    def test_passes_with_valid_structure(self) -> None:
        chapters = [StubChapter(number=1), StubChapter(number=2)]
        toc = [{"chapter": 1, "title": "Ch 1"}, {"chapter": 2, "title": "Ch 2"}]
        output = StubAssembleOutput(
            title="Test Book",
            chapters=chapters,
            table_of_contents=toc,
            metadata={"foreword": self._long_foreword()},
        )
        result = document_structure_gate(output)
        assert result.passed is True

    def test_fails_with_toc_chapter_mismatch(self) -> None:
        chapters = [StubChapter(number=1)]
        toc = [
            {"chapter": 1, "title": "Ch 1"},
            {"chapter": 2, "title": "Ch 2"},
        ]
        output = StubAssembleOutput(
            title="Test Book",
            chapters=chapters,
            table_of_contents=toc,
            metadata={"foreword": self._long_foreword()},
        )
        result = document_structure_gate(output)
        assert result.passed is False
        assert any("ToC" in f for f in result.failures)

    def test_fails_with_missing_foreword(self) -> None:
        chapters = [StubChapter(number=1)]
        output = StubAssembleOutput(
            title="Test Book", chapters=chapters, metadata={}
        )
        result = document_structure_gate(output)
        assert result.passed is False
        assert any("foreword" in f for f in result.failures)

    def test_fails_with_no_title(self) -> None:
        chapters = [StubChapter(number=1)]
        output = StubAssembleOutput(
            title="", chapters=chapters, metadata={"foreword": self._long_foreword()}
        )
        result = document_structure_gate(output)
        assert result.passed is False
        assert any("title" in f for f in result.failures)

    def test_fails_with_non_sequential_chapters(self) -> None:
        chapters = [StubChapter(number=1), StubChapter(number=3)]
        toc = [
            {"chapter": 1, "title": "Ch 1"},
            {"chapter": 3, "title": "Ch 3"},
        ]
        output = StubAssembleOutput(
            title="Test Book",
            chapters=chapters,
            table_of_contents=toc,
            metadata={"foreword": self._long_foreword()},
        )
        result = document_structure_gate(output)
        assert result.passed is False
        assert any("sequential" in f for f in result.failures)


# ===================================================================
# Artifact Availability Gate
# ===================================================================


class TestArtifactAvailabilityGate:
    def test_passes_with_valid_artifacts(self) -> None:
        artifacts = [
            StubExportArtifact(format="pdf", file_size_bytes=50000),
            StubExportArtifact(
                format="epub",
                blob_uri="https://storage.blob.core.windows.net/output/book.epub",
                file_size_bytes=30000,
            ),
        ]
        output = StubExportOutput(artifacts=artifacts)
        result = artifact_availability_gate(output)
        assert result.passed is True

    def test_fails_with_missing_pdf(self) -> None:
        artifacts = [StubExportArtifact(format="epub", file_size_bytes=30000)]
        output = StubExportOutput(artifacts=artifacts)
        result = artifact_availability_gate(output)
        assert result.passed is False
        assert any("pdf" in f for f in result.failures)

    def test_fails_with_missing_epub(self) -> None:
        artifacts = [StubExportArtifact(format="pdf", file_size_bytes=50000)]
        output = StubExportOutput(artifacts=artifacts)
        result = artifact_availability_gate(output)
        assert result.passed is False
        assert any("epub" in f for f in result.failures)

    def test_fails_with_zero_size(self) -> None:
        artifacts = [
            StubExportArtifact(format="pdf", file_size_bytes=0),
            StubExportArtifact(format="epub", file_size_bytes=30000),
        ]
        output = StubExportOutput(artifacts=artifacts)
        result = artifact_availability_gate(output)
        assert result.passed is False
        assert any("too small" in f for f in result.failures)

    def test_fails_with_no_artifacts(self) -> None:
        output = StubExportOutput(artifacts=[])
        result = artifact_availability_gate(output)
        assert result.passed is False
        assert len(result.failures) >= 2

    def test_fails_with_invalid_uri(self) -> None:
        artifacts = [
            StubExportArtifact(format="pdf", blob_uri="not-a-url", file_size_bytes=50000),
            StubExportArtifact(format="epub", file_size_bytes=30000),
        ]
        output = StubExportOutput(artifacts=artifacts)
        result = artifact_availability_gate(output)
        assert result.passed is False
        assert any("invalid URI" in f for f in result.failures)
