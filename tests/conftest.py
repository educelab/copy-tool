"""Shared pytest configuration for the acquisition-workflow test suite.

Forces Qt into headless ('offscreen') mode so GUI tests run without a display
(e.g. in CI). This must happen before PySide6 is imported, so it lives here at
collection time. No Qt import occurs in this module, so pure (non-Qt) tests can
still be collected when PySide6 is not installed.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
