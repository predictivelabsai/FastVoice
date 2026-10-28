import os

import pytest

# Tests always run offline with mock providers, regardless of keys in .env.
for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "ELEVENLABS_API_KEY", "XI_API_KEY",
          "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS_JSON", "GOOGLE_CLOUD_API_KEY"):
    os.environ[k] = ""
os.environ["KL_LLM_PROVIDER"] = "mock"
os.environ["KL_STT_PROVIDER"] = "mock"
os.environ["KL_TTS_PROVIDER"] = "mock"


@pytest.fixture(scope="session")
def kl():
    from knowledge_line.pipeline import KnowledgeLine

    return KnowledgeLine()
