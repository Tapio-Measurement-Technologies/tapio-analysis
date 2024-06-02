@echo off

REM Function to check if a command exists
:TestCommand
SETLOCAL
SET "command=%~1"
SET "commandPath="
FOR /F "tokens=*" %%I IN ('WHERE %command% 2^>NUL') DO SET "commandPath=%%I"
IF "%commandPath%"=="" (
    ENDLOCAL & EXIT /B 1
) ELSE (
    ENDLOCAL & EXIT /B 0
)

REM Check if Python is installed
CALL :TestCommand "python"
IF ERRORLEVEL 1 (
    ECHO Python is not installed or not found in PATH. Please install Python to proceed.
    EXIT /B 1
)

REM Check if pip is installed
CALL :TestCommand "pip"
IF ERRORLEVEL 1 (
    ECHO pip is not installed or not found in PATH. Please install pip to proceed.
    EXIT /B 1
)

REM Create a virtual environment in the .venv folder
IF NOT EXIST ".venv" (
    python -m venv .venv
)

REM Check if the virtual environment was created successfully
IF NOT EXIST ".venv\Scripts\activate.bat" (
    ECHO Failed to create virtual environment. Please check your Python installation.
    EXIT /B 1
)

REM Install the packages from requirements.txt
CALL .\.venv\Scripts\activate.bat
pip install -r requirements.txt

REM Define the paths
SET "projectPath=%cd%"
SET "venvActivatePath=%projectPath%\.venv\Scripts\activate.bat"
SET "scriptPath=%projectPath%\src\main.py"
SET "batchFilePath=%projectPath%\run_tapio_analysis.bat"
SET "localSettingsPath=%projectPath%\src\local_settings.py"
SET "iconPath=%projectPath%\src\assets\tapio_favicon.ico"
SET "shortcutPath=%projectPath%\Tapio Analysis.lnk"

REM Create a batch file to activate the virtual environment and run the script
(
    ECHO @echo off
    ECHO call "%venvActivatePath%"
    ECHO python "%scriptPath%"
) > "%batchFilePath%"

REM Create local_settings.py if it does not already exist
IF NOT EXIST "%localSettingsPath%" (
    type NUL > "%localSettingsPath%"
)

REM Create a Windows shortcut to the batch file
SET "shortcutScript=%TEMP%\create_shortcut.vbs"
(
    ECHO Set WScriptShell = CreateObject("WScript.Shell")
    ECHO Set shortcut = WScriptShell.CreateShortcut("%shortcutPath%")
    ECHO shortcut.TargetPath = "%batchFilePath%"
    ECHO shortcut.WorkingDirectory = "%projectPath%"
    ECHO shortcut.IconLocation = "%iconPath%"
    ECHO shortcut.Save
) > "%shortcutScript%"

CSCRIPT //NoLogo "%shortcutScript%"
DEL "%shortcutScript%"

REM Display a verbose completion message
SET "frame=**********************************************************************"
ECHO.
ECHO %frame%
ECHO.
ECHO Tapio Analysis successfully installed.
ECHO - A shortcut to launch Tapio Analysis has been created in this directory. Move or copy it to a suitable location.
ECHO - Override default settings defined in settings.py by editing local_settings.py at:
ECHO %localSettingsPath%
ECHO - For support, training and customizations contact info@tapiotechnologies.com
ECHO.
ECHO %frame%
ECHO.

EXIT /B 0
