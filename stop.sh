#!/usr/bin/env bash
# NARE & CO. — Stop
pkill -f "python.*server.py" || pkill -f "server.py" || echo "No running NARE & CO. process found"
echo "Stopped"
