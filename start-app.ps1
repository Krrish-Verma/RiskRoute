Set-Location "$PSScriptRoot"

$backend = Start-Process -FilePath "$PSScriptRoot/.venv/Scripts/python.exe" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$PSScriptRoot/backend" -PassThru
Start-Sleep -Seconds 4

$frontend = Start-Process -FilePath "npm" -ArgumentList "run dev -- --hostname 127.0.0.1 --port 3000" -WorkingDirectory "$PSScriptRoot/frontend" -PassThru

Write-Host "Backend PID: $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
Write-Host "Open http://127.0.0.1:3000"
