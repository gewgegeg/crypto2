from __future__ import annotations

import logging
from typing import Optional


class Notifier:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("arbitrage.notifier")

    def notify(self, message: str) -> None:
        self.logger.info(message)
        print(message)