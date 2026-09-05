#!/usr/bin/env bash
# NARE & CO. — Start (Unix/macOS)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -f ".env" ]; then
  echo "Creating .env with random SECRET_KEY..."
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > .env <<EOF
SECRET_KEY=$SECRET
BASE_URL=http://localhost:5000
HOST=127.0.0.1
PORT=5000
FLASK_DEBUG=false
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
EOF
  echo ".env created"
fi
if [ ! -d "venv" ]; then
  python3 -m venv venv || true
fi
# Use venv if exists
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi
pip install -r requirements.txt
echo "=== NARE & CO. starting on http://localhost:5000 ==="
python app.py
