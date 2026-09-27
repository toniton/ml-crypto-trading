# MCT Trading Bot - Database Setup & Runner (PowerShell for Windows)
param(
    [string]$Option = ""
)

Write-Host "=========================================="
Write-Host " MCT Trading Bot - Database Setup & Runner"
Write-Host "=========================================="

function Test-PortListening {
    param([string]$HostName = "localhost", [int]$Port = 5432)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($HostName, $Port)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Start-LocalPostgresService {
    Write-Host "Attempting to start local PostgreSQL service..."
    try {
        Start-Service postgresql* -ErrorAction SilentlyContinue
    } catch {}
}

function Start-DockerPostgresContainer {
    Write-Host "Starting PostgreSQL container via Docker Compose..."
    $DockerRunning = & docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        & docker compose up -d postgres
        Write-Host "Waiting for PostgreSQL container to start..."
        $retries = 15
        while ($retries -gt 0) {
            if (Test-PortListening "localhost" 5432) {
                Write-Host "[✓] PostgreSQL container is up and listening on port 5432."
                return $true
            }
            Start-Sleep -Seconds 1
            $retries--
        }
        Write-Host "[!] Container launched, but port 5432 is not ready yet."
    } else {
        Write-Host "Error: Docker Desktop is not running. Please start Docker Desktop and try again."
        return $false
    }
}

function Install-DockerOnWindows {
    Write-Host "Installing Docker Desktop via winget..."
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        & winget install Docker.DockerDesktop
        Write-Host "Please start Docker Desktop to finalize setup, then re-run this script."
    } else {
        Write-Host "winget not found. Please download Docker Desktop from: https://www.docker.com/products/docker-desktop/"
    }
}

function Install-NativePostgresOnWindows {
    Write-Host "Installing PostgreSQL via winget..."
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        & winget install PostgreSQL.PostgreSQL
        Start-LocalPostgresService
    } else {
        Write-Host "winget not found. Please download PostgreSQL from: https://www.postgresql.org/download/windows/"
    }
}

# 1. Check if already active
if (Test-PortListening "localhost" 5432) {
    Write-Host "[✓] PostgreSQL is already running and accessible on localhost:5432."
    exit 0
}

# 2. Check if local PostgreSQL is installed
$PsqlFound = (Get-Command "psql" -ErrorAction SilentlyContinue) -or (Get-Command "postgres" -ErrorAction SilentlyContinue) -or (Get-Command "pg_isready" -ErrorAction SilentlyContinue)
if ($PsqlFound) {
    Write-Host "[!] PostgreSQL is installed locally but not running."
    Start-LocalPostgresService
    if (Test-PortListening "localhost" 5432) {
        Write-Host "[✓] Local PostgreSQL service successfully started."
        exit 0
    }
}

# 3. Check if Docker is installed
$DockerFound = Get-Command "docker" -ErrorAction SilentlyContinue
if ($DockerFound) {
    Write-Host "[✓] Docker is installed on this machine."
    Start-DockerPostgresContainer
    exit 0
}

# 4. Neither installed -> Prompt user for selection
if (-not $Option) {
    Write-Host ""
    Write-Host "Neither PostgreSQL nor Docker is running on this machine."
    Write-Host "Please select your preferred installation method:"
    Write-Host "  1) Docker & Docker Compose (Recommended - Isolated container)"
    Write-Host "  2) Native PostgreSQL"
    Write-Host "  3) Cancel"
    $UserInput = Read-Host "Enter choice [1-3] (default: 1)"
    if (-not $UserInput) { $Option = "1" } else { $Option = $UserInput }
}

switch ($Option) {
    "1" { Install-DockerOnWindows }
    "2" { Install-NativePostgresOnWindows }
    "3" { Write-Host "Database setup cancelled."; exit 0 }
    default { Write-Host "Invalid option: $Option"; exit 1 }
}

Write-Host ""
Write-Host "Database setup completed. You can apply schema migrations with:"
Write-Host "  make upgrade  (or: alembic upgrade head)"
