#!/usr/bin/env python3
"""DB migration: 加入人工標注欄位"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "novel_analyzer.db"

migrations = [
    "ALTER TABLE scene_framework_cards ADD COLUMN human_focal_character TEXT",
    "ALTER TABLE scene_framework_cards ADD COLUMN human_match_level TEXT",
    "ALTER TABLE scene_framework_cards ADD COLUMN human_shift_type TEXT",
    "ALTER TABLE scene_framework_cards ADD COLUMN human_shift_intensity INTEGER",
    "ALTER TABLE scene_framework_cards ADD COLUMN ai_original_values TEXT",
    "ALTER TABLE scene_framework_cards ADD COLUMN is_golden_example INTEGER DEFAULT 0",
    "ALTER TABLE scene_framework_cards ADD COLUMN human_annotated_at TEXT",
]

conn = sqlite3.connect(DB)
for sql in migrations:
    try:
        conn.execute(sql)
        col = sql.split("ADD COLUMN")[1].strip().split()[0]
        print(f"  OK  {col}")
    except Exception as e:
        print(f"  --  {str(e)[:60]}")
conn.commit()
conn.close()
print("migration done")
