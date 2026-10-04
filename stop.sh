#!/usr/bin/env bash
# DR & CO. — Stop
pkill -f "python.*server.py" || pkill -f "server.py" || echo "No running DR & CO. process found"
echo "Stopped"
