"""The TS event mirror (packages/shared) must match the Python RunEvent model."""

from __future__ import annotations

import re
from pathlib import Path

from app.schemas.events import RunEvent

_TS = Path(__file__).resolve().parents[3] / "packages" / "shared" / "src" / "events.ts"


def test_run_event_fields_match_ts_mirror():
    text = _TS.read_text("utf-8")
    block = re.search(r"RUN_EVENT_FIELDS\s*=\s*\[(.*?)\]", text, re.S)
    assert block, "RUN_EVENT_FIELDS not found in events.ts"
    ts_fields = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    py_fields = set(RunEvent.model_fields.keys())
    assert ts_fields == py_fields, f"drift: py-only={py_fields - ts_fields} ts-only={ts_fields - py_fields}"


def test_event_types_align():
    text = _TS.read_text("utf-8")
    ts_types = set(re.findall(r'"([a-z_.]+)"', text.split("RunEventType")[1].split(";")[0]))
    from typing import get_args

    py_types = set(get_args(RunEvent.model_fields["type"].annotation))
    assert py_types <= ts_types
