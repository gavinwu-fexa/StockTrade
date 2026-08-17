@echo off
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo Starting Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  for /L %%I in (1,1,90) do (
    docker info >nul 2>&1 && goto docker_ready
    timeout /t 2 /nobreak >nul
  )
  echo Docker Desktop did not become ready. Open it manually, then run this file again.
  pause
  exit /b 1
)

:docker_ready
echo Building and starting StockTrade...
docker compose up --build -d
if errorlevel 1 (
  echo StockTrade failed to start. Run Logs-StockTrade.cmd for details.
  pause
  exit /b 1
)

docker compose ps
echo.
echo StockTrade: http://localhost:5173
echo Backend:    http://localhost:8000
start "" "http://localhost:5173"
pause
