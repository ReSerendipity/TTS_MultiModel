# PowerShell Startup Script - TTS MultiModel Voice Studio
# Hotkeys: q - Quit, r - Load Model, u - Unload Model, s - Model Status

$ErrorActionPreference = "Continue"
$WarningPreference = "Continue"
$Script:ConfirmExit = $false

function Request-ExitConfirmation {
    Write-Host ""
    Write-Host "[WARN] Press Y to confirm exit, or any other key to cancel..." -ForegroundColor Yellow -NoNewline
    $confirmation = $host.UI.RawUI.ReadKey("NoEcho, IncludeKeyDown")
    if ($confirmation.Character -eq 'y' -or $confirmation.Character -eq 'Y') {
        Write-Host " [Y] Exiting..." -ForegroundColor Green
        return $true
    }
    Write-Host " [Cancelled]" -ForegroundColor Cyan
    return $false
}

[Console]::TreatControlCAsInput = $false
[Console]::CancelKeyPress.Add_Invoked({
    param($sender, $e)
    $e.Cancel = $true
    $Script:ConfirmExit = $true
})

# --- Path Configuration ---
$Script:ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:WPY_PATH = Join-Path $Script:ROOT_DIR "WPy64-312101\python"
$Script:PY_EXE = Join-Path $Script:WPY_PATH "python.exe"
$Script:BIN_DIR = Join-Path $Script:ROOT_DIR "bin"

# --- Server Configuration ---
$Script:SERVER_IP = "127.0.0.1"
$Script:DEFAULT_PORT = 7869
$Script:SERVER_PORT = $null
$Script:BASE_URL = $null

# --- Environment Variables ---
$env:PATH = "$($Script:BIN_DIR);$($Script:WPY_PATH);$($Script:WPY_PATH)\Scripts;$env:PATH"
$env:PYTHONPATH = "$($Script:BIN_DIR);$env:PYTHONPATH"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_OFFLINE = "1"
$env:MODELSCOPE_OFFLINE = "1"

# --- Process State ---
$Script:AppProcess = $null

# --- Core Functions ---

function Resolve-ServerPort {
    $portFile = Join-Path $Script:ROOT_DIR ".server_port"
    if (Test-Path $portFile) {
        try {
            $port = (Get-Content $portFile -Raw).Trim()
            if ($port -match '^\d+$' -and [int]$port -ge 1 -and [int]$port -le 65535) {
                $Script:SERVER_PORT = $port
                $Script:BASE_URL = "http://${Script:SERVER_IP}:${port}"
                return $true
            }
        } catch {}
    }

    for ($p = $Script:DEFAULT_PORT; $p -lt $Script:DEFAULT_PORT + 10; $p++) {
        try {
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $tcpClient.Connect($Script:SERVER_IP, $p)
            $tcpClient.Close()
            try {
                $response = Invoke-RestMethod -Uri "http://${Script:SERVER_IP}:${p}/api/health/ping" -Method Get -TimeoutSec 3
                if ($response.status -eq "ok") {
                    $Script:SERVER_PORT = [string]$p
                    $Script:BASE_URL = "http://${Script:SERVER_IP}:${p}"
                    return $true
                }
            } catch {}
        } catch {}
    }
    return $false
}

function Start-Application {
    if ($null -ne $Script:AppProcess -and !$Script:AppProcess.HasExited) {
        Write-Host "[INFO] Application is already running" -ForegroundColor Yellow
        return
    }

    $portFile = Join-Path $Script:ROOT_DIR ".server_port"
    if (Test-Path $portFile) {
        Remove-Item $portFile -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[START] Launching TTS MultiModel application..." -ForegroundColor Cyan

    try {
        $launchScript = Join-Path $Script:BIN_DIR "clean_launch.py"

        if (!(Test-Path $launchScript)) {
            Write-Host "[ERROR] Launch script not found: $launchScript" -ForegroundColor Red
            return
        }

        $processStartInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processStartInfo.FileName = $Script:PY_EXE
        $processStartInfo.Arguments = "`"$launchScript`""
        $processStartInfo.WorkingDirectory = $Script:ROOT_DIR
        $processStartInfo.UseShellExecute = $false
        $processStartInfo.RedirectStandardOutput = $true
        $processStartInfo.RedirectStandardError = $true
        $processStartInfo.CreateNoWindow = $true

        $Script:AppProcess = New-Object System.Diagnostics.Process
        $Script:AppProcess.StartInfo = $processStartInfo

        $outputAction = {
            param($sender, $line)
            if ($line.Data -ne $null) {
                Write-Host $line.Data
            }
        }
        Register-ObjectEvent -InputObject $Script:AppProcess -EventName OutputDataReceived -Action $outputAction | Out-Null
        Register-ObjectEvent -InputObject $Script:AppProcess -EventName ErrorDataReceived -Action $outputAction | Out-Null

        $Script:AppProcess.Start() | Out-Null
        $Script:AppProcess.BeginOutputReadLine()
        $Script:AppProcess.BeginErrorReadLine()

        Write-Host "[OK] Application started, PID: $($Script:AppProcess.Id)" -ForegroundColor Green
    }
    catch {
        Write-Host "[ERROR] Failed to start application: $_" -ForegroundColor Red
    }
}

function Stop-Application {
    if ($null -eq $Script:AppProcess) {
        Write-Host "[INFO] No running application" -ForegroundColor Yellow
        return
    }

    try {
        if (!$Script:AppProcess.HasExited) {
            Write-Host "[QUIT] Stopping application..." -ForegroundColor Cyan
            $Script:AppProcess.Kill()
            $Script:AppProcess.WaitForExit(3000)
            Write-Host "[OK] Application stopped" -ForegroundColor Green
        }
        else {
            Write-Host "[INFO] Application has exited" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "[ERROR] Error stopping application: $_" -ForegroundColor Red
    }
    finally {
        $Script:AppProcess.Dispose()
        $Script:AppProcess = $null
        $portFile = Join-Path $Script:ROOT_DIR ".server_port"
        if (Test-Path $portFile) {
            Remove-Item $portFile -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ApiCall {
    param(
        [string]$Endpoint,
        [string]$Method = "Post",
        [hashtable]$Payload = @{}
    )

    if (!$Script:BASE_URL) {
        Write-Host "[ERROR] Server port not resolved, cannot make API call" -ForegroundColor Red
        return $null
    }

    $url = "$($Script:BASE_URL)$Endpoint"

    try {
        if ($Method -eq "Get") {
            $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 30
        }
        else {
            $jsonBody = $Payload | ConvertTo-Json -Compress
            $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)
            $response = Invoke-RestMethod -Uri $url -Method Post -Body $bodyBytes -ContentType "application/json; charset=utf-8" -TimeoutSec 120
        }
        return $response
    }
    catch {
        Write-Host "[ERROR] API call failed: $_" -ForegroundColor Red
        return $null
    }
}

function Get-ModelStatus {
    return Invoke-ApiCall -Endpoint "/api/model/status" -Method "Get"
}

function Invoke-LoadModel {
    Write-Host "[LOAD] Querying available models..." -ForegroundColor Cyan

    $status = Get-ModelStatus
    if ($null -eq $status) {
        Write-Host "[ERROR] Cannot reach server, please check if it is running" -ForegroundColor Red
        return
    }

    $engine = $null
    if ($status.current_engine) {
        $engine = $status.current_engine
    }
    elseif ($status.available_engines -and $status.available_engines.Count -gt 0) {
        $engine = $status.available_engines[0]
    }
    else {
        $engine = "voxcpm2"
    }

    Write-Host "[LOAD] Loading model: $engine" -ForegroundColor Cyan

    $result = Invoke-ApiCall -Endpoint "/api/model/load" -Payload @{ engine = $engine; size = $engine }

    if ($null -ne $result) {
        if ($result.status -eq "ok") {
            Write-Host "[OK] $($result.message)" -ForegroundColor Green
        }
        else {
            Write-Host "[ERROR] $($result.message)" -ForegroundColor Red
        }
    }
}

function Invoke-UnloadModel {
    Write-Host "[UNLOAD] Sending model unload request..." -ForegroundColor Cyan

    $result = Invoke-ApiCall -Endpoint "/api/model/unload"

    if ($null -ne $result) {
        if ($result.status -eq "ok") {
            Write-Host "[OK] $($result.message)" -ForegroundColor Green
        }
        else {
            Write-Host "[ERROR] $($result.message)" -ForegroundColor Red
        }
    }
}

function Show-ModelStatus {
    Write-Host "[STATUS] Querying model status..." -ForegroundColor Cyan

    $result = Get-ModelStatus
    if ($null -ne $result) {
        Write-Host "  Engine:  $($result.current_engine)" -ForegroundColor White
        Write-Host "  Status:  $($result.status)" -ForegroundColor White
        if ($result.available_engines) {
            Write-Host "  Available: $($result.available_engines -join ', ')" -ForegroundColor White
        }
    }
}

function Show-Help {
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host "      TTS MultiModel Voice Studio Console" -ForegroundColor Magenta
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  Hotkeys:" -ForegroundColor Cyan
    Write-Host "    [R] - Load Model" -ForegroundColor White
    Write-Host "    [U] - Unload Model" -ForegroundColor White
    Write-Host "    [S] - Model Status" -ForegroundColor White
    Write-Host "    [Q] - Quit Application" -ForegroundColor White
    Write-Host "    [H] - Show Help" -ForegroundColor White
    Write-Host ""
    if ($Script:SERVER_PORT) {
        Write-Host "  Server: http://${Script:SERVER_IP}:${Script:SERVER_PORT}" -ForegroundColor DarkGray
    }
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host ""
}

function Wait-ForServer {
    param([int]$TimeoutSeconds = 180)

    Write-Host "[INFO] Waiting for server to be ready..." -ForegroundColor Yellow
    $startTime = Get-Date

    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        if (Resolve-ServerPort) {
            try {
                $response = Invoke-RestMethod -Uri "$($Script:BASE_URL)/api/health/ping" -Method Get -TimeoutSec 3
                if ($response.status -eq "ok") {
                    Write-Host "[OK] Server is ready on port $($Script:SERVER_PORT)!" -ForegroundColor Green
                    return $true
                }
            } catch {}
        }
        Start-Sleep -Seconds 2
    }

    Write-Host "[WARN] Server did not become ready within $TimeoutSeconds seconds" -ForegroundColor Red
    return $false
}

# --- Main Loop ---
function Main {
    Show-Help

    Start-Application

    $serverReady = Wait-ForServer

    if (!$serverReady) {
        Write-Host "[WARN] Server not ready, but hotkeys still available" -ForegroundColor Yellow
    }

    Write-Host "[INFO] Press hotkeys to control the application..." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        if ($Script:ConfirmExit) {
            $Script:ConfirmExit = $false
            if (Request-ExitConfirmation) {
                Write-Host "[QUIT] Shutting down..." -ForegroundColor Red
                Stop-Application
                Write-Host "[DONE] Goodbye!" -ForegroundColor Green
                Start-Sleep -Milliseconds 500
                exit 0
            }
        }

        if ($host.UI.RawUI.KeyAvailable) {
            $key = $host.UI.RawUI.ReadKey("NoEcho, IncludeKeyDown")

            switch ($key.VirtualKeyCode) {
                81 {
                    Write-Host "`n[QUIT] Shutting down..." -ForegroundColor Red
                    Stop-Application
                    Write-Host "[DONE] Goodbye!" -ForegroundColor Green
                    Start-Sleep -Milliseconds 500
                    exit 0
                }

                82 {
                    Write-Host ""
                    Invoke-LoadModel
                }

                85 {
                    Write-Host ""
                    Invoke-UnloadModel
                }

                83 {
                    Write-Host ""
                    Show-ModelStatus
                }

                72 {
                    Show-Help
                }
            }
        }

        if ($null -ne $Script:AppProcess -and $Script:AppProcess.HasExited) {
            Write-Host "[WARN] Application process has exited" -ForegroundColor Red
            Start-Sleep -Seconds 1
        }

        Start-Sleep -Milliseconds 100
    }
}

try {
    Main
}
catch {
    $errMsg = "[FATAL] " + $_.Exception.Message
    Write-Host $errMsg -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    Stop-Application
    exit 1
}
finally {
    Stop-Application
}
