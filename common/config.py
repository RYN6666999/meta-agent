from __future__ import annotations

from pathlib import Path

BASE_DIR = Path("/Users/ryan/meta-agent")
MEMORY_DIR = BASE_DIR / "memory"
ERROR_LOG_DIR = BASE_DIR / "error-log"
TRUTH_SOURCE_DIR = BASE_DIR / "truth-source"
USERS_DIR = MEMORY_DIR / "users"
PERSONA_REPORTS_DIR = MEMORY_DIR / "persona-reports"

STATUS_FILE = MEMORY_DIR / "system-status.json"
ENV_FILE = BASE_DIR / ".env"
LAW_JSON = BASE_DIR / "law.json"

LIGHTRAG_API = "http://localhost:9621"
N8N_API = "http://localhost:5678"

HTTP_TIMEOUT_SHORT = 5
HTTP_TIMEOUT_DEFAULT = 15
HTTP_TIMEOUT_LONG = 60
