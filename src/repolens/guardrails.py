"""Guardrails for untrusted repository content: prompt-injection phrases and secrets.

Both are plain regular expressions (ADR-0015). The injection patterns catch the common
phrasings of an instruction aimed at a model, not a determined attacker; the main defence
stays that the model sees code only as untrusted data and the Report cites only lines it was
shown. The secret patterns follow the token formats gitleaks knows, plus secret-looking
values assigned to names like `password` or `api_key`.
"""

import re

REDACTED = "[REDACTED]"

# Each pattern is described, not quoted, so this file doesn't match its own patterns.
_INJECTIONS = [
    # A verb that sets aside, then a word for the instructions given before it.
    r"\b(?:ignore|disregard|forget)\W+(?:\w+\W+){0,3}?"
    r"(?:previous|prior|above|earlier|preceding|your|all)\W+(?:\w+\W+)?"
    r"(?:instructions|directions|system\W+prompt)\b",
    # A note addressed to an AI, an LLM or a language model.
    r"\bnote\W+(?:to|for)\W+(?:the\W+|any\W+|all\W+)?(?:AI|LLM|language\W+model)s?\b",
    # A condition on the reader being an AI, an LLM or a language model.
    r"\bif\W+you\W+are\W+(?:an?\W+)?(?:AI|LLM|large\W+language\W+model|language\W+model)\b",
]
_INJECTION = re.compile("|".join(f"(?:{pattern})" for pattern in _INJECTIONS), re.IGNORECASE)

# A secret-looking value: 8+ characters with a letter and a digit, and not a URL.
_VALUE = r"(?=[^'\"\s]*\d)(?=[^'\"\s]*[A-Za-z])(?![^'\"\s]*://)[^'\"\s{}]{8,}"
_SECRETS = [
    # A private key, or the part of one in a Chunk that starts or ends inside it.
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
    r"\A(?:(?!-----BEGIN )[\s\S])*?-----END [A-Z ]*PRIVATE KEY-----",
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",  # AWS access key id
    r"\bgh[pousr]_[A-Za-z0-9]{36,}",  # GitHub tokens
    r"\bgithub_pat_[A-Za-z0-9_]{22,}",
    r"\bsk-[A-Za-z0-9_-]{20,}",  # OpenAI and Anthropic API keys
    r"\bAIza[0-9A-Za-z_-]{35}",  # Google API key
    r"\bxox[abposr]-[A-Za-z0-9-]{10,}",  # Slack tokens
    r"\b[rs]k_live_[A-Za-z0-9]{20,}",  # Stripe live keys
    r"(?<=\b[Bb]earer )[A-Za-z0-9._~+/-]{20,}=*",
    # `password = "..."`, `SECRET_KEY: str = '...'`, `"api_key": "..."`
    r"(?i:\b[\w.-]*?(?:password|passwd|secret|api_?key|access_?key|private_?key|token)"
    r"[\w-]*['\"]?\s*(?::\s*\w+\s*)?[:=]\s*['\"])(?P<value>" + _VALUE + ")",
]
_SECRET = re.compile("|".join(f"(?:{pattern})" for pattern in _SECRETS))


def looks_like_injection(text: str) -> bool:
    """Whether the text has a phrase that tells a model what to do."""
    return _INJECTION.search(text) is not None


def redact_secrets(text: str) -> str:
    """Replace each line of every secret with `[REDACTED]`, keeping the line count."""
    return _SECRET.sub(_redact, text)


def _redact(match: re.Match[str]) -> str:
    """The match with its secret redacted: the `value` of an assignment, or all of it."""
    start, end = match.span("value") if match.group("value") else match.span()
    start, end = start - match.start(), end - match.start()
    text = match.group()
    return text[:start] + re.sub(r"[^\n]+", REDACTED, text[start:end]) + text[end:]
