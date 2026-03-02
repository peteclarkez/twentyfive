#!/bin/bash
# Auto-format Python files after Claude edits or writes them.
# Receives tool input as JSON on stdin.
file_path=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)

if [[ "$file_path" == *.py ]]; then
    ruff format "$file_path" 2>/dev/null
fi
