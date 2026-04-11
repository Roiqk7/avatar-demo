from backend.personalities.llm_baseline import (
    LLM_SYSTEM_PROMPT_FOOTER,
    LLM_SYSTEM_PROMPT_HEADER,
    compose_llm_system_prompt,
)


def test_compose_includes_header_footer_and_body():
    out = compose_llm_system_prompt("MIDDLE")
    assert out.startswith(LLM_SYSTEM_PROMPT_HEADER.strip())
    assert out.endswith(LLM_SYSTEM_PROMPT_FOOTER.strip())
    assert "\n\nMIDDLE\n\n" in out


def test_compose_empty_body_is_header_footer_only():
    out = compose_llm_system_prompt("")
    assert out == f"{LLM_SYSTEM_PROMPT_HEADER.strip()}\n\n{LLM_SYSTEM_PROMPT_FOOTER.strip()}"


def test_compose_strips_body_whitespace():
    out = compose_llm_system_prompt("  x  ")
    assert "\n\nx\n\n" in out
