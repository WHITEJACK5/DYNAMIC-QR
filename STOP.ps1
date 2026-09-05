Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*Python311*" } | Stop-Process -Force
Write-Host "NARE & CO. server stopped" -ForegroundColor Yellow
