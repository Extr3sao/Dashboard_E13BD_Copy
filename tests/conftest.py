"""Regression tests exercise handlers without a deployment identity provider.

Production defaults to mandatory browser authentication.  Unit tests that
exercise legacy handlers opt out explicitly; security integration tests set the
flag back to true for their request scope.
"""
import os

os.environ.setdefault("E13DB_AUTH_REQUIRED", "false")
