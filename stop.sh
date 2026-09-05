#!/usr/bin/env bash
# NARE & CO. — Stop
pkill -f "python.*app.py" || pkill -f "app.py" || echo "No running NARE & CO. process found"
echo "Stopped"
