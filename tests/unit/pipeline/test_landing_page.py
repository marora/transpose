"""D-2: Landing page render tests.

Validates that `generate_landing_html` (Trinity TR-3) produces HTML that:

  - Contains required OG meta tags: og:title, og:description, og:type
  - Contains required Twitter Card meta tags
  - Contains both download links (source + translated PDF)
  - Does NOT mention license.status anywhere on the page
  - Is syntactically valid HTML (parsed with html.parser from stdlib)
  - Matches the known-good golden fixture (snapshot test)

Tests are marked ``pytest.mark.contract`` and skipped until Trinity's
TR-3 lands at ``transpose.workspace.landing.generate_landing_html``.

Spec references: .squad/decisions.md
  - Architecture Addendum §C (WhatsApp Preview, Option A — Static HTML)
  - Architecture Addendum §D (metadata.json fields for landing page)
  - Template minimum in §C
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Contract import guard — skipped until Trinity lands TR-3
# ---------------------------------------------------------------------------

try:
    from transpose.workspace.landing import generate_landing_html  # type: ignore[import]
    HAS_LANDING_MODULE = True
except ImportError:
    HAS_LANDING_MODULE = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_METADATA: dict = {
    "workspace_id": "ws-a1b2c3d4",
    "book_id": "beacab8b-ea5c-49e5-a60f-1ebc753c7061",
    "slug": "vigyan-bhairav-tantra-vol-1",
    "title": "Vigyan Bhairav Tantra Vol. 1",
    "author": "Osho",
    "source_language": "Hindi",
    "target_language": "English",
    "page_count": 312,
    "status": "review",
    "pipeline_version": "1.3.0",
    "created_at": "2026-05-20T22:52:32-04:00",
    "updated_at": "2026-05-20T23:19:30-04:00",
    "published_at": None,
    "translator_note": "A Tantra classic. 112 meditation techniques as described by Shiva to Devi.",
    "cover_image_blob_url": None,
    "landing_page_url": (
        "https://transposebooks.z6.web.core.windows.net/"
        "vigyan-bhairav-tantra-vol-1--b7f3a2/"
    ),
    "license": {
        "status": "verified-public-domain",
        "notes": "Pre-1925 text; no modern editorial layer on this scan.",
    },
    "provenance": {
        "source": {
            "url": "https://archive.org/details/osho-vbt-vol1-hindi",
            "edition": "Diamond Pocket Books, New Delhi, 2005 edition",
            "acquired_at": "2026-04-01T10:00:00Z",
            "notes": None,
        }
    },
    "share": {
        "source_pdf_sas_url": (
            "https://transposebooks.blob.core.windows.net/book-workspaces/"
            "vigyan-bhairav-tantra-vol-1--b7f3a2/input/source.pdf"
            "?sv=2023-01-03&se=2026-06-19T23%3A10%3A00Z&sr=b&sp=r&sig=FAKESIG002"
        ),
        "translated_pdf_sas_url": (
            "https://transposebooks.blob.core.windows.net/book-workspaces/"
            "vigyan-bhairav-tantra-vol-1--b7f3a2/output/translated.pdf"
            "?sv=2023-01-03&se=2026-06-19T23%3A10%3A00Z&sr=b&sp=r&sig=FAKESIG001"
        ),
        "sas_expiry": "2026-06-19T23:10:00Z",
        "generated_at": "2026-05-20T23:10:06Z",
    },
    "artifact_manifest": [],
}


@pytest.fixture
def sample_metadata() -> dict:
    """Full valid metadata.json dict for use as generate_landing_html input."""
    return dict(SAMPLE_METADATA)


@pytest.fixture
def golden_fixture_path() -> Path:
    """Absolute path to the golden landing-page HTML fixture."""
    return Path(__file__).parents[2] / "golden" / "landing_page_fixture.html"


@pytest.fixture
def golden_html(golden_fixture_path: Path) -> str:
    """Contents of the golden landing-page HTML fixture."""
    assert golden_fixture_path.exists(), (
        f"Golden fixture not found at {golden_fixture_path}. "
        "Run the test suite once to generate it."
    )
    return golden_fixture_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML helper
# ---------------------------------------------------------------------------


class _MetaCollector(HTMLParser):
    """Collects all <meta> tags and <a href> links from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.meta_tags: list[dict[str, str]] = []
        self.links: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta":
            self.meta_tags.append(a)
        elif tag == "a":
            href = a.get("href")
            if href:
                self.links.append(href)

    def error(self, message: str) -> None:  # type: ignore[override]
        self.errors.append(message)


def _parse_html(html: str) -> _MetaCollector:
    collector = _MetaCollector()
    collector.feed(html)
    return collector


def _og_content(tags: list[dict], property_name: str) -> str | None:
    for t in tags:
        if t.get("property") == property_name:
            return t.get("content")
    return None


def _twitter_content(tags: list[dict], name: str) -> str | None:
    for t in tags:
        if t.get("name") == name:
            return t.get("content")
    return None


# ---------------------------------------------------------------------------
# Golden fixture validation (always runnable — tests the fixture itself)
# ---------------------------------------------------------------------------

class TestGoldenFixtureIntegrity:
    """Validates that the checked-in golden fixture is itself well-formed.

    These tests run without Trinity's code, verifying the fixture file is a
    useful baseline for the snapshot comparison.
    """

    def test_golden_fixture_has_og_title(self, golden_html: str) -> None:
        """Golden fixture must contain og:title."""
        parsed = _parse_html(golden_html)
        val = _og_content(parsed.meta_tags, "og:title")
        assert val, "Golden fixture is missing <meta property='og:title'>."

    def test_golden_fixture_has_og_description(self, golden_html: str) -> None:
        """Golden fixture must contain og:description."""
        parsed = _parse_html(golden_html)
        val = _og_content(parsed.meta_tags, "og:description")
        assert val, "Golden fixture is missing <meta property='og:description'>."

    def test_golden_fixture_has_og_type(self, golden_html: str) -> None:
        """Golden fixture must contain og:type."""
        parsed = _parse_html(golden_html)
        val = _og_content(parsed.meta_tags, "og:type")
        assert val, "Golden fixture is missing <meta property='og:type'>."

    def test_golden_fixture_has_twitter_card(self, golden_html: str) -> None:
        """Golden fixture must contain twitter:card meta tag."""
        parsed = _parse_html(golden_html)
        val = _twitter_content(parsed.meta_tags, "twitter:card")
        assert val, "Golden fixture is missing <meta name='twitter:card'>."

    def test_golden_fixture_has_two_download_links(self, golden_html: str) -> None:
        """Golden fixture must contain links to both source and translated PDFs."""
        parsed = _parse_html(golden_html)
        assert len(parsed.links) >= 2, (  # noqa: PLR2004
            f"Golden fixture must have at least 2 PDF links, found {len(parsed.links)}."
        )
        has_source = any("input/source.pdf" in link for link in parsed.links)
        has_translated = any("output/translated.pdf" in link for link in parsed.links)
        assert has_source, "Golden fixture missing link to input/source.pdf."
        assert has_translated, "Golden fixture missing link to output/translated.pdf."

    def test_golden_fixture_does_not_mention_license_status(
        self, golden_html: str
    ) -> None:
        """license.status must NOT appear anywhere in the rendered HTML.

        Spec: decisions.md §C — 'The page does not render "license status" to readers.
        license.status is an internal operational field.'
        """
        status_values = [
            "rights-unknown",
            "claimed-public-domain",
            "verified-public-domain",
            "rights-cleared",
            "license.status",
            "license_status",
        ]
        for val in status_values:
            assert val not in golden_html, (
                f"Golden fixture must not expose license metadata to readers, "
                f"but found '{val}' in rendered HTML."
            )

    def test_golden_fixture_is_valid_html(self, golden_html: str) -> None:
        """html.parser must parse the golden fixture without errors."""
        parsed = _parse_html(golden_html)
        assert not parsed.errors, (
            f"Golden fixture HTML has parse errors: {parsed.errors}"
        )


# ---------------------------------------------------------------------------
# D-2 contract tests against Trinity's generate_landing_html (TR-3)
# ---------------------------------------------------------------------------

_SKIP_REASON = (
    "Contract test — requires Trinity TR-3 "
    "(transpose.workspace.landing.generate_landing_html)"
)


@pytest.mark.contract
@pytest.mark.skipif(not HAS_LANDING_MODULE, reason=_SKIP_REASON)
class TestGenerateLandingHtml:
    """Test that Trinity's generate_landing_html produces spec-compliant HTML."""

    def test_landing_page_contains_og_title(self, sample_metadata: dict) -> None:
        """Rendered HTML must have <meta property='og:title'> = '{title} — {author}'.

        Spec: decisions.md §C template — og:title content="{{ title }} — {{ author }}"
        """
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        val = _og_content(parsed.meta_tags, "og:title")
        assert val is not None, "Rendered HTML is missing <meta property='og:title'>."
        assert sample_metadata["title"] in val, (
            f"og:title must include the book title '{sample_metadata['title']}', got: {val!r}"
        )
        assert sample_metadata["author"] in val, (
            f"og:title must include the author '{sample_metadata['author']}', got: {val!r}"
        )

    def test_landing_page_contains_og_description(self, sample_metadata: dict) -> None:
        """Rendered HTML must have <meta property='og:description'> with non-empty content.

        Spec: decisions.md §C template — og:description is translator_note (max 200 chars)
        or the auto-generated fallback (TR-4).
        """
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        val = _og_content(parsed.meta_tags, "og:description")
        assert val, "Rendered HTML must have a non-empty <meta property='og:description'>."

    def test_landing_page_contains_og_type(self, sample_metadata: dict) -> None:
        """Rendered HTML must have <meta property='og:type' content='book'>."""
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        val = _og_content(parsed.meta_tags, "og:type")
        assert val == "book", (
            f"og:type must be 'book' per spec template, got: {val!r}"
        )

    def test_landing_page_contains_twitter_card_tags(
        self, sample_metadata: dict
    ) -> None:
        """Rendered HTML must contain Twitter Card meta tags for WhatsApp/social preview.

        Spec: decisions.md §C — 'WhatsApp, iMessage, Signal, Telegram all scrape
        raw HTTP.' Twitter Card tags ensure fallback rendering on platforms that
        prefer them over OG tags.

        NOTE: Morpheus's §C template does not yet include twitter: tags — this test
        is a spec extension flagged in .squad/decisions/inbox/dozer-twitter-card-gap.md.
        """
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        card = _twitter_content(parsed.meta_tags, "twitter:card")
        assert card, "Rendered HTML must have <meta name='twitter:card'>."
        title = _twitter_content(parsed.meta_tags, "twitter:title")
        assert title, "Rendered HTML must have <meta name='twitter:title'>."
        description = _twitter_content(parsed.meta_tags, "twitter:description")
        assert description, "Rendered HTML must have <meta name='twitter:description'>."

    def test_landing_page_contains_both_download_links(
        self, sample_metadata: dict
    ) -> None:
        """Rendered HTML must have non-empty href links to both source and translated PDFs.

        Spec: decisions.md §D — share.source_pdf_sas_url and share.translated_pdf_sas_url
        must both appear on the landing page.
        """
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)

        src_url = sample_metadata["share"]["source_pdf_sas_url"]
        trs_url = sample_metadata["share"]["translated_pdf_sas_url"]

        assert any(src_url in link for link in parsed.links), (
            f"Rendered HTML must contain a link to the source PDF SAS URL.\n"
            f"Expected: {src_url!r}\nFound links: {parsed.links}"
        )
        assert any(trs_url in link for link in parsed.links), (
            f"Rendered HTML must contain a link to the translated PDF SAS URL.\n"
            f"Expected: {trs_url!r}\nFound links: {parsed.links}"
        )

    def test_landing_page_does_not_expose_license_status(
        self, sample_metadata: dict
    ) -> None:
        """license.status must NOT appear anywhere in the rendered HTML.

        Spec: decisions.md §C — license.status is internal; readers must never see it.
        """
        html = generate_landing_html(sample_metadata)
        status_tokens = [
            "rights-unknown",
            "claimed-public-domain",
            "verified-public-domain",
            "rights-cleared",
            "license.status",
            "license_status",
        ]
        for token in status_tokens:
            assert token not in html, (
                f"generate_landing_html must not expose license metadata. "
                f"Found '{token}' in rendered HTML."
            )

    def test_landing_page_html_is_syntactically_valid(
        self, sample_metadata: dict
    ) -> None:
        """html.parser must parse the rendered output without errors."""
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        assert not parsed.errors, (
            f"generate_landing_html produced invalid HTML: {parsed.errors}"
        )

    def test_landing_page_snapshot(
        self, sample_metadata: dict, golden_html: str
    ) -> None:
        """Rendered HTML must match the golden fixture (snapshot test).

        The golden fixture is at tests/golden/landing_page_fixture.html.
        To update it: regenerate using generate_landing_html(SAMPLE_METADATA)
        and commit the new file.
        """
        html = generate_landing_html(sample_metadata)

        # Normalise whitespace for a stable comparison
        def _normalise(s: str) -> str:
            return re.sub(r"\s+", " ", s).strip()

        assert _normalise(html) == _normalise(golden_html), (
            "generate_landing_html output does not match the golden fixture. "
            "If this is intentional, update tests/golden/landing_page_fixture.html."
        )

    def test_landing_page_uses_fallback_description_when_no_translator_note(
        self, sample_metadata: dict
    ) -> None:
        """Rendered og:description must be non-empty even when translator_note is absent.

        Spec: decisions.md TR-4 — 'use a default of "{title} by {author}, translated
        from {source_language} to {target_language} by Transpose ({page_count} pages)."'
        """
        sample_metadata.pop("translator_note", None)
        html = generate_landing_html(sample_metadata)
        parsed = _parse_html(html)
        val = _og_content(parsed.meta_tags, "og:description")
        assert val, (
            "og:description must have a non-empty fallback value when translator_note "
            "is absent."
        )
        assert sample_metadata["title"] in val or sample_metadata["author"] in val, (
            "Fallback og:description should include title or author per TR-4 spec."
        )
