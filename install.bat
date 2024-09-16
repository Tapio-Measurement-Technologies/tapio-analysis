@echo off
setlocal

:: Check if Python is installed
echo Checking if Python is installed...
where python >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo Python is installed.
) else (
    echo Python is not installed or not found in PATH. Please install Python to proceed.
    exit /b 1
)

:: Check if pip is installed
echo Checking if pip is installed...
where pip >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo pip is installed.
) else (
    echo pip is not installed or not found in PATH. Please install pip to proceed.
    exit /b 1
)

:: Create a virtual environment in the .venv folder if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv ".venv"
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment.
        exit /b 1
    )
    echo Virtual environment created.
)

:: Check if the virtual environment was created successfully
if not exist ".venv\Scripts\activate" (
    echo Failed to create virtual environment. Please check your Python installation.
    exit /b 1
)
echo Virtual environment exists.

:: Install the packages from requirements.txt
echo Activating virtual environment...
call ".\.venv\Scripts\activate"
if %ERRORLEVEL% neq 0 (
    echo Failed to activate virtual environment.
    exit /b 1
)
echo Virtual environment activated.

echo Installing packages from requirements.txt...
".\.venv\Scripts\pip.exe" install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Failed to install packages.
    exit /b 1
)
echo Packages installed.

:: Define the paths
set "projectPath=%cd%"
set "venvActivatePath=%projectPath%\.venv\Scripts\activate"
set "scriptPath=%projectPath%\src\main.py"
set "batchFilePath=%projectPath%\run_tapio_analysis.bat"
set "localSettingsPath=%projectPath%\src\local_settings.py"
set "iconPath=%projectPath%\src\assets\tapio_favicon.ico"
set "shortcutPath=%projectPath%\Tapio Analysis.lnk"

:: Create a batch file to activate the virtual environment and run the script
echo Creating batch file to run Tapio Analysis...
echo @echo off > "%batchFilePath%"
echo call "%venvActivatePath%" >> "%batchFilePath%"
echo python "%scriptPath%" >> "%batchFilePath%"
if %ERRORLEVEL% neq 0 (
    echo Failed to create batch file.
    exit /b 1
)
echo Batch file created: "%batchFilePath%"

:: Create local_settings.py if it does not already exist
if not exist "%localSettingsPath%" (
    echo Creating local_settings.py...
    type nul > "%localSettingsPath%"
    if %ERRORLEVEL% neq 0 (
        echo Failed to create local_settings.py.
        exit /b 1
    )
    echo local_settings.py created at "%localSettingsPath%"
)

:: Create a Windows shortcut to the batch file
echo Creating Windows shortcut...
powershell -Command "$WScriptShell = New-Object -ComObject WScript.Shell; $shortcut = $WScriptShell.CreateShortcut('%shortcutPath%'); $shortcut.TargetPath = '%batchFilePath%'; $shortcut.WorkingDirectory = '%projectPath%'; $shortcut.IconLocation = '%iconPath%'; $shortcut.Save()"
if %ERRORLEVEL% neq 0 (
    echo Failed to create shortcut.
    exit /b 1
)
echo Shortcut created: "%shortcutPath%"

:: Display a verbose completion message
echo *******************************************************************************
echo Tapio Analysis successfully installed.
echo - A shortcut to launch Tapio Analysis has been created in this directory. Move or copy it to a suitable location.
echo - Override default settings defined in settings.py by editing local_settings.py at:
echo "%localSettingsPath%"
echo - For support, training and customizations contact info@tapiotechnologies.com
echo *******************************************************************************

endlocal
pause
