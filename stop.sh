#!/usr/bin/env bash
# DRQR — Stop
pkill -f "python.*server.py" || pkill -f "server.py" || echo "No running DRQR process found"
echo "Stopped"
