"""날짜 + 크기 회전 · 보관일수 파일 핸들러 (logging-overhaul ADR-004).

- 매일 자정에 ``app.log`` → ``app.log.2026-10-19`` (표준 ``TimedRotatingFileHandler``).
- 하루 안에서 ``max_bytes`` 를 넘으면 ``app.log.2026-10-19.1``·``.2``… 로 나눈다.
- 회전할 때마다 ``retention_days`` 보다 오래된 날짜 파일·분할 파일을 지운다(0 = 지우지 않음).

한 파일을 한 프로세스만 쓴다는 전제다 — 여러 프로세스가 같은 파일을 회전하면 안전하지 않다(README).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class DailySizeRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename: str,
        max_bytes: int = 0,
        retention_days: int = 0,
        utc: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__(
            filename, when="midnight", backupCount=0, encoding=encoding, utc=utc, delay=True
        )
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        name = re.escape(Path(self.baseFilename).name)
        self._rotated = re.compile(rf"^{name}\.(\d{{4}}-\d{{2}}-\d{{2}})(?:\.\d+)?$")

    def _today(self) -> str:
        now = time.time()
        return time.strftime(self.suffix, time.gmtime(now) if self.utc else time.localtime(now))

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if super().shouldRollover(record):
            return True
        if self.max_bytes <= 0:
            return False
        if self.stream is None:
            self.stream = self._open()
        pos = self.stream.tell()
        return bool(pos) and pos + len(self.format(record)) + 1 > self.max_bytes

    def doRollover(self) -> None:
        if time.time() >= self.rolloverAt:
            super().doRollover()
        else:
            if self.stream:
                self.stream.close()
                self.stream = None
            prefix = f"{self.baseFilename}.{self._today()}."
            n = 1
            while os.path.exists(f"{prefix}{n}"):
                n += 1
            self.rotate(self.baseFilename, f"{prefix}{n}")
        self._purge()

    def _purge(self) -> None:
        if self.retention_days <= 0:
            return
        oldest = (
            date.fromisoformat(self._today()) - timedelta(days=self.retention_days)
        ).isoformat()
        folder = Path(self.baseFilename).parent
        for path in folder.iterdir():
            m = self._rotated.match(path.name)
            if m and m[1] < oldest:
                path.unlink(missing_ok=True)
