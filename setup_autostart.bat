@echo off
rem Install / remove Keyboard-Agent autostart (per-user Windows Startup folder).
rem
rem   setup_autostart.bat            install silent autostart on logon
rem   setup_autostart.bat --remove   remove the autostart entry
rem
rem Uses the per-user Startup folder (%APPDATA%\...\Startup): no admin needed and
rem fully transparent - open shell:startup to see the entry, delete it to disable.

cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ENTRY=%STARTUP%\Keyboard-Agent.bat"

if /i "%~1"=="--remove" (
    if exist "%ENTRY%" (
        del "%ENTRY%"
        echo Removed autostart entry: %ENTRY%
    ) else (
        echo No autostart entry found.
    )
    goto :eof
)

> "%ENTRY%" echo @echo off
>> "%ENTRY%" echo rem Keyboard-Agent autostart ^(created by setup_autostart.bat^)
>> "%ENTRY%" echo start "" /min "%CD%\run_agent.bat"

echo Installed autostart entry: %ENTRY%
echo Keyboard-Agent will start silently on next logon.
echo To remove: run this again with --remove, or delete the entry from shell:startup.
