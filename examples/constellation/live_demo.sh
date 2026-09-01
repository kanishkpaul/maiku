#!/usr/bin/env zsh
# Run the complete live multi-intelligence maiku demonstration from any directory.
set -euo pipefail

script_dir=${0:A:h}
cd "$script_dir/../.."

echo "MAIKU LIVE DEMO"
echo "Using local Gemma at 127.0.0.1:8081 as narrator and simulated human reviewer."
echo "The default pace is recording-friendly; add --fast to remove deliberate pauses."
echo

exec uv run python -m examples.constellation.run "$@"
