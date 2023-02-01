#!/bin/bash

# Kill child processes when script exits
trap 'trap - SIGTERM && kill -- -$$' SIGTERM SIGINT

# Start server processes
python3 server.py &
python3 websocket_server.py &
hypercorn http_server:app --bind 0.0.0.0:8001 &

# Wait until the first process ends
wait -n

# Exit with the same exit code
exit $?
