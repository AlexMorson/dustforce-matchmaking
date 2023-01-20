#!/bin/bash

# Kill child processes when script exits
trap 'trap - SIGTERM && kill -- -$$' SIGTERM SIGINT

# Start server processes
python3 websocket_server.py &
python3 server.py &

# Wait until the first process ends
wait -n

# Exit with the same exit code
exit $?
