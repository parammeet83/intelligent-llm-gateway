"""Deterministic prompt features. Plain regular expressions over the text, not a language model.

Limitations (documented in docs/ROUTING_METHODOLOGY.md): English-centric keyword lists, no notion
of semantic difficulty (a short riddle can score low), easy to game by adding keywords, and token
counts are estimated (~4 characters per token).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.providers.base import ChatMessage, estimate_tokens

_MULTI_STEP = re.compile(
    r"(?im)\b(step[- ]by[- ]step|first(ly)?\b.*\bthen|finally|after that|next,)\b|^\s*\d+[.)]\s+\S"
)
_CONSTRAINT = re.compile(r"(?i)\b(must|must not|should not|exactly|at most|at least|ensure|only)\b")
_REASONING = re.compile(
    r"(?i)\b(prove|derive|justify|analy[sz]e|compare|contrast|trade-?offs?|evaluate|optimi[sz]e"
    r"|explain why|root cause|critique)\b"
)
_MATH = re.compile(
    r"(?i)\b(integral|derivative|equation|probability|theorem|matrix|modulo|expected value)\b"
    r"|\d+\s*[-+*/^]\s*\d+"
)
_CODE_BLOCK = re.compile(r"```")


@dataclass(frozen=True)
class Features:
    estimated_input_tokens: int
    input_chars: int
    max_output_tokens: int
    json_output: bool
    multi_step_matches: int
    constraint_matches: int
    reasoning_matches: int
    math_matches: int
    has_code_block: bool


def extract_features(
    messages: tuple[ChatMessage, ...], *, max_output_tokens: int, json_output: bool
) -> Features:
    text = "\n".join(m.content for m in messages)
    # Only user-authored text drives complexity markers; system prompts are boilerplate.
    user_text = "\n".join(m.content for m in messages if m.role == "user")
    return Features(
        estimated_input_tokens=estimate_tokens(text),
        input_chars=len(text),
        max_output_tokens=max_output_tokens,
        json_output=json_output,
        multi_step_matches=len(_MULTI_STEP.findall(user_text)),
        constraint_matches=len(_CONSTRAINT.findall(user_text)),
        reasoning_matches=len(_REASONING.findall(user_text)),
        math_matches=len(_MATH.findall(user_text)),
        has_code_block=bool(_CODE_BLOCK.search(user_text)),
    )
