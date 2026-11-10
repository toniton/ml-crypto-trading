# MCT Trading Bot - Windows PowerShell Interactive Installer Launcher
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 1. Resolve Python 3.11+ interpreter
$PythonBin = $null
$Candidates = @("python", "py", "python3")

foreach ($Candidate in $Candidates) {
    if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
        $VerCheck = & $Candidate -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonBin = $Candidate
            break
        }
    }
}

if (-not $PythonBin) {
    Write-Error "Error: Python 3.11+ is required but was not found in PATH. Please install Python 3.11+ and retry."
    exit 1
}

# 2. Check virtualenv python
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $ExecPython = $VenvPython
} else {
    $ExecPython = $PythonBin
}

# 3. Launch installer module
& $ExecPython -m installer @args
