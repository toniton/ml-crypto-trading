# MCT Trading Bot - Environment Setup (PowerShell for Windows)
param(
    [string]$DbChoice = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $ProjectRoot "venv"

Write-Host "=========================================="
Write-Host " MCT Trading Bot - Environment Setup"
Write-Host "=========================================="

# 1. Resolve Python
$PythonCmd = $null
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
} elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} else {
    Write-Error "Error: Python interpreter not found. Please install Python 3.11+."
    exit 1
}

$PythonVersion = & $PythonCmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
Write-Host "Found Python version: $PythonVersion using $PythonCmd"

# 2. Setup Virtual Environment
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment at: $VenvDir"
    & $PythonCmd -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists at: $VenvDir"
}

$VenvScripts = Join-Path $VenvDir "Scripts"
$VenvPython = Join-Path $VenvScripts "python.exe"
$VenvPip = Join-Path $VenvScripts "pip.exe"
$VenvPreCommit = Join-Path $VenvScripts "pre-commit.exe"
$VenvAlembic = Join-Path $VenvScripts "alembic.exe"

# 3. Upgrade Pip
Write-Host "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip

# 4. Install Dependencies
$ReqDev = Join-Path $ProjectRoot "requirements-dev.txt"
$ReqProd = Join-Path $ProjectRoot "requirements.txt"

if (Test-Path $ReqDev) {
    Write-Host "Installing development dependencies..."
    & $VenvPip install -r $ReqDev
} elseif (Test-Path $ReqProd) {
    Write-Host "Installing production dependencies..."
    & $VenvPip install -r $ReqProd
}

# Helper to update key-value in .env
function Set-EnvVariable {
    param([string]$Key, [string]$Value, [string]$Path)
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content $Path
    }
    $found = $false
    $newLines = @()
    foreach ($line in $lines) {
        if ($line -match "^$Key=") {
            $newLines += "$Key=$Value"
            $found = $true
        } else {
            $newLines += $line
        }
    }
    if (-not $found) {
        $newLines += "$Key=$Value"
    }
    $newLines | Set-Content $Path
}

# 5. Bootstrap Environment File
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Write-Host "Creating .env from .env.example..."
        Copy-Item -Path $EnvExample -Destination $EnvFile
    }
}

# 6. Database Prerequisite Setup
Write-Host ""
Write-Host "--------------------------------------------------"
Write-Host " Database Prerequisite Configuration"
Write-Host "--------------------------------------------------"
Write-Host "MCT requires a PostgreSQL database (local or remote) to store trading state."
Write-Host "Please select your database option:"
Write-Host "  1) Use existing remote database (e.g., Supabase, Neon, AWS RDS)"
Write-Host "  2) Set up local database (Docker or native PostgreSQL via db_setup)"
Write-Host "  3) Skip / Configure .env manually later"

if (-not $DbChoice) {
    $UserInput = Read-Host "Enter choice [1-3] (default: 2)"
    if (-not $UserInput) { $DbChoice = "2" } else { $DbChoice = $UserInput }
}

switch ($DbChoice) {
    "1" {
        Write-Host ""
        $DbHost = Read-Host "Host & Port (e.g. db.xxx.supabase.co:5432)"
        $DbName = Read-Host "Database name [trading]"
        if (-not $DbName) { $DbName = "trading" }
        $DbUser = Read-Host "Username [postgres]"
        if (-not $DbUser) { $DbUser = "postgres" }
        $DbPass = Read-Host "Password" -AsSecureString
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($DbPass)
        $DbPassPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

        Set-EnvVariable "DATABASE_CONNECTION_HOST" $DbHost $EnvFile
        Set-EnvVariable "POSTGRES_DATABASE" $DbName $EnvFile
        Set-EnvVariable "POSTGRES_USER" $DbUser $EnvFile
        Set-EnvVariable "POSTGRES_PASSWORD" $DbPassPlain $EnvFile
        Write-Host "[✓] Remote database credentials saved to .env."

        $RunMig = Read-Host "Run database schema migrations now? [Y/n]"
        if ($RunMig -ne "n" -and $RunMig -ne "N") {
            Push-Location $ProjectRoot
            if (Test-Path $VenvAlembic) {
                & $VenvAlembic upgrade head
            }
            Pop-Location
        }
    }
    "2" {
        Write-Host ""
        $DbSetupScript = Join-Path $ScriptDir "db_setup.ps1"
        if (Test-Path $DbSetupScript) {
            & $DbSetupScript
        }
    }
    "3" {
        Write-Host "Skipping database configuration. Please configure .env before starting the bot."
    }
    Default {
        Write-Host "Skipping database configuration."
    }
}

# 7. Install Git pre-commit hooks
$GitDir = Join-Path $ProjectRoot ".git"
if ((Test-Path $GitDir) -and (Test-Path $VenvPreCommit)) {
    Write-Host ""
    Write-Host "Configuring pre-commit git hooks..."
    Push-Location $ProjectRoot
    & $VenvPreCommit install
    Pop-Location
}

$ActivateScript = Join-Path $VenvScripts "Activate.ps1"
Write-Host "=========================================="
Write-Host " Setup complete! Virtual environment ready."
Write-Host " Activate with: & '$ActivateScript'"
Write-Host "=========================================="
