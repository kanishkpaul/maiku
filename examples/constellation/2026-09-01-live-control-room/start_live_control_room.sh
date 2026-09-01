#!/usr/bin/env zsh
# Starts the real Maiku control plane and the Vite UI together for the local demo.
set -euo pipefail

script_dir="${0:A:h}"
repo_root="${script_dir:h:h:h}"
cd "$repo_root"

if lsof -tiTCP:8787 -sTCP:LISTEN >/dev/null 2>&1; then
  print -u2 "Port 8787 is already in use. Stop the existing Maiku control-room process first."
  exit 1
fi
if lsof -tiTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  print -u2 "Port 5173 is already in use. Stop the existing Vite process first."
  exit 1
fi

pace="${MAIKU_DEMO_PACE:-11}"
mnist_test="$repo_root/examples/real/data/MNIST/raw/t10k-images-idx3-ubyte"
if [[ ! -f "$mnist_test" ]]; then
  print "Preparing the one-time MNIST test fixture used by DigitCNN…"
  uv run --extra torch --group dev "$script_dir/bootstrap_live_control_room.py"
fi

uv run --extra web --extra net --extra torch "$script_dir/run_live_control_room.py" --pace "$pace" &
control_room_pid=$!

cleanup() {
  kill "$control_room_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in {1..50}; do
  if curl --silent --fail http://127.0.0.1:8787/api/status >/dev/null; then
    break
  fi
  sleep 0.2
done

if ! curl --silent --fail http://127.0.0.1:8787/api/status >/dev/null; then
  print -u2 "The Maiku control room did not start on http://127.0.0.1:8787."
  exit 1
fi

print "\nMaiku live demo is ready at http://127.0.0.1:5173\n"
npm run dev -- --host 127.0.0.1 --strictPort
