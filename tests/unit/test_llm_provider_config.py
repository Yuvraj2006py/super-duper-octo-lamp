import pytest

from app.core.config import Settings
from app.services.writing import MockLLMProvider, OpenAICompatibleLLMProvider, build_llm_provider


def test_build_llm_provider_mock():
    settings = Settings(llm_provider="mock")
    provider = build_llm_provider(settings)
    assert isinstance(provider, MockLLMProvider)


def test_build_llm_provider_rejects_key_in_provider_field():
    bad_value = "gsk_example_secret_value"
    settings = Settings(llm_provider=bad_value, llm_api_key="")
    with pytest.raises(ValueError) as exc:
        build_llm_provider(settings)

    message = str(exc.value)
    assert "API key" in message
    assert bad_value not in message


def test_build_llm_provider_groq_uses_default_compatible_base_url():
    settings = Settings(
        llm_provider="groq",
        llm_api_key="dummy-key",
        llm_model="llama-3.3-70b-versatile",
        llm_base_url="https://api.openai.com/v1",
    )
    provider = build_llm_provider(settings)

    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.base_url == "https://api.groq.com/openai/v1"
