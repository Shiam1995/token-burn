#!/usr/bin/env sh
cd "$(dirname "$0")"
(sleep 1; xdg-open http://localhost:8787 2>/dev/null || open http://localhost:8787 2>/dev/null) &
exec python3 tokenburn.py
