from __future__ import annotations

import os
from pathlib import Path

_env_base = os.environ.get("META_AGENT_BASE_DIR", "").strip()
BASE_DIR = Path(_env_base) if _env_base else Path(__file__).resolve().parents[1]
MEMORY_DIR = BASE_DIR / "memory"
ERROR_LOG_DIR = BASE_DIR / "error-log"
TRUTH_SOURCE_DIR = BASE_DIR / "truth-source"
USERS_DIR = MEMORY_DIR / "users"
PERSONA_REPORTS_DIR = MEMORY_DIR / "persona-reports"

STATUS_FILE = MEMORY_DIR / "system-status.json"
ENV_FILE = BASE_DIR / ".env"
LAW_JSON = BASE_DIR / "law.json"
STRUCTURED_MEMORY_DB = MEMORY_DIR / "structured_memory.db"

LIGHTRAG_API = os.environ.get("LIGHTRAG_API", "http://127.0.0.1:9631")
N8N_API = "http://localhost:5678"

HTTP_TIMEOUT_SHORT = 5
HTTP_TIMEOUT_DEFAULT = 15
HTTP_TIMEOUT_LONG = 60
