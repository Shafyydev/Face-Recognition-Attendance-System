import os
import tempfile

# Ensure tests never hit production DB or send real SMS.
# This module is imported by pytest; for unittest runs, individual tests
# should also respect these env vars when set externally.
if "ATTENDANCE_DB_PATH" not in os.environ:
    _tmp = os.path.join(tempfile.gettempdir(), "attendance_system_test_isolated.db")
    os.environ["ATTENDANCE_DB_PATH"] = _tmp

# Force mock SMS provider and disable real SMS side effects in tests.
os.environ.setdefault("SMS_PROVIDER", "mock")
os.environ.setdefault("SMS_ENABLED", "false")
