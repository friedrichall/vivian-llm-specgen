"""Utilities for capturing job stdout/stderr into a log file."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from threading import Lock
from typing import Iterator, TextIO
import sys


class TeeWriter:
    """Write text to a file and optionally mirror it to the process console."""

    def __init__(self, log_file: TextIO, mirror_stream: TextIO | None = None) -> None:
        self._log_file = log_file
        self._mirror_stream = mirror_stream
        self._lock = Lock()

    def write(self, text: str) -> int:
        if not text:
            return 0
        with self._lock:
            self._log_file.write(text)
            self._log_file.flush()
            if self._mirror_stream is not None:
                self._mirror_stream.write(text)
                self._mirror_stream.flush()
        return len(text)

    def flush(self) -> None:
        with self._lock:
            self._log_file.flush()
            if self._mirror_stream is not None:
                self._mirror_stream.flush()

    def writable(self) -> bool:
        return True


@contextmanager
def capture_job_output(log_path: Path, mirror_console: bool = True) -> Iterator[None]:
    """Redirect stdout/stderr into a job log."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    mirror_stream = sys.__stdout__ if mirror_console else None

    with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
        writer = TeeWriter(log_file=log_file, mirror_stream=mirror_stream)
        with redirect_stdout(writer), redirect_stderr(writer):
            yield
        writer.flush()
