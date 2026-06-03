@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

if not exist "%BACKEND_DIR%\venv" (
  echo Backend virtualenv not found at: %BACKEND_DIR%\venv
  echo Create it first or install the backend dependencies.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Frontend dependencies not found. Running npm install...
  pushd "%FRONTEND_DIR%"
  call npm install
  popd
)

echo Starting Conversys Fut...
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000
for /f "tokens=14" %%i in ('ipconfig ^| findstr /i "IPv4"') do (
  echo Network:  http://%%i:3000
  goto printed_network
)
:printed_network
echo.

if exist "%BACKEND_DIR%\venv\Scripts\activate.bat" (
  start "Conversys Backend" cmd /k "cd /d "%BACKEND_DIR%" && call "venv\Scripts\activate.bat" && uvicorn main:app --reload --host 0.0.0.0 --port 8000"
) else (
  start "Conversys Backend" cmd /k "cd /d "%BACKEND_DIR%" && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
)

start "Conversys Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

endlocal
