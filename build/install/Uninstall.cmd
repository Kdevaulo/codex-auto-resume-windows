@echo off
setlocal
"%SystemRoot%\System32\chcp.com" 65001 >nul
title Codex Auto Resume - uninstall
rem -Silent (winget, a script): nothing waits for a key. It is passed on to install.ps1 with the rest.
set "SILENT="
for %%A in (%*) do if /i "%%~A"=="-Silent" set "SILENT=1"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install.ps1" -Uninstall %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not defined SILENT pause
exit /b %EXIT_CODE%
