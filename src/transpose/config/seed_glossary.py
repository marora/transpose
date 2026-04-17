"""Curated seed glossary of culturally significant terms.

These terms should be preserved untranslated in their transliterated form.
The LLM is also instructed to detect additional terms — those get merged
into the book glossary if they appear frequently enough.
"""

# Each entry: (transliterated_term, original_script, brief_definition)
# Organized by tradition for maintainability.

SEED_TERMS: list[tuple[str, str, str]] = [
    # --- Shared / Pan-Indic ---
    ("atman", "आत्मन्", "The soul or true self"),
    ("dharma", "धर्म", "Righteous duty, moral law, cosmic order"),
    ("karma", "कर्म", "Action and its consequences across lifetimes"),
    ("moksha", "मोक्ष", "Liberation from the cycle of rebirth"),
    ("samsara", "संसार", "The cycle of death and rebirth"),
    ("maya", "माया", "Illusion; the transient material world"),
    ("guru", "गुरु", "Spiritual teacher or guide"),
    ("mantra", "मन्त्र", "Sacred utterance or syllable used in meditation"),
    ("yoga", "योग", "Spiritual discipline; union with the divine"),
    ("bhakti", "भक्ति", "Devotional worship"),
    ("ahimsa", "अहिंसा", "Non-violence"),
    ("puja", "पूजा", "Worship ritual"),
    ("avatar", "अवतार", "Divine incarnation"),
    ("shakti", "शक्ति", "Divine feminine power"),
    ("prana", "प्राण", "Life breath, vital energy"),
    ("tapas", "तपस्", "Austerity, spiritual discipline through heat"),
    ("satsang", "सत्संग", "Gathering in truth; spiritual assembly"),
    ("darshan", "दर्शन", "Sacred seeing; beholding the divine"),
    ("deva", "देव", "Divine being, deity"),
    ("rishi", "ऋषि", "Sage, seer"),
    ("veda", "वेद", "Sacred knowledge; the foundational Hindu scriptures"),
    ("sutra", "सूत्र", "Thread; a concise spiritual aphorism"),
    ("yantra", "यन्त्र", "Sacred geometric diagram"),
    ("tantra", "तन्त्र", "Esoteric spiritual practice"),
    ("samadhi", "समाधि", "Deep meditative absorption"),
    ("nirvana", "निर्वाण", "Extinction of suffering; ultimate liberation"),
    ("dharmic", "धार्मिक", "Pertaining to dharma"),
    ("yuga", "युग", "Cosmic age or epoch"),
    ("ashram", "आश्रम", "Hermitage; stage of life"),
    ("sadhu", "साधु", "Holy person, ascetic"),
    ("swami", "स्वामी", "Master; title for a renunciant"),

    # --- Sikh tradition ---
    ("sangat", "ਸੰਗਤ", "Congregation; the gathered community of Sikhs"),
    ("langar", "ਲੰਗਰ", "Community kitchen serving free meals"),
    ("seva", "ਸੇਵਾ", "Selfless service"),
    ("gurdwara", "ਗੁਰਦੁਆਰਾ", "Sikh place of worship"),
    ("gurbani", "ਗੁਰਬਾਣੀ", "The Guru's word; sacred Sikh scripture"),
    ("waheguru", "ਵਾਹਿਗੁਰੂ", "Wonderful Lord; Sikh name for God"),
    ("hukam", "ਹੁਕਮ", "Divine will or command"),
    ("naam", "ਨਾਮ", "The divine Name; meditation on God's name"),
    ("simran", "ਸਿਮਰਨ", "Remembrance of the divine through meditation"),
    ("ardas", "ਅਰਦਾਸ", "Sikh prayer"),
    ("amrit", "ਅੰਮ੍ਰਿਤ", "Nectar of immortality; Sikh baptismal water"),
    ("khalsa", "ਖ਼ਾਲਸਾ", "The community of initiated Sikhs"),
    ("kirtan", "ਕੀਰਤਨ", "Devotional singing of hymns"),
    ("bani", "ਬਾਣੀ", "Sacred utterance, divine word"),
    ("mool mantar", "ਮੂਲ ਮੰਤਰ", "The foundational verse of Sikh scripture"),
    ("panth", "ਪੰਥ", "The Sikh community or path"),
    ("raag", "ਰਾਗ", "Musical mode in which scripture is sung"),
    ("granthi", "ਗ੍ਰੰਥੀ", "Custodian of the Guru Granth Sahib"),
    ("kaur", "ਕੌਰ", "Princess; surname given to Sikh women"),
    ("singh", "ਸਿੰਘ", "Lion; surname given to Sikh men"),

    # --- Hindu philosophical terms ---
    ("brahman", "ब्रह्मन्", "The ultimate reality, universal consciousness"),
    ("purusha", "पुरुष", "Cosmic being; pure consciousness"),
    ("prakriti", "प्रकृति", "Primordial nature, material world"),
    ("jnana", "ज्ञान", "Spiritual knowledge, wisdom"),
    ("viveka", "विवेक", "Discernment, discrimination between real and unreal"),
    ("vairagya", "वैराग्य", "Detachment, dispassion"),
    ("sattva", "सत्त्व", "Quality of purity, goodness, light"),
    ("rajas", "रजस्", "Quality of passion, activity, restlessness"),
    ("tamas", "तमस्", "Quality of darkness, inertia, ignorance"),
    ("kundalini", "कुण्डलिनी", "Coiled spiritual energy at the base of the spine"),
    ("chakra", "चक्र", "Energy center in the subtle body"),
]


def get_seed_glossary() -> dict[str, tuple[str, str]]:
    """Return seed glossary as {term: (original_script, definition)}."""
    return {term: (script, defn) for term, script, defn in SEED_TERMS}
