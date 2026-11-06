@echo off
setlocal
if not defined PUBLIC set "PUBLIC=C:\Users\Public"
set "TEMP=%PUBLIC%\OpenAgentCU-temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
  echo [OpenAgentCU] Cannot create temp dir: %TEMP%
  echo Please use the portable zip instead.
  pause
  exit /b 1
)
"%~dp0OpenAgentCU-0.1.0-Setup.exe" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [OpenAgentCU] Setup exit code: %RC%
  if /I not "%1"=="/VERYSILENT" pause
)
exit /b %RC%
