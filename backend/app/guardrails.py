"""Basic input/output guardrails.

These are heuristics, one layer of defence. The stronger protections are structural:
  - Presentation mode retrieves from the 'public' scope only (enforced in SQL)
  - Retrieved text is fenced and labelled as untrusted data in the prompt
  - The persona prompt forbids revealing instructions or private data
"""

import re
from dataclasses import dataclass

from .config import settings

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any )?(the )?(previous|prior|above|earlier)",
    r"forget (everything|all|your) (you|instructions|rules)",
    r"(reveal|show|print|repeat|output) (me )?(your|the) (system|hidden|initial) (prompt|instructions|message)",
    r"what (is|are) your (system|hidden|initial) (prompt|instructions)",
    r"you are now (?:in )?(dan|developer mode|jailbreak)",
    r"act as (?:if you (?:are|were) )?(?:an? )?(?:unrestricted|unfiltered|jailbroken)",
    r"pretend (that )?you (have|are) no (rules|restrictions|guidelines)",
    r"</?(system|assistant|instructions?)>",
    r"\[\s*(system|inst)\s*\]",
    r"companion mode",  # public users must not try to switch modes via text
    r"private (notes|data|index|documents)",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

# Things the model should never echo back in a public answer
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{20,}",  # API-key-like strings
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN-like
    r"\b(?:\d[ -]?){13,16}\b",  # card-number-like
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",  # email addresses
]
_SECRET_RE = re.compile("|".join(SECRET_PATTERNS))


@dataclass
class InputCheck:
    ok: bool
    reason: str = ""
    flagged: bool = False


def check_input(message: str, mode: str) -> InputCheck:
    message = message.strip()
    if not message:
        return InputCheck(ok=False, reason="Empty message.")
    if len(message) > settings.max_message_chars:
        return InputCheck(
            ok=False,
            reason=f"Message too long (max {settings.max_message_chars} characters).",
        )
    # In public mode, a match is rejected outright. In companion mode the user is
    # authenticated and trusted, so we don't block, only flag for logging.
    if _INJECTION_RE.search(message):
        if mode == "presentation":
            return InputCheck(
                ok=False,
                flagged=True,
                reason="That looks like an attempt to override my instructions, so I can't help with it. Ask me about my work, skills or background instead.",
            )
        return InputCheck(ok=True, flagged=True)
    return InputCheck(ok=True)


def scrub_output(text: str, mode: str) -> str:
    """Redact secret-looking strings from public answers."""
    if mode != "presentation":
        return text
    return _SECRET_RE.sub("[redacted]", text)


def fence_context(chunks: list[dict]) -> str:
    """Wrap retrieved chunks so the model treats them as data, not instructions."""
    if not chunks:
        return "<retrieved_context>\n(no relevant context found)\n</retrieved_context>"
    body = "\n\n".join(
        f'<chunk source="{c["source"]}" score="{c["score"]:.2f}">\n{c["content"]}\n</chunk>'
        for c in chunks
    )
    return f"<retrieved_context>\n{body}\n</retrieved_context>"
