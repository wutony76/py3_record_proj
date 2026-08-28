"""共用的 logger 設定，各模組都用同一個 "auto-flow" logger。"""

import logging

LOGGER_NAME = "auto-flow"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(LOGGER_NAME)


log = logging.getLogger(LOGGER_NAME)
