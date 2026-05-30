"""TTS provider abstraction layer.

Defines the interface for text-to-speech providers and ships the default
Azure AI Speech implementation. Provider is selected via TRANSPOSE_TTS_PROVIDER
environment variable (default: 'azure').

Implements: #125 — Configurable TTS provider abstraction layer.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TTSProviderType(str, Enum):
    """Supported TTS provider backends."""

    AZURE = "azure"
    ELEVENLABS = "elevenlabs"
    OPENAI = "openai"


@dataclass
class WordBoundary:
    """A single word's timing within the synthesized audio."""

    text: str
    start_ms: int
    end_ms: int


@dataclass
class AudioResult:
    """Result of synthesizing a single chapter/segment."""

    audio_bytes: bytes
    duration_ms: int
    word_boundaries: list[WordBoundary] = field(default_factory=list)
    character_count: int = 0
    cost_estimate: float = 0.0


@dataclass
class Voice:
    """Metadata about an available TTS voice."""

    id: str
    name: str
    language: str
    gender: str
    style_list: list[str] = field(default_factory=list)


@dataclass
class SSMLOptions:
    """Options for SSML generation — gracefully ignored by providers that don't support SSML."""

    rate: str = "-10%"
    paragraph_pause_ms: int = 500
    chapter_intro_pause_ms: int = 2000
    pronunciation_lexicon: dict[str, str] = field(default_factory=dict)
    # Map of term -> IPA pronunciation for cultural terms


class TTSProvider(ABC):
    """Abstract interface for text-to-speech providers.

    Pipeline stages call this interface — never a specific SDK directly.
    Mirrors the pattern established by OcrClient and LlmClient.
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        ssml_options: SSMLOptions | None = None,
        chapter_title: str | None = None,
    ) -> AudioResult:
        """Synthesize text into audio.

        Args:
            text: Plain text to synthesize (a full chapter or segment).
            voice: Voice identifier (provider-specific).
            ssml_options: Prosody and pronunciation settings. Providers that
                don't support SSML should ignore gracefully.
            chapter_title: If provided, a "Chapter N: Title" intro is prepended.

        Returns:
            AudioResult with audio bytes and metadata.
        """

    @abstractmethod
    async def get_available_voices(self, language: str = "en") -> list[Voice]:
        """List available voices for the given language prefix."""

    @abstractmethod
    def estimate_cost(self, character_count: int) -> float:
        """Estimate the cost in USD for synthesizing N characters."""

    @abstractmethod
    def supports_word_boundaries(self) -> bool:
        """Whether this provider can return word-level timing."""

    @abstractmethod
    def supports_ssml(self) -> bool:
        """Whether this provider supports SSML markup for prosody control."""

    async def close(self) -> None:
        """Clean up resources. Override if the provider holds connections."""


class AzureTTSProvider(TTSProvider):
    """Azure AI Speech TTS provider.

    Uses the Azure Cognitive Services Speech SDK with Neural HD voices.
    Supports full SSML, word boundary events, and pronunciation lexicons.
    """

    # Azure Neural TTS pricing: $16 per 1M characters (standard),
    # $24 per 1M characters (Neural HD)
    _COST_PER_CHAR_NEURAL_HD = 24.0 / 1_000_000

    def __init__(
        self,
        *,
        speech_key: str = "",
        speech_region: str = "",
        speech_endpoint: str = "",
        default_voice: str = "en-US-AndrewMultilingualNeural",
    ) -> None:
        self._speech_key = speech_key
        self._speech_region = speech_region
        self._speech_endpoint = speech_endpoint
        self._default_voice = default_voice
        self._synthesizer = None

    def _build_ssml(
        self,
        text: str,
        voice: str,
        ssml_options: SSMLOptions | None,
        chapter_title: str | None,
    ) -> str:
        """Build SSML document from text and options."""
        opts = ssml_options or SSMLOptions()
        voice_id = voice or self._default_voice

        # Build pronunciation lexicon entries as phoneme tags
        def _apply_lexicon(t: str) -> str:
            for term, ipa in opts.pronunciation_lexicon.items():
                t = t.replace(
                    term,
                    f'<phoneme alphabet="ipa" ph="{ipa}">{term}</phoneme>',
                )
            return t

        # Split into paragraphs for pause insertion
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        body_parts = []

        # Chapter intro
        if chapter_title:
            body_parts.append(
                f'<break time="{opts.chapter_intro_pause_ms}ms"/>'
                f"<prosody rate=\"-5%\">{chapter_title}</prosody>"
                f'<break time="{opts.chapter_intro_pause_ms}ms"/>'
            )

        for i, para in enumerate(paragraphs):
            para_ssml = _apply_lexicon(para)
            body_parts.append(f"<p>{para_ssml}</p>")
            if i < len(paragraphs) - 1:
                body_parts.append(f'<break time="{opts.paragraph_pause_ms}ms"/>')

        body = "\n".join(body_parts)

        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
            f'<voice name="{voice_id}">'
            f'<prosody rate="{opts.rate}">'
            f"{body}"
            "</prosody></voice></speak>"
        )
        return ssml

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "",
        ssml_options: SSMLOptions | None = None,
        chapter_title: str | None = None,
    ) -> AudioResult:
        """Synthesize text to audio using Azure AI Speech SDK."""
        import azure.cognitiveservices.speech as speechsdk

        voice_id = voice or self._default_voice

        # Configure speech
        if self._speech_endpoint:
            speech_config = speechsdk.SpeechConfig(endpoint=self._speech_endpoint)
            if self._speech_key:
                speech_config.subscription_key = self._speech_key
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._speech_key, region=self._speech_region
            )

        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz128KBitRateMonoMp3
        )
        speech_config.speech_synthesis_voice_name = voice_id

        # Collect word boundaries
        word_boundaries: list[WordBoundary] = []

        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None
        )

        def _on_word_boundary(evt):
            word_boundaries.append(
                WordBoundary(
                    text=evt.text,
                    start_ms=evt.audio_offset // 10_000,  # ticks to ms
                    end_ms=(evt.audio_offset + evt.duration) // 10_000,
                )
            )

        synthesizer.synthesis_word_boundary.connect(_on_word_boundary)

        # Build SSML and synthesize
        ssml = self._build_ssml(text, voice_id, ssml_options, chapter_title)
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            raise RuntimeError(
                f"TTS synthesis canceled: {cancellation.reason} — "
                f"{cancellation.error_details}"
            )

        audio_data = result.audio_data
        duration_ms = len(audio_data) * 8 // 128  # rough estimate from bitrate
        char_count = len(text)

        # More accurate duration from result if available
        if hasattr(result, "audio_duration") and result.audio_duration:
            duration_ms = int(result.audio_duration.total_seconds() * 1000)

        return AudioResult(
            audio_bytes=audio_data,
            duration_ms=duration_ms,
            word_boundaries=word_boundaries,
            character_count=char_count,
            cost_estimate=self.estimate_cost(char_count),
        )

    async def get_available_voices(self, language: str = "en") -> list[Voice]:
        """List voices from Azure Speech service."""
        import azure.cognitiveservices.speech as speechsdk

        if self._speech_endpoint:
            speech_config = speechsdk.SpeechConfig(endpoint=self._speech_endpoint)
            if self._speech_key:
                speech_config.subscription_key = self._speech_key
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._speech_key, region=self._speech_region
            )

        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None
        )
        result = synthesizer.get_voices_async(locale=language).get()

        voices = []
        if result.voices:
            for v in result.voices:
                voices.append(
                    Voice(
                        id=v.short_name,
                        name=v.local_name,
                        language=v.locale,
                        gender=str(v.gender),
                        style_list=list(v.style_list) if v.style_list else [],
                    )
                )
        return voices

    def estimate_cost(self, character_count: int) -> float:
        """Estimate cost in USD based on Azure Neural HD pricing."""
        return character_count * self._COST_PER_CHAR_NEURAL_HD

    def supports_word_boundaries(self) -> bool:
        return True

    def supports_ssml(self) -> bool:
        return True


def get_tts_provider(
    provider_type: str = "azure",
    *,
    speech_key: str = "",
    speech_region: str = "",
    speech_endpoint: str = "",
    default_voice: str = "en-US-AndrewMultilingualNeural",
) -> TTSProvider:
    """Factory function to create a TTS provider instance.

    Args:
        provider_type: One of 'azure', 'elevenlabs', 'openai'.
        speech_key: API key / subscription key.
        speech_region: Azure region (e.g., 'eastus').
        speech_endpoint: Full endpoint URL (alternative to region).
        default_voice: Default voice ID for synthesis.

    Returns:
        Configured TTSProvider instance.
    """
    ptype = TTSProviderType(provider_type.lower())

    if ptype == TTSProviderType.AZURE:
        return AzureTTSProvider(
            speech_key=speech_key,
            speech_region=speech_region,
            speech_endpoint=speech_endpoint,
            default_voice=default_voice,
        )

    if ptype == TTSProviderType.ELEVENLABS:
        raise NotImplementedError(
            "ElevenLabs TTS provider not yet implemented. "
            "Implement a class extending TTSProvider and register here."
        )

    if ptype == TTSProviderType.OPENAI:
        raise NotImplementedError(
            "OpenAI TTS provider not yet implemented. "
            "Implement a class extending TTSProvider and register here."
        )

    raise ValueError(f"Unknown TTS provider: {provider_type}")
