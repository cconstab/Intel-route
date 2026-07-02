#!/usr/bin/env python3
"""
Bug: AtClient.notify()'s `session_id` default is evaluated ONCE at import.

    def notify(self, at_key, value, operation=..., session_id=str(uuid.uuid4())):

`str(uuid.uuid4())` runs when the function is defined, not per call, so every
notify() that doesn't pass an explicit session_id reuses the SAME id for the whole
process lifetime. The atServer dedups by notification id, so all-but-the-first of
those notifications can be silently dropped.

This repro needs no network — it inspects the default binding.
"""
import inspect
from at_client import AtClient

default = inspect.signature(AtClient.notify).parameters["session_id"].default
print(f"session_id default binding: {default!r}")

is_fixed_uuid = isinstance(default, str) and len(default) == 36 and default.count("-") == 4
print("RESULT:", "BUG — fixed UUID baked in at import (shared across all calls)"
      if is_fixed_uuid else "OK — default is None/regenerated per call")
