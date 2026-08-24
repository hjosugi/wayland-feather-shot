"""Finding text worth redacting.

Pure Python — no GTK, no OCR engine — so the rules, the merging and the
deduplication are unit-testable on their own.  The caller supplies recognised
words with their boxes; where those come from is :mod:`..recognize`.

Redacting a screenshot before sharing means finding every token, email address
and IP by eye, and missing one is the whole risk — the failure is silent.  This
proposes the regions; **it never applies them**.  A false negative must not read
as "this image is clean", so what comes back is a suggestion the user confirms,
adjusts or throws away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Rect = Tuple[float, float, float, float]   # normalized x, y, w, h


@dataclass(frozen=True)
class Word:
    """One recognised word and where it sits, in image pixels."""

    text: str
    x: float
    y: float
    w: float
    h: float
    #: Groups words into the line they were read from.
    line: Tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True)
class Region:
    """A proposed redaction, in normalized image coordinates."""

    rect: Rect
    text: str
    rule: str


def luhn(digits: Sequence[int]) -> bool:
    """The check digit every real payment card carries.

    Without it any run of 13–19 digits — an order number, a serial, a phone
    with the spaces stripped — reads as a card.
    """
    total = 0
    double = False
    for digit in reversed(list(digits)):
        value = digit * 2 if double else digit
        if value > 9:
            value -= 9
        total += value
        double = not double
    return total % 10 == 0


def _is_ipv4(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False
    return True


def _is_phone(value: str) -> bool:
    return 8 <= sum(c.isdigit() for c in value) <= 15


def _is_card(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    return 13 <= len(digits) <= 19 and luhn(digits)


def _is_opaque_token(value: str) -> bool:
    """A long mixed-case-and-digits run with few separators.

    Deliberately conservative: prose and file paths are full of long words, and
    a rule that fires on those trains people to ignore the suggestions.
    """
    if len(value) < 24:
        return False
    if not (any(c.isalpha() for c in value) and any(c.isdigit() for c in value)):
        return False
    separators = sum(1 for c in value if c in "-_")
    return separators <= max(6, len(value) // 8)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    accepts: Optional[Callable[[str], bool]] = None
    #: Which capture group to redact; 0 is the whole match.
    group: int = 0


RULES: Tuple[Rule, ...] = (
    Rule("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    Rule("url", r"\bhttps?://[^\s<>\"']+"),
    Rule("host", r"\bwww\.[^\s<>\"']+"),
    Rule("ipv4", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", _is_ipv4),
    Rule("jwt", r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    # Prefixed keys come in three shapes: separated by _ or - (Stripe,
    # GitHub, Slack), run straight on (AWS, Google API), or separated by a dot
    # (Google OAuth).  All three, or the well-known ones slip through.
    Rule("api-key",
         r"\b(?:sk|pk|rk|ghp|gho|ghu|github_pat|xoxb|xoxp|xoxa|xoxr|xoxs)"
         r"[-_][A-Za-z0-9_-]{8,}\b"),
    Rule("api-key",
         r"\b(?:AKIA|ASIA|AIza|ya29)\.?[A-Za-z0-9_.-]{8,}\b"),
    # The labelled form: redact the value, not the word "password".
    Rule("secret",
         r"\b(?:password|passcode|secret|api\s*key|access\s*key|client\s*secret"
         r"|private\s*key|authorization|bearer|token)\b\s*[:=]\s*(\S+)",
         group=1),
    Rule("card", r"\b(?:\d[ -]?){13,19}\b", _is_card),
    Rule("phone", r"\+?\d[\d\s().-]{7,}\d", _is_phone),
    Rule("token", r"\b[A-Za-z0-9_-]{24,}\b", _is_opaque_token),
)


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    rule: str


def sensitive_matches(text: str) -> List[Match]:
    """Spans of *text* worth redacting, merged and in order.

    Overlapping matches from different rules become one span — two boxes over
    the same token would just be a heavier blur in the same place — and the
    merged span keeps the name of the first rule that found it, so a
    suggestion can say why it is there.
    """
    found: List[Match] = []
    for rule in RULES:
        for match in re.finditer(rule.pattern, text, re.IGNORECASE):
            try:
                start, end = match.span(rule.group)
            except (IndexError, re.error):
                continue
            if start < 0 or end <= start:
                continue
            if rule.accepts and not rule.accepts(text[start:end]):
                continue
            found.append(Match(start, end, rule.name))
    return merge_matches(found)


def merge_matches(matches: Sequence[Match]) -> List[Match]:
    merged: List[Match] = []
    for match in sorted(matches, key=lambda m: (m.start, m.end)):
        if merged and match.start <= merged[-1].end:
            last = merged[-1]
            merged[-1] = Match(last.start, max(last.end, match.end), last.rule)
        else:
            merged.append(match)
    return merged


def sensitive_spans(text: str) -> List[Tuple[int, int]]:
    """Just the spans, for callers that do not care which rule fired."""
    return [(m.start, m.end) for m in sensitive_matches(text)]


def merge_spans(spans: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    return [(m.start, m.end) for m in
            merge_matches([Match(s, e, "") for s, e in spans])]


def matched_rules(text: str) -> List[str]:
    """Which rules fire on *text* — for tests and for explaining a suggestion."""
    names: List[str] = []
    for rule in RULES:
        for match in re.finditer(rule.pattern, text, re.IGNORECASE):
            value = match.group(rule.group)
            if value and (rule.accepts is None or rule.accepts(value)):
                if rule.name not in names:
                    names.append(rule.name)
                break
    return names


# -- words to regions --------------------------------------------------------

@dataclass
class Line:
    """A recognised line, with each word's span in the reconstructed text."""

    text: str = ""
    words: List[Word] = field(default_factory=list)
    spans: List[Tuple[int, int]] = field(default_factory=list)


def build_lines(words: Sequence[Word]) -> List[Line]:
    """Reassemble words into lines, remembering where each word landed.

    OCR gives words; the rules need running text, and the boxes have to be
    findable again afterwards — so the mapping is kept rather than recomputed.
    """
    grouped: Dict[Tuple[int, int, int], List[Word]] = {}
    for word in words:
        if word.text.strip():
            grouped.setdefault(word.line, []).append(word)

    lines: List[Line] = []
    for key in sorted(grouped):
        ordered = sorted(grouped[key], key=lambda w: w.x)
        line = Line()
        for word in ordered:
            if line.text:
                line.text += " "
            start = len(line.text)
            line.text += word.text
            line.words.append(word)
            line.spans.append((start, len(line.text)))
        lines.append(line)
    return lines


def _box_for_span(line: Line, span: Tuple[int, int]) -> Optional[Rect]:
    """The union of every word box the span touches, in pixels."""
    start, end = span
    hits = [word for word, (ws, we) in zip(line.words, line.spans)
            if ws < end and we > start]
    if not hits:
        return None
    left = min(w.x for w in hits)
    top = min(w.y for w in hits)
    right = max(w.x + w.w for w in hits)
    bottom = max(w.y + w.h for w in hits)
    return (left, top, right - left, bottom - top)


def normalized_padding(image_size: Tuple[float, float]) -> Tuple[float, float]:
    """A little slack around a box, so glyph edges do not peek out."""
    width = max(image_size[0], 1.0)
    height = max(image_size[1], 1.0)
    return (min(max(6 / width, 0.002), 0.012),
            min(max(4 / height, 0.002), 0.012))


def _padded(rect: Rect, padding: Tuple[float, float]) -> Rect:
    x = max(0.0, rect[0] - padding[0])
    y = max(0.0, rect[1] - padding[1])
    right = min(1.0, rect[0] + rect[2] + padding[0])
    bottom = min(1.0, rect[1] + rect[3] + padding[1])
    return (x, y, max(0.0, right - x), max(0.0, bottom - y))


def _area(rect: Rect) -> float:
    return max(rect[2], 0.0) * max(rect[3], 0.0)


def _overlap(a: Rect, b: Rect) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[0] + a[2], b[0] + b[2])
    bottom = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, right - left) * max(0.0, bottom - top)


def dedupe(regions: Sequence[Region], threshold: float = 0.85) -> List[Region]:
    """Drop regions that mostly cover one already kept.

    Different rules land on the same token often — an API key is also an opaque
    token — and stacking boxes on it only makes the blur heavier in one spot.
    """
    kept: List[Region] = []
    for region in regions:
        area = _area(region.rect)
        duplicate = False
        for existing in kept:
            shared = _overlap(region.rect, existing.rect)
            # Compared against the smaller of the two, so a small box sitting
            # inside a big one counts as covered.
            reference = min(area, _area(existing.rect))
            if reference > 0 and shared >= reference * threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(region)
    return kept


def regions_from_words(words: Sequence[Word],
                       image_size: Tuple[float, float]) -> List[Region]:
    """Every sensitive-looking region in a page of recognised words."""
    width, height = image_size
    if width <= 0 or height <= 0:
        return []
    padding = normalized_padding(image_size)

    found: List[Region] = []
    for line in build_lines(words):
        for match in sensitive_matches(line.text):
            box = _box_for_span(line, (match.start, match.end))
            if box is None:
                continue
            rect = _padded((box[0] / width, box[1] / height,
                            box[2] / width, box[3] / height), padding)
            if rect[2] < 0.001 or rect[3] < 0.001:
                continue
            found.append(Region(rect=rect,
                                text=line.text[match.start:match.end],
                                rule=match.rule))
    return dedupe(found)
