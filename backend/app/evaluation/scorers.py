"""Deterministic scorers. No LLM judge is used anywhere.

Every scorer returns ScoreResult(passed, score, details). `passed=None` means "not scorable
automatically" (e.g. code execution disabled) and is reported separately, never as a pass.

Code execution: model-generated code runs only when explicitly enabled (`allow_code_exec`), in a
separate `python -I` subprocess, inside a temporary directory, with a timeout and a stripped
environment. It is still untrusted code on the operator's machine, so it's off by default.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FENCE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```", re.DOTALL)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")
# "ANSWER: <value>" on its own line; markdown emphasis around either part is tolerated.
_FINAL_ANSWER = re.compile(
    r"^[\s*_>#-]*(?:final\s+)?answer[\s*_]*[:=][\s*_]*(.*?)[\s*_]*$", re.IGNORECASE | re.MULTILINE
)
# A sentence ends at . ! or ? followed by whitespace or the end (so "80%." and "09:12" are fine).
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
# Abbreviations and initials whose full stops don't end a sentence (abbreviation-aware counting),
# unless they are the last thing in the text.
# The currency prefix (if any) is added per case; see score_numeric.
_STRICT_NUMBER = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\.?")
_MASK = chr(0x2024)  # stands in for a full stop that doesn't end a sentence
_ABBREVIATION = re.compile(
    r"\b(?i:e\.g|i\.e|etc|vs|approx|incl|no|mr|mrs|ms|dr|prof|st|u\.s|u\.k|a\.m|p\.m)\.(?=\s+\S)"
    r"|\b[A-Z]\.(?=\s+[A-Z])",
)
_CODE_TIMEOUT_S = 10
# A strict 24-hour "HH:MM" string: ASCII digits only, two-digit hour and minute.
_HHMM = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")

PYTEST_SHIM = """
def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        return True
    raise AssertionError(f"{fn.__name__} did not raise {exc.__name__}")
"""


@dataclass(frozen=True)
class ScoreResult:
    passed: bool | None
    score: float | None
    details: dict[str, Any] = field(default_factory=dict)


def _norm(text: str, *, case_sensitive: bool = False) -> str:
    text = text.strip().strip("`").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" .!\"'")
    return text if case_sensitive else text.lower()


def strip_fences(text: str) -> str:
    match = _FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def _numbers(text: str) -> list[float]:
    values = []
    for raw in _NUMBER.findall(text):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return values


def score_choice(output: str, spec: dict[str, Any]) -> ScoreResult:
    labels = [str(label).lower() for label in spec["labels"]]
    # Longest labels first so "not_spam" isn't read as "spam".
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(lb) for lb in sorted(labels, key=len, reverse=True)) + r")\b"
    )
    found = pattern.findall(output.lower())
    distinct = list(dict.fromkeys(found))
    chosen = distinct[0] if len(distinct) == 1 else None
    passed = chosen == str(spec["answer"]).lower()
    return ScoreResult(passed, 1.0 if passed else 0.0, {"labels_found": distinct})


def score_exact(output: str, spec: dict[str, Any]) -> ScoreResult:
    """`accept`: further strings that are equally correct (e.g. formatting variants)."""
    cs = bool(spec.get("case_sensitive"))
    got = _norm(output, case_sensitive=cs)
    wanted = {_norm(str(a), case_sensitive=cs) for a in [spec["answer"], *spec.get("accept", [])]}
    passed = got in wanted
    return ScoreResult(passed, 1.0 if passed else 0.0, {"normalised_output": got[:200]})


def score_regex(output: str, spec: dict[str, Any]) -> ScoreResult:
    """`strip_fences`: match inside the first fenced code block, if there is one."""
    text = strip_fences(output) if spec.get("strip_fences") else output.strip()
    passed = re.search(spec["pattern"], text) is not None
    return ScoreResult(passed, 1.0 if passed else 0.0)


def final_answer(output: str) -> str | None:
    """The value on the last `ANSWER: ...` line, or None if there is none."""
    matches = _FINAL_ANSWER.findall(output)
    return matches[-1].strip() if matches else None


def count_sentences(text: str, *, abbreviation_aware: bool = False) -> int:
    """Count sentences. `abbreviation_aware` (opt-in, so v2 scoring is unchanged) doesn't end a
    sentence at common abbreviations ("e.g.", "Dr.", "a.m.") or at single-letter initials."""
    body = text.strip()
    if not body:
        return 0
    if abbreviation_aware:
        body = _ABBREVIATION.sub(lambda m: m.group(0).replace(".", _MASK), body)
    ends = len(_SENTENCE_END.findall(body))
    # Trailing text without closing punctuation is still a sentence.
    return ends + (0 if _SENTENCE_END.search(body[-1:] + " ") else 1)


def score_numeric(output: str, spec: dict[str, Any]) -> ScoreResult:
    """`strict_number` (opt-in): the whole value must be one number (correctly grouped thousands
    commas, optional trailing full stop) with no other text. `currency_symbols` lists the
    symbols allowed in front of it; v5+ cases always set it ([] for non-currency answers). When
    it's absent, the v4 behaviour (an optional `$`) applies."""
    if spec.get("strict_number"):
        bare = output.strip().strip("*_`").strip()
        symbols = spec.get("currency_symbols", ["$"])
        prefix = "(?:" + "|".join(re.escape(s) for s in symbols) + ")?" if symbols else ""
        if not re.fullmatch(prefix + _STRICT_NUMBER.pattern, bare):
            return ScoreResult(False, 0.0, {"reason": "not exactly one number", "value": bare[:80]})
    numbers = _numbers(output)
    if not numbers:
        return ScoreResult(False, 0.0, {"reason": "no number found"})
    if spec.get("last_number"):
        value = numbers[-1]
    elif spec.get("first_number"):
        # For a final-answer line such as "328 (sum of 15 primes)".
        value = numbers[0]
    elif len(numbers) == 1:
        value = numbers[0]
    else:
        # Several numbers and no "last line" convention: ambiguous, so not a pass.
        return ScoreResult(
            False, 0.0, {"reason": "ambiguous: several numbers", "numbers": numbers[:10]}
        )
    passed = abs(value - float(spec["answer"])) <= float(spec.get("tolerance", 0))
    return ScoreResult(passed, 1.0 if passed else 0.0, {"value": value})


def _has_word(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", text) is not None


def score_contains(output: str, spec: dict[str, Any]) -> ScoreResult:
    text = output.lower()
    checks: dict[str, bool] = {}
    for term in spec.get("all", []):
        checks[f"all:{term}"] = term.lower() in text
    if spec.get("any"):
        checks["any:" + "|".join(spec["any"])] = any(t.lower() in text for t in spec["any"])
    # Each group is a list of equally acceptable spellings; every group needs one of them.
    for group in spec.get("groups", []):
        checks["group:" + "|".join(group)] = any(t.lower() in text for t in group)
    for term in spec.get("none", []):
        checks[f"none:{term}"] = term.lower() not in text
    # Whole-word variants, so "now" doesn't match "know" and "please" doesn't match "pleased".
    for term in spec.get("all_words", []):
        checks[f"all_words:{term}"] = _has_word(text, term)
    for term in spec.get("none_words", []):
        checks[f"none_words:{term}"] = not _has_word(text, term)
    if "max_words" in spec:
        checks[f"max_words:{spec['max_words']}"] = len(output.split()) <= int(spec["max_words"])
    if "max_sentences" in spec:
        aware = spec.get("sentence_rules") == "abbreviation_aware"
        checks[f"max_sentences:{spec['max_sentences']}"] = count_sentences(
            output, abbreviation_aware=aware
        ) <= int(spec["max_sentences"])
    # Whole answer, ignoring surrounding whitespace, quotes and markdown emphasis.
    bare = output.strip().strip("\"'`*_ ").strip()
    if "starts_with_word" in spec:
        word = re.escape(str(spec["starts_with_word"]))
        checks[f"starts_with_word:{spec['starts_with_word']}"] = (
            re.match(rf"(?i){word}(?!\w)", bare) is not None
        )
    if "ends_with" in spec:
        checks[f"ends_with:{spec['ends_with']}"] = bare.endswith(str(spec["ends_with"]))
    passed = all(checks.values()) if checks else False
    score = sum(checks.values()) / len(checks) if checks else 0.0
    details: dict[str, Any] = {"checks": checks}
    if spec.get("needs_human_review"):
        details["needs_human_review"] = True
        details["rubric"] = spec.get("rubric")
    return ScoreResult(passed, round(score, 4), details)


def _path(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _equal(got: Any, want: Any) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want
    if isinstance(want, int | float) and isinstance(got, int | float):
        return abs(float(got) - float(want)) < 1e-9
    if isinstance(want, str) and isinstance(got, str):
        return got.strip().lower() == want.strip().lower()
    return bool(got == want)


def _json_type_ok(value: Any, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    raise ValueError(f"unknown JSON type {kind!r}")


def score_json(output: str, spec: dict[str, Any]) -> ScoreResult:
    try:
        data = json.loads(strip_fences(output))
    except (json.JSONDecodeError, ValueError):
        return ScoreResult(False, 0.0, {"reason": "invalid JSON"})
    checks: dict[str, bool] = {}
    for key, want in (spec.get("expected_subset") or {}).items():
        checks[f"field:{key}"] = isinstance(data, dict) and _equal(data.get(key), want)
    # `exact_keys` (opt-in): the top-level object must have exactly the expected keys.
    if spec.get("exact_keys"):
        checks["exact_keys"] = isinstance(data, dict) and set(data) == set(
            spec.get("expected_subset") or {}
        )
    # `field_types` (opt-in): JSON type per key, e.g. 45.0 is not an "integer".
    for key, kind in (spec.get("field_types") or {}).items():
        checks[f"type:{key}"] = isinstance(data, dict) and _json_type_ok(data.get(key), kind)
    if "list_contains" in spec:
        lc = spec["list_contains"]
        items = _path(data, lc["path"])
        names = {
            str(i.get(lc["key"], "")).strip().lower() for i in items or [] if isinstance(i, dict)
        }
        for value in lc["values"]:
            checks[f"contains:{value}"] = value.lower() in names
    if "list_values" in spec:
        lv = spec["list_values"]
        totals: dict[str, float] = {}
        for item in _path(data, lv["path"]) or []:
            if isinstance(item, dict) and isinstance(item.get(lv["value_key"]), int | float):
                key = str(item.get(lv["key"], "")).strip().upper()
                totals[key] = totals.get(key, 0) + float(item[lv["value_key"]])
        for key, want in lv["expected"].items():
            checks[f"value:{key}"] = totals.get(key.upper()) == float(want)
    if "list_pairs" in spec:
        # String field per item, matched by key; each expected value is a string or a list of
        # equally acceptable strings (case-insensitive, trimmed).
        lp = spec["list_pairs"]
        found = {
            str(i.get(lp["key"], "")).strip().lower(): str(i.get(lp["value_key"], ""))
            .strip()
            .lower()
            for i in _path(data, lp["path"]) or []
            if isinstance(i, dict)
        }
        for key, want in lp["expected"].items():
            options = {w.strip().lower() for w in ([want] if isinstance(want, str) else want)}
            checks[f"pair:{key}"] = found.get(key.strip().lower()) in options
    if "list_records" in spec:
        # Records keyed by one field (trimmed, case-insensitive). Every expected key must appear
        # exactly once with every listed field equal; with `exact`, no other keys are allowed.
        lr = spec["list_records"]
        items = _path(data, lr["path"])
        records: dict[str, list[dict[str, Any]]] = {}
        well_formed = isinstance(items, list) and all(isinstance(i, dict) for i in items)
        for item in items if well_formed else []:
            records.setdefault(str(item.get(lr["key"], "")).strip().lower(), []).append(item)
        checks[f"records:{lr['path']}:well_formed"] = well_formed
        checks[f"records:{lr['path']}:no_duplicates"] = well_formed and all(
            len(v) == 1 for v in records.values()
        )
        expected = {str(k).strip().lower(): v for k, v in lr["expected"].items()}
        if lr.get("exact"):
            checks[f"records:{lr['path']}:exact_keys"] = well_formed and set(records) == set(
                expected
            )
        for key, fields in expected.items():
            matches = records.get(key, [])
            checks[f"record:{key}"] = len(matches) == 1 and all(
                _equal(matches[0].get(f), want) for f, want in fields.items()
            )
    if "list_length" in spec:
        ll = spec["list_length"]
        items = _path(data, ll["path"])
        checks[f"length:{ll['path']}"] = isinstance(items, list) and len(items) == int(ll["equals"])
    if "numeric" in spec:
        num = spec["numeric"]
        got = _path(data, num["path"])
        checks[f"numeric:{num['path']}"] = (
            isinstance(got, int | float)
            and not isinstance(got, bool)
            and abs(float(got) - float(num["answer"])) <= float(num.get("tolerance", 0))
        )
    passed = all(checks.values()) if checks else False
    return ScoreResult(
        passed, round(sum(checks.values()) / len(checks), 4) if checks else 0.0, {"checks": checks}
    )


def score_code(output: str, spec: dict[str, Any], *, allow_exec: bool) -> ScoreResult:
    if not allow_exec:
        return ScoreResult(None, None, {"reason": "code execution disabled (--allow-code-exec)"})
    code = strip_fences(output)
    # `python -I` drops the script directory from sys.path, so the test helper is registered
    # in-process instead of being importable from disk.
    shim = (
        "import sys as _sys, types as _types\n"
        "_shim = _types.ModuleType('pytest_shim')\n"
        f"exec({PYTEST_SHIM!r}, _shim.__dict__)\n"
        "_sys.modules['pytest_shim'] = _shim\n"
    )
    script = shim + code + "\n\n" + "\n".join(spec["tests"]) + "\nprint('ALL_TESTS_PASSED')\n"
    with tempfile.TemporaryDirectory(prefix="rw-eval-") as tmp:
        Path(tmp, "candidate.py").write_text(script, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "candidate.py"],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=_CODE_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ScoreResult(False, 0.0, {"reason": f"timed out after {_CODE_TIMEOUT_S}s"})
    passed = proc.returncode == 0 and "ALL_TESTS_PASSED" in proc.stdout
    error = proc.stderr.strip().splitlines()[-1:] if proc.stderr else []
    return ScoreResult(passed, 1.0 if passed else 0.0, {"error": error[0][:200] if error else None})


def _meeting_schedule(output: str, *, strict_hhmm: bool = False) -> ScoreResult:
    """`strict_hhmm` (opt-in, the v5.2.1 C12 amendment): every start time must be a JSON string
    in strict HH:MM form, so "9:30", "09:30:00", "0930" or 9.5 fail instead of being parsed."""
    try:
        data = json.loads(strip_fences(output))
        starts = {k: data[k] for k in ("A", "B", "C")}
        minutes = {}
        for key, value in starts.items():
            if strict_hhmm and not (isinstance(value, str) and _HHMM.fullmatch(value)):
                return ScoreResult(
                    False,
                    0.0,
                    {"reason": f"{key} is not a strict HH:MM string", "value": str(value)[:40]},
                )
            hh, mm = str(value).split(":")
            minutes[key] = int(hh) * 60 + int(mm)
    except (ValueError, KeyError, TypeError, AttributeError):
        return ScoreResult(False, 0.0, {"reason": "invalid schedule JSON"})
    length = {"A": 60, "B": 30, "C": 30}
    spans = {k: (minutes[k], minutes[k] + length[k]) for k in minutes}
    checks = {
        "within_9_to_11": all(s >= 540 and e <= 660 for s, e in spans.values()),
        "no_overlap": all(
            spans[a][1] <= spans[b][0] or spans[b][1] <= spans[a][0]
            for a in spans
            for b in spans
            if a < b
        ),
        "A_before_B": spans["A"][0] < spans["B"][0],
        "C_ends_by_10": spans["C"][1] <= 600,
    }
    passed = all(checks.values())
    return ScoreResult(passed, round(sum(checks.values()) / len(checks), 4), {"checks": checks})


def _meeting_schedule_hhmm(output: str) -> ScoreResult:
    return _meeting_schedule(output, strict_hhmm=True)


VALIDATORS = {
    "meeting_schedule": _meeting_schedule,
    "meeting_schedule_hhmm": _meeting_schedule_hhmm,
}


def score(output: str, spec: dict[str, Any], *, allow_code_exec: bool = False) -> ScoreResult:
    """`final_answer: true` scores only the value on the last `ANSWER:` line (missing = fail), so
    working shown above it can't be mistaken for the answer."""
    if spec.get("final_answer"):
        value = final_answer(output)
        if value is None:
            return ScoreResult(False, 0.0, {"reason": "no ANSWER: line"})
        inner = score(
            value,
            {k: v for k, v in spec.items() if k != "final_answer"},
            allow_code_exec=allow_code_exec,
        )
        return ScoreResult(
            inner.passed, inner.score, {**inner.details, "final_answer": value[:200]}
        )
    method = spec["method"]
    if method == "choice":
        return score_choice(output, spec)
    if method == "exact":
        return score_exact(output, spec)
    if method == "regex":
        return score_regex(output, spec)
    if method == "numeric":
        return score_numeric(output, spec)
    if method == "contains":
        return score_contains(output, spec)
    if method == "json":
        return score_json(output, spec)
    if method == "code":
        return score_code(output, spec, allow_exec=allow_code_exec)
    if method == "validator":
        return VALIDATORS[spec["name"]](output)
    raise ValueError(f"unknown scoring method {method}")
