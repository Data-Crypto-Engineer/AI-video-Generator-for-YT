import logging
import sys
import re
from typing import Optional

# Redaction pattern for API tokens, secret keys, bearer tokens
SENSITIVE_PATTERNS = [
    re.compile(r'Bearer\s+[A-Za-z0-9_\-\.]{15,}', re.IGNORECASE),
    re.compile(r'key=[A-Za-z0-9_\-\.]{15,}', re.IGNORECASE),
    re.compile(r'cfut_[A-Za-z0-9_\-]{20,}', re.IGNORECASE),
    re.compile(r'AQ\.[A-Za-z0-9_\-]{20,}', re.IGNORECASE),
]

class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern in SENSITIVE_PATTERNS:
            msg = pattern.sub("[REDACTED_SECRET]", msg)
        return msg

def get_logger(name: str = "ai_video_pipeline") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

class PipelineLogger:
    """Specialized logger for recording multi-agent production progress."""
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.logger = get_logger(f"Project-{project_id[:8]}")
        self.events = []

    def log_stage(self, stage: str, message: str, level: str = "INFO"):
        clean_msg = f"[{stage}] {message}"
        if level == "ERROR":
            self.logger.error(clean_msg)
        elif level == "WARNING":
            self.logger.warning(clean_msg)
        else:
            self.logger.info(clean_msg)
        self.events.append({
            "stage": stage,
            "message": message,
            "level": level
        })

    def get_events(self):
        return list(self.events)
