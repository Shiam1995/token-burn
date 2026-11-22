#!/usr/bin/env sh
# tokens.xlsx -> token-burn.png
cd "$(dirname "$0")"
exec python3 tools/image.py "$@"
