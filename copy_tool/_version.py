"""Single source of truth for the CopyTool version.

CI rewrites this file before building so release binaries carry the commit
they were built from. Keep it to plain string literals: setuptools reads
``__version__`` by parsing the AST, without importing the package.
"""

__version__ = "1.3.0"
