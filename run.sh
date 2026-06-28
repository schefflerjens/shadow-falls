#!/bin/bash
# Get directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Stop any existing process running on port 8090 to ensure updates are loaded
EXISTING_PID=$(lsof -t -i :8090)
if [ ! -z "$EXISTING_PID" ]; then
  echo "Stopping existing Homer Web Viewer process on port 8090 (PID: $EXISTING_PID)..."
  kill $EXISTING_PID
  sleep 1
fi

# Start the Homer web viewer in the background on port 8090
echo "Starting Homer Web Viewer on port 8090..."
if [ -f "$DIR/.venv/bin/python" ]; then
  "$DIR/.venv/bin/python" "$DIR/mcp_server/web_viewer.py" 8090 > "$DIR/web_viewer.log" 2>&1 &
else
  python3 "$DIR/mcp_server/web_viewer.py" 8090 > "$DIR/web_viewer.log" 2>&1 &
fi

SERVER_PID=$!

# Wait a moment for server to bind
sleep 1

# Check if the process is still running
if kill -0 $SERVER_PID >/dev/null 2>&1; then
  echo "Homer Web Viewer started successfully in the background (PID: $SERVER_PID). Logs written to web_viewer.log."
else
  echo "Homer Web Viewer was already active or skipped port binding. Continuing..."
fi

# Start opencode with whatever arguments were passed
echo "Launching opencode..."
opencode "$@"
