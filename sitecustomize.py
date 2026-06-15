import os


# Keep pytest reproducible inside this repo by ignoring globally installed plugins
# that may inject conflicting command-line options.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
