"""Shell command tokenizer — 移植自 packages/opencode/src/tool/shell-tokenize.ts

Tokenizes shell-style scripts into commands with proper handling of
heredocs, quotes, comments, and POSIX line continuations.

Uses ``shlex`` for parsing after pre-processing heredocs and comments.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Argv:
    """Parsed command: line number and token list."""
    line: int
    tokens: list[str] = field(default_factory=list)


@dataclass
class ParseError:
    """Shell parse error."""
    kind: str  # "unclosed-quote" | "unsupported-operator" | "unclosed-heredoc" | "internal"
    line: int
    detail: str = ""


# Heredoc marker: starts with letter/underscore, then word chars
HEREDOC_MARKER_HEAD = re.compile(r"[A-Za-z_]")
HEREDOC_MARKER_TAIL = re.compile(r"[A-Za-z0-9_]")


def _parse_heredoc_marker(script: str, start: int) -> dict | None:
    """Parse a heredoc opener at `start` (where script[start] and start+1 are `<<`).

    Returns {"marker": str, "end": int} or None.
    """
    j = start + 2
    if j < len(script) and script[j] == "-":
        j += 1
    while j < len(script) and script[j] in (" ", "\t"):
        j += 1

    quote = None
    if j < len(script) and script[j] in ("'", '"'):
        quote = script[j]
        j += 1

    marker_start = j
    if not (j < len(script) and HEREDOC_MARKER_HEAD.match(script[j])):
        return None
    while j < len(script) and HEREDOC_MARKER_TAIL.match(script[j]):
        j += 1

    marker = script[marker_start:j]
    if quote:
        if j >= len(script) or script[j] != quote:
            return None
        j += 1

    return {"marker": marker, "end": j}


def _extract_heredocs(script: str) -> dict:
    """Extract heredoc bodies from a script, replacing with placeholders.

    Returns {"ok": True, "stripped": str, "bodies": list[str]} on success,
    or {"ok": False, "error": ParseError} on failure.
    """
    bodies: list[str] = []
    out_parts: list[str] = []
    quote = None
    i = 0
    line = 1

    while i < len(script):
        ch = script[i]

        # Inside a quoted string: pass through verbatim
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(script):
                out_parts.append(ch + script[i + 1])
                if script[i + 1] == "\n":
                    line += 1
                i += 2
                continue
            if ch == quote:
                quote = None
                out_parts.append(ch)
                i += 1
                continue
            if ch == "\n":
                line += 1
            out_parts.append(ch)
            i += 1
            continue

        # At top level
        if ch in ('"', "'"):
            quote = ch
            out_parts.append(ch)
            i += 1
            continue

        # Check for `<<` at top level (but not `<<<` herestring)
        if ch == "<" and i + 1 < len(script) and script[i + 1] == "<":
            # `<<<` herestring
            if i + 2 < len(script) and script[i + 2] == "<":
                out_parts.append("<<< ")
                i += 3
                while i < len(script) and script[i] != "\n":
                    i += 1
                continue

            opener = _parse_heredoc_marker(script, i)
            if opener:
                marker = opener["marker"]
                k = opener["end"]
                while k < len(script) and script[k] in (" ", "\t"):
                    k += 1

                if k < len(script) and script[k] != "\n":
                    return {
                        "ok": False,
                        "error": ParseError(
                            kind="unsupported-operator",
                            line=line,
                            detail="tokens after <<MARKER on the same line are not supported",
                        ),
                    }

                # Valid heredoc: emit placeholder
                body_index = len(bodies)
                open_line = line
                out_parts.append(f"\x00HD{body_index}\x00\n")
                i = k + 1
                line += 1

                # Collect body lines
                body_lines: list[str] = []
                closed = False
                while i < len(script):
                    line_end = i
                    while line_end < len(script) and script[line_end] != "\n":
                        line_end += 1
                    body_line = script[i:line_end]
                    out_parts.append("\n")
                    if body_line.strip() == marker:
                        i = line_end + (1 if line_end < len(script) else 0)
                        line += 1
                        closed = True
                        break
                    body_lines.append(body_line)
                    i = line_end + (1 if line_end < len(script) else 0)
                    line += 1

                if not closed:
                    return {
                        "ok": False,
                        "error": ParseError(
                            kind="unclosed-heredoc",
                            line=open_line,
                            detail=f"unclosed heredoc <<{marker}",
                        ),
                    }

                bodies.append("\n".join(body_lines))
                continue

            # `<<` without a valid marker — pass through
            out_parts.append(ch)
            i += 1
            continue

        out_parts.append(ch)
        if ch == "\n":
            line += 1
        i += 1

    return {"ok": True, "stripped": "".join(out_parts), "bodies": bodies}


def _preprocess_comments(input_text: str) -> str:
    """Remove POSIX-style comments, escaping mid-token #."""
    out: list[str] = []
    i = 0
    quote = None
    prev_was_boundary = True

    while i < len(input_text):
        ch = input_text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(input_text):
                out.append(input_text[i + 1])
                i += 2
                prev_was_boundary = False
                continue
            if ch == quote:
                quote = None
            i += 1
            prev_was_boundary = False
            continue

        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            prev_was_boundary = False
            continue

        if ch == "\\":
            if i + 1 < len(input_text) and input_text[i + 1] == "#":
                out.append("\\#")
                i += 2
                prev_was_boundary = False
                continue
            out.append(ch)
            i += 1
            prev_was_boundary = False
            continue

        if ch == "#":
            if prev_was_boundary:
                # word-boundary # → real comment
                while i < len(input_text) and input_text[i] != "\n":
                    i += 1
                continue
            # mid-token # → escape
            out.append("\\#")
            i += 1
            prev_was_boundary = False
            continue

        out.append(ch)
        prev_was_boundary = ch == "\n" or ch.isspace()
        i += 1

    return "".join(out)


# Heredoc placeholder regex
HD_RE = re.compile(r"^\x00HD(\d+)\x00$")


def _scan_unclosed_quote(segment: str) -> str | None:
    """Scan for unclosed quotes. Returns the quote char or None."""
    quote = None
    i = 0
    while i < len(segment):
        ch = segment[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(segment):
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
        i += 1
    return quote


def _split_top_level_lines(script: str) -> list[dict]:
    """Split script into segments separated by top-level line breaks.

    Returns list of {"line": int, "text": str}.
    """
    segments: list[dict] = []
    buf: list[str] = []
    seg_start = 1
    line = 1
    quote = None
    i = 0

    while i < len(script):
        ch = script[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(script):
                buf.append(ch + script[i + 1])
                if script[i + 1] == "\n":
                    line += 1
                i += 2
                continue
            if ch == quote:
                quote = None
                buf.append(ch)
                i += 1
                continue
            if ch == "\n":
                line += 1
            buf.append(ch)
            i += 1
            continue

        if ch in ('"', "'"):
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == "\\" and i + 1 < len(script) and script[i + 1] == "\n":
            # POSIX line continuation: \<LF> disappears
            line += 1
            i += 2
            continue

        if ch == "\n":
            if buf:
                segments.append({"line": seg_start, "text": "".join(buf)})
                buf = []
            line += 1
            seg_start = line
            i += 1
            continue

        buf.append(ch)
        i += 1

    if buf:
        segments.append({"line": seg_start, "text": "".join(buf)})

    return segments


def tokenize(script: str) -> list[Argv] | ParseError:
    """Tokenize a shell script into a list of Argv entries.

    Returns list[Argv] on success, ParseError on failure.
    """
    if not script.strip():
        return []

    heredoc_result = _extract_heredocs(script)
    if not heredoc_result.get("ok"):
        return heredoc_result["error"]

    stripped = heredoc_result["stripped"]
    bodies = heredoc_result["bodies"]

    segments = _split_top_level_lines(_preprocess_comments(stripped))
    segments = [seg for seg in segments if seg["text"].strip()]

    out: list[Argv] = []
    for seg in segments:
        unclosed = _scan_unclosed_quote(seg["text"])
        if unclosed:
            return ParseError(
                kind="unclosed-quote",
                line=seg["line"],
                detail=f"unclosed {unclosed}-quoted string",
            )

        # Use shlex for lexing
        try:
            lexer = shlex.shlex(seg["text"], posix=True)
            lexer.whitespace_split = True
            tokens: list[str] = []
            for tok in lexer:
                # Check heredoc placeholder
                m = HD_RE.match(tok)
                if m:
                    idx = int(m.group(1))
                    if idx < len(bodies):
                        tokens.append(bodies[idx])
                    continue
                tokens.append(tok)
        except ValueError as e:
            return ParseError(
                kind="internal",
                line=seg["line"],
                detail=str(e),
            )

        if tokens:
            out.append(Argv(line=seg["line"], tokens=tokens))

    return out


def tokenize_safe(script: str) -> list[Argv]:
    """Safe version of tokenize that returns [] on any error."""
    result = tokenize(script)
    if isinstance(result, ParseError):
        return []
    return result
