"""FastVoice Knowledge Line: a provider-configurable STT -> RAG + LLM -> TTS
question-answering voice line, with Lithuanian as a first-class locale.

Runs fully offline with mock providers (no keys needed) and switches to
Google Gemini / Mistral (LLM), Google Cloud Speech / ElevenLabs (STT, TTS)
by configuration.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
