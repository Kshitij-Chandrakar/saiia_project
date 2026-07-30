import re
from dataclasses import dataclass


INTERNAL_MARKER_KEYS = frozenset({"category", "type", "mode", "intent", "answer_type"})
_KEY_PATTERN = "|".join(sorted(INTERNAL_MARKER_KEYS))
_COMPLETE_MARKER_RE = re.compile(
    rf"\[\[\s*(?P<key>{_KEY_PATTERN})\s*:\s*(?P<value>[A-Za-z0-9_. -]{{0,80}})\s*\]\]",
    flags=re.IGNORECASE,
)


def strip_internal_control_markers(text: str) -> str:
    return _COMPLETE_MARKER_RE.sub("", str(text or "")).strip()


@dataclass
class InternalMarkerStreamSanitizerStats:
    marker_removed_count: int = 0
    stream_prefix_buffered: bool = False
    flush_used: bool = False


class InternalMarkerStreamSanitizer:
    def __init__(self, *, max_pending: int = 128) -> None:
        self.max_pending = max_pending
        self.pending = ""
        self.at_start = True
        self.stats = InternalMarkerStreamSanitizerStats()

    def reset(self) -> None:
        self.pending = ""
        self.at_start = True
        self.stats = InternalMarkerStreamSanitizerStats()

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.pending += str(chunk)
        return self._drain(final=False)

    def flush(self) -> str:
        self.stats.flush_used = bool(self.pending)
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        output: list[str] = []

        while self.pending:
            marker_start = self.pending.find("[[")
            if marker_start < 0:
                emit_len = len(self.pending) if final else max(0, len(self.pending) - 1)
                if self.at_start:
                    non_space_index = self._first_non_space(self.pending[:emit_len])
                    if non_space_index < 0:
                        if len(self.pending) > self.max_pending or final:
                            output.append(self.pending[:emit_len])
                            self.pending = self.pending[emit_len:]
                            self.at_start = False
                        break
                if emit_len <= 0:
                    break
                output.append(self.pending[:emit_len])
                self.pending = self.pending[emit_len:]
                self.at_start = False
                continue

            prefix = self.pending[:marker_start]
            if marker_start > 0 and not (self.at_start and prefix.isspace()):
                output.append(prefix)
                self.pending = self.pending[marker_start:]
                self.at_start = False
                continue

            marker_end = self.pending.find("]]", marker_start + 2)
            if marker_end < 0:
                candidate = self.pending[marker_start:]
                if not final and len(candidate) <= self.max_pending and self._could_be_control_marker(candidate):
                    self.stats.stream_prefix_buffered = True
                    break
                if final and self.at_start and (not prefix or prefix.isspace()) and self._could_be_control_marker(candidate):
                    self.pending = ""
                    self.stats.marker_removed_count += 1
                    break
                output.append(self.pending)
                self.pending = ""
                self.at_start = False
                break

            candidate = self.pending[marker_start : marker_end + 2]
            if _COMPLETE_MARKER_RE.fullmatch(candidate):
                self.stats.marker_removed_count += 1
                self.pending = self.pending[marker_end + 2 :]
                if self.at_start:
                    self.pending = self.pending.lstrip()
                continue

            emit_len = marker_end + 2
            output.append(self.pending[:emit_len])
            self.pending = self.pending[emit_len:]
            self.at_start = False

        return "".join(output)

    def _could_be_control_marker(self, candidate: str) -> bool:
        value = candidate.lower()
        if not value.startswith("[["):
            return False
        body = value[2:].lstrip()
        if not body:
            return True
        key = body.split(":", 1)[0].strip()
        if ":" not in body:
            return any(known.startswith(key) for known in INTERNAL_MARKER_KEYS)
        return key in INTERNAL_MARKER_KEYS

    def _first_non_space(self, value: str) -> int:
        for index, char in enumerate(value):
            if not char.isspace():
                return index
        return -1
