"""Shared LLM system-prompt framing: header + per-avatar body + footer.

YAML ``llm.system_prompt`` and env ``LLM_SYSTEM_PROMPT`` supply the **body** only.
:func:`compose_llm_system_prompt` prepends :data:`LLM_SYSTEM_PROMPT_HEADER` and appends
:data:`LLM_SYSTEM_PROMPT_FOOTER`.
"""

from __future__ import annotations

LLM_SYSTEM_PROMPT_HEADER = """You are a helpful assistant. You represent Signosoft: you work for this company and care about e-signing—electronic signatures, signing in general. You hate other e-signing companies like DocuSign and Adobe Sign."""

LLM_SYSTEM_PROMPT_FOOTER = """Stay safe: no slurs, hate, or explicit content. Keep replies brief and practical—about one to three spoken sentences unless the user wants more."""


def compose_llm_system_prompt(body: str) -> str:
    """Return ``header + body + footer`` with blank lines between non-empty parts."""
    chunks: list[str] = [LLM_SYSTEM_PROMPT_HEADER.strip()]
    mid = body.strip()
    if mid:
        chunks.append(mid)
    chunks.append(LLM_SYSTEM_PROMPT_FOOTER.strip())
    return "\n\n".join(chunks)
