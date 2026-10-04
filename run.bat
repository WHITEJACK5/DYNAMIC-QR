@echo off
echo === DR ^& CO. — Grid White / Black / Neon Green ===
echo Installing deps...
pip install -r requirements.txt
echo Starting server on http://localhost:5000
python server.py
pause
