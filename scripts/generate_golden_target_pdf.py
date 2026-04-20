#!/usr/bin/env python3
"""Generate the Golden Target English PDF for QA benchmarking.

This script creates a stable reference English PDF that represents the
"correct" translation of the Golden Source Hindi PDF
(tests/fixtures/test-hindi-10page.pdf). It is checked in and never
regenerated automatically — update only when the pipeline legitimately
improves.

Usage:
    python scripts/generate_golden_target_pdf.py
"""

from __future__ import annotations

import html
from pathlib import Path

# ---------------------------------------------------------------------------
# Content — faithful English rendering of the Hindi source chapters
# ---------------------------------------------------------------------------

TITLE = "Hindi Literature and Culture — Test Booklet"
SUBTITLE = "हिन्दी साहित्य और संस्कृति — परीक्षण पुस्तिका"

CHAPTERS: list[dict[str, str]] = [
    {
        "number": "1",
        "title": "Dharma and Karma — The Message of the Gita",
        "content": (
            "The Shrimad Bhagavad Gita, composed on the battlefield of Kurukshetra, "
            "remains one of the most profound philosophical texts in Indian heritage. "
            "At its core lies the dialogue between Prince Arjuna and Lord Krishna, who "
            "serves as both charioteer and divine counselor. The text explores the "
            "nature of dharma — righteous duty — and the concept of nishkama karma, "
            "selfless action performed without attachment to its fruits. Krishna's "
            "teaching urges Arjuna to fulfill his obligations as a warrior while "
            "remaining spiritually detached from the outcomes of battle.\n\n"
            "The Gita synthesizes several strands of Indian philosophy: the path of "
            "knowledge (jnana yoga), the path of devotion (bhakti yoga), and the "
            "path of selfless action (karma yoga). Each offers a distinct route toward "
            "spiritual liberation, yet all converge on the principle that one must "
            "act in accordance with dharma. The text's enduring relevance lies in its "
            "universality — its ethical framework applies as readily to modern moral "
            "dilemmas as it did to Arjuna's crisis of conscience on the ancient "
            "battlefield. Scholars across centuries have returned to the Gita for its "
            "nuanced treatment of duty, free will, and the nature of the self."
        ),
    },
    {
        "number": "2",
        "title": "Yoga and Meditation — Physical and Spiritual Discipline",
        "content": (
            "Yoga, derived from the Sanskrit root 'yuj' meaning to unite, represents "
            "one of India's oldest contributions to human well-being. Far more than a "
            "system of physical postures, classical yoga encompasses an eight-limbed "
            "path (ashtanga) outlined by the sage Patanjali in the Yoga Sutras. These "
            "eight limbs progress from ethical observances (yama and niyama) through "
            "physical postures (asana) and breath control (pranayama) to the higher "
            "stages of sensory withdrawal (pratyahara), concentration (dharana), "
            "meditation (dhyana), and ultimately samadhi — a state of transcendent "
            "absorption in which the practitioner experiences union with the divine.\n\n"
            "The practice of pranayama, or regulated breathing, serves as a bridge "
            "between the physical and spiritual dimensions of yoga. Ancient texts "
            "describe how control of the breath leads to control of the mind, which "
            "in turn opens the door to deeper states of awareness. In contemporary "
            "India and across the world, yoga has gained recognition not only as a "
            "spiritual discipline but as a scientifically validated approach to stress "
            "reduction, physical health, and mental clarity. The United Nations' "
            "declaration of International Yoga Day in 2015 affirmed yoga's global "
            "significance as a cultural and health practice rooted in Indian tradition."
        ),
    },
    {
        "number": "3",
        "title": "Sikh Tradition — Sangat, Langar, and Seva",
        "content": (
            "Sikhism, founded by Guru Nanak in the fifteenth century in the Punjab "
            "region, emerged as a distinctive spiritual movement emphasizing devotion "
            "to one universal God (waheguru), equality of all human beings, and "
            "service to the community. The tradition developed through ten successive "
            "Gurus, each contributing to the refinement of Sikh theology and practice. "
            "Central to Sikh worship is the concept of sangat — the sacred congregation "
            "that gathers in the gurdwara to pray, sing devotional hymns (kirtan), and "
            "listen to readings from the Guru Granth Sahib, the holy scripture.\n\n"
            "Equally significant is the institution of langar, the communal kitchen "
            "found in every gurdwara, which serves free meals to all visitors without "
            "distinction of caste, creed, or social standing. Langar embodies the "
            "Sikh principle of seva — selfless service — and stands as a powerful "
            "expression of egalitarianism. The Golden Temple in Amritsar feeds tens "
            "of thousands daily through its langar, making it one of the largest "
            "community kitchens in the world. These practices of sangat, langar, and "
            "seva form the practical foundation of Sikh life and continue to inspire "
            "communities far beyond the Punjab."
        ),
    },
    {
        "number": "4",
        "title": "Moksha and Vedanta Philosophy",
        "content": (
            "Moksha, the concept of liberation from the cycle of birth, death, and "
            "rebirth (samsara), stands as the supreme goal in Hindu philosophical "
            "thought. The Vedanta school, particularly the Advaita (non-dual) "
            "tradition expounded by Adi Shankaracharya, teaches that the individual "
            "soul (atman) is ultimately identical with the universal spirit (Brahman). "
            "Ignorance (avidya) creates the illusion of separation; through knowledge "
            "and spiritual practice, this veil of maya is lifted, and the seeker "
            "attains liberation.\n\n"
            "The path to moksha is intimately connected with the doctrine of karma — "
            "the moral law of cause and effect that governs the cycle of rebirth. "
            "Actions performed in accordance with dharma gradually purify the soul, "
            "while attachment to the fruits of action binds it more tightly to "
            "samsara. The Upanishads, which form the philosophical culmination of "
            "the Vedas, elaborate extensively on the nature of moksha and the means "
            "to achieve it. Whether through jnana (knowledge), bhakti (devotion), "
            "or karma (action), the aspirant strives to transcend the limitations "
            "of material existence and realize the infinite nature of the self."
        ),
    },
    {
        "number": "5",
        "title": "Hindi Literature — From Kabir to Premchand",
        "content": (
            "The history of Hindi literature spans several centuries and encompasses "
            "a rich diversity of voices, genres, and movements. Among the earliest "
            "and most influential poets is Kabir, the fifteenth-century mystic weaver "
            "whose dohas (couplets) challenged religious orthodoxy with their emphasis "
            "on direct spiritual experience over ritual. Kabir's bhakti poetry, "
            "composed in a language accessible to common people, transcended the "
            "boundaries of Hinduism and Islam, advocating a path of inner devotion "
            "stripped of sectarian divisions.\n\n"
            "The modern era of Hindi prose was shaped decisively by Munshi Premchand, "
            "often called the emperor of Hindi fiction. Writing in the early twentieth "
            "century, Premchand brought the concerns of rural India — poverty, caste "
            "oppression, and social injustice — into the literary mainstream. His "
            "novels, including Godan and Nirmala, combined realism with deep moral "
            "conviction, earning him recognition as a champion of social justice "
            "through literature. Between Kabir's medieval devotional verse and "
            "Premchand's modern social realism lies the Romantic period (Chhayavaad), "
            "represented by poets like Jaishankar Prasad and Mahadevi Varma, who "
            "brought lyrical beauty and emotional depth to Hindi poetry."
        ),
    },
    {
        "number": "6",
        "title": "Bollywood and Indian Cinema",
        "content": (
            "The Indian film industry, popularly known as Bollywood, stands as one "
            "of the largest and most prolific centers of cinematic production in the "
            "world. Rooted in a tradition that stretches back to Dadasaheb Phalke's "
            "Raja Harishchandra in 1913, Indian cinema has evolved from silent films "
            "to a vibrant industry producing over a thousand films annually in dozens "
            "of languages. Hindi cinema, centered in Mumbai, has historically served "
            "as the cultural lingua franca of the nation, its songs, dialogues, and "
            "characters woven into the fabric of everyday Indian life.\n\n"
            "Bollywood's distinctive style — blending narrative drama with song-and-"
            "dance sequences, elaborate choreography, and colorful visual spectacle — "
            "reflects the diverse cultural traditions of the subcontinent. The industry "
            "has also served as a mirror for social change, with filmmakers addressing "
            "themes of national identity, gender equality, religious harmony, and "
            "economic aspiration. In recent decades, a new wave of independent and "
            "art-house cinema has expanded the boundaries of Indian filmmaking, "
            "garnering international acclaim and bringing fresh perspectives to "
            "audiences at home and abroad."
        ),
    },
    {
        "number": "7",
        "title": "Festivals and Traditions",
        "content": (
            "India's calendar is punctuated by a remarkable array of festivals that "
            "reflect the country's religious, cultural, and agrarian traditions. "
            "Diwali, the festival of lights, celebrates the triumph of light over "
            "darkness and good over evil, with families illuminating their homes with "
            "oil lamps and sharing sweets with neighbors. Holi, the festival of "
            "colors, heralds the arrival of spring and dissolves social barriers as "
            "participants drench one another in brightly colored powders and water.\n\n"
            "Beyond these widely known celebrations, India observes hundreds of "
            "regional and local festivals tied to harvest cycles, seasonal changes, "
            "and the commemorations of saints and deities. Pongal in Tamil Nadu, "
            "Baisakhi in Punjab, Onam in Kerala, and Bihu in Assam are all rooted "
            "in agrarian traditions that honor the earth's bounty. These festivals "
            "serve as vital threads in the social fabric, reinforcing community "
            "bonds, preserving oral traditions, and transmitting cultural values "
            "from one generation to the next."
        ),
    },
    {
        "number": "8",
        "title": "Ayurveda and Ancient Medicine",
        "content": (
            "Ayurveda, often translated as 'the science of life,' is one of the "
            "world's oldest systems of holistic medicine, with roots extending back "
            "over three thousand years to the Vedic period. The foundational texts "
            "of Ayurveda — the Charaka Samhita and the Sushruta Samhita — describe "
            "a comprehensive medical system based on the balance of three vital "
            "energies or doshas: vata (air), pitta (fire), and kapha (earth and "
            "water). Health, in the Ayurvedic view, is the harmonious equilibrium "
            "of these forces within the individual.\n\n"
            "The guru tradition played a central role in the transmission of "
            "Ayurvedic knowledge, with teachers passing detailed medical wisdom to "
            "students through oral instruction and apprenticeship. Alongside herbal "
            "remedies and dietary regimens, Ayurveda integrates practices of yoga "
            "and meditation as essential components of preventive care. The concept "
            "of prana — vital life force — connects Ayurveda to the broader Indian "
            "philosophical tradition, linking physical health with spiritual "
            "well-being. Today, Ayurveda continues to be practiced widely in India "
            "and has gained a growing following internationally as a complementary "
            "approach to modern medicine."
        ),
    },
    {
        "number": "9",
        "title": "Conclusion — The Continuity of Indian Culture",
        "content": (
            "Indian culture, with its extraordinary continuity across millennia, "
            "represents one of humanity's most enduring civilizational achievements. "
            "From the philosophical insights of the Upanishads to the devotional "
            "fervor of the bhakti movement, from the scientific precision of ancient "
            "mathematics to the artistic grandeur of temple architecture, India's "
            "cultural heritage is characterized by both diversity and an underlying "
            "coherence. The concepts of dharma, karma, and yoga are not relics of a "
            "distant past; they remain living principles that shape the daily lives "
            "of millions.\n\n"
            "The strength of Indian culture lies in its capacity for synthesis — its "
            "ability to absorb new influences while retaining its essential character. "
            "Whether in the fusion of classical and contemporary music, the adaptation "
            "of traditional textiles to modern fashion, or the integration of ancient "
            "wellness practices with scientific research, Indian culture continues to "
            "evolve without losing its roots. As India engages with the challenges "
            "and opportunities of the twenty-first century, the timeless values "
            "embedded in its cultural traditions — compassion, duty, spiritual "
            "inquiry, and communal harmony — offer enduring guidance for a rapidly "
            "changing world."
        ),
    },
]


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def build_html() -> str:
    """Build the full HTML document for WeasyPrint rendering."""
    parts: list[str] = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head><meta charset="UTF-8"></head>',
        '<body>',
    ]

    # -- Cover page --
    parts.append("<div class='title-page'>")
    parts.append(f"<div class='title'>{_esc(TITLE)}</div>")
    parts.append(f"<div class='subtitle'>{_esc(SUBTITLE)}</div>")
    parts.append("<hr class='title-separator'>")
    parts.append("</div>")

    # -- Table of Contents --
    parts.append("<div class='toc-page'>")
    parts.append("<h1>Table of Contents</h1>")
    parts.append("<ul class='toc'>")
    for ch in CHAPTERS:
        ch_id = f"chapter-{ch['number']}"
        parts.append(
            f"<li class='toc-entry'><a href='#{ch_id}'><span class='toc-title'>"
            f"Chapter {ch['number']}: {_esc(ch['title'])}</span></a></li>"
        )
    parts.append("</ul></div>")

    # -- Reset page counter for body --
    parts.append("<div style='counter-reset: page 1;'></div>")

    # -- Chapters --
    for ch in CHAPTERS:
        ch_id = f"chapter-{ch['number']}"
        parts.append(f"<h1 id='{ch_id}'>Chapter {ch['number']}: {_esc(ch['title'])}</h1>")
        for para in ch["content"].split("\n\n"):
            stripped = para.strip()
            if stripped:
                parts.append(f"<p>{_esc(stripped)}</p>")

    parts.append("</body></html>")
    return "\n".join(parts)


def build_css(font_path: Path) -> str:
    """Return the CSS stylesheet string."""
    return f"""
    @font-face {{
        font-family: 'Noto Sans Devanagari';
        src: url('file://{font_path}') format('truetype');
        font-weight: normal;
        font-style: normal;
    }}
    @page {{
        size: A4;
        margin: 2.5cm;
        @bottom-center {{
            content: counter(page);
            font-size: 10pt;
            color: #666;
        }}
    }}
    @page :first {{
        @bottom-center {{
            content: none;
        }}
    }}
    .title-page, .toc-page {{
        page: frontmatter;
    }}
    @page frontmatter {{
        @bottom-center {{
            content: counter(page, lower-roman);
            font-size: 10pt;
            color: #666;
        }}
    }}
    body {{
        font-family: Georgia, 'Noto Sans Devanagari', serif;
        line-height: 1.6;
        font-size: 12pt;
    }}
    h1 {{
        font-size: 24pt;
        margin-top: 2em;
        page-break-before: always;
    }}
    h1:first-of-type {{
        page-break-before: avoid;
    }}
    p {{
        margin: 1em 0;
        text-align: justify;
    }}
    .title-page {{
        text-align: center;
        padding-top: 3cm;
        page-break-after: always;
    }}
    .title {{
        font-size: 32pt;
        font-weight: bold;
        letter-spacing: 2px;
        margin-bottom: 1em;
    }}
    .subtitle {{
        font-size: 16pt;
        font-style: italic;
        color: #444;
        margin-bottom: 2em;
    }}
    .title-separator {{
        border: none;
        border-top: 2px solid #666;
        width: 40%;
        margin: 2em auto;
    }}
    .toc-page {{
        page-break-after: always;
    }}
    .toc-page h1 {{
        text-align: center;
        page-break-before: avoid;
    }}
    .toc {{
        list-style: none;
        padding: 0;
    }}
    .toc-entry {{
        padding: 0.5em 0;
        border-bottom: 1px dotted #ccc;
        font-size: 14pt;
    }}
    .toc-entry a {{
        text-decoration: none;
        color: inherit;
        display: flex;
        justify-content: space-between;
    }}
    .toc-entry a::after {{
        content: target-counter(attr(href url), page);
        font-style: normal;
    }}
    """


def main() -> None:
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    repo_root = Path(__file__).resolve().parents[1]
    font_path = repo_root / "fonts" / "NotoSansDevanagari.ttf"
    output_path = repo_root / "tests" / "golden" / "golden-target-english.pdf"

    print(f"Repo root:   {repo_root}")
    print(f"Font path:   {font_path} (exists={font_path.exists()})")
    print(f"Output path: {output_path}")

    font_config = FontConfiguration()
    stylesheet = CSS(string=build_css(font_path), font_config=font_config)
    html_content = build_html()

    pdf_bytes = HTML(string=html_content).write_pdf(
        stylesheets=[stylesheet],
        font_config=font_config,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)

    size_kb = len(pdf_bytes) / 1024
    print(f"Generated: {output_path.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
