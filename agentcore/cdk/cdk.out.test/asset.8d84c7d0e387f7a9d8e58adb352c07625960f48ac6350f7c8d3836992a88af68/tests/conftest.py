"""pytest conftest — applied to the entire barttagent test suite.

Sets ``KNOWLEDGE_BASE_ID`` in the environment **before** any test module is
imported so that ``config.py`` (and ``main.py`` at module level) see a
non-empty value and do not trigger the strict-mode ``SystemExit`` guard.

Individual tests that exercise the "no KB ID" code path patch
``main.KNOWLEDGE_BASE_ID`` directly inside their ``with patch(...)`` block;
that works because Python attribute patching replaces the already-imported
module's namespace binding without re-running the module-level startup check.
"""
import os

# main.py raises SystemExit(1) when KNOWLEDGE_BASE_ID is unset and
# GROUNDING_STRICT_MODE defaults to true.  Supply a sentinel value here so
# the module can be imported; real retrieval is always mocked in tests.
os.environ.setdefault("KNOWLEDGE_BASE_ID", "test-kb")
