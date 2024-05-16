# Create a virtual environment in the .venv folder
if (!(Test-Path -Path ".venv")) {
    python -m venv .venv
}

# Install the packages from requirements.txt
& .\.venv\Scripts\pip.exe install -r requirements.txt

# Define the paths
$projectPath = Get-Location
$projectPathString = $projectPath.ToString()
$venvActivatePath = "$projectPathString\.venv\Scripts\activate"
$scriptPath = "$projectPathString\src\main.py"
$batchFilePath = "$projectPathString\run_tapio_analysis.bat"
$localSettingsPath = "$projectPathString\src\local_settings.py"
$iconPath = "$projectPathString\src\assets\tapio_favicon.ico"
$shortcutPath = "$projectPathString\Tapio Analysis.lnk"

# Create a batch file to activate the virtual environment and run the script
$batchFileContent = @"
@echo off
call "$venvActivatePath"
python "$scriptPath"
"@
Set-Content -Path $batchFilePath -Value $batchFileContent

# Create local_settings.py if it does not already exist
if (!(Test-Path -Path $localSettingsPath)) {
    New-Item -ItemType File -Path $localSettingsPath | Out-Null
}

# Create a Windows shortcut to the batch file
$WScriptShell = New-Object -ComObject WScript.Shell
$shortcut = $WScriptShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batchFilePath
$shortcut.WorkingDirectory = $projectPathString
$shortcut.IconLocation = $iconPath
$shortcut.Save()

# Display a verbose completion message
$frame = '*' * 70
$completionMessage = @"

$frame

Tapio Analysis successfully installed.
- A shortcut to launch Tapio Analysis has been created in this directory. Move or copy it to a suitable location.
- Override default settings defined in settings.py by editing local_settings.py at:
$localSettingsPath
- For support, training and customizations contact info@tapiotechnologies.com


$frame
"@
Write-Output $completionMessage

