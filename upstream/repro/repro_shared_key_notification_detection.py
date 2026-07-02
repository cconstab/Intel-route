#!/usr/bin/env python3
"""
Bug: AtMonitorConnection misclassifies shared-key notifications.

In connections/atmonitorconnection.py the check is:

    if key.startswith(str(self.atsign.to_string) + ":shared_key@"):   # BUG: no ()

`self.atsign.to_string` is a bound METHOD; `str(...)` of it is like
"<bound method AtSign.to_string of ...>", which never prefixes a real key. So the
SHARED_KEY_NOTIFICATION branch is never taken and shared-key notifications are
mis-typed as ordinary UPDATE_NOTIFICATIONs. (Line 124 in the same file correctly
uses `to_string()` — so this is an isolated missing-parentheses bug.)

This repro needs no network — it evaluates both predicates directly.
"""
from at_client.common import AtSign

atsign = AtSign("@alice")
key = atsign.to_string() + ":shared_key@bob"   # a real shared-key notification key
print(f"notification key: {key}")

buggy = key.startswith(str(atsign.to_string) + ":shared_key@")   # current SDK
fixed = key.startswith(atsign.to_string() + ":shared_key@")      # with ()

print(f"current SDK detects shared-key notification: {buggy}   (should be True)")
print(f"with to_string() called:                     {fixed}")
print("RESULT:", "BUG — shared-key notifications never detected" if not buggy else "OK")
