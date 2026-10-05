"""Gemini API helpers."""

from __future__ import annotations

from google import genai


MODEL = "gemini-3.5-flash-lite"


def smoke_test(api_key: str, context: str) -> str:
    """Send a small integration-test prompt and return Gemini's text response."""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=(
            "This is a brief integration smoke test for a newsletter digest bot. "
            "Use the context below only as source material and return one concise "
            "sentence confirming you received it.\n\n"
            f"Context: {context}"
        ),
    )
    result = (response.text or "").strip()
    if not result:
        raise RuntimeError("Gemini returned an empty response")
    return result
