# PowerShell Startup Script - TTS MultiModel
# Hotkeys: q - Quit, r - Load Model, u - Unload Model

$ErrorActionPreference = "Continue"
$WarningPreference = "Continue"

# --- Path Configuration ---
$Script:ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:WPY_PATH = Join-Path $Script:ROOT_DIR "WPy64-312101\python"
$Script:PY_EXE = Join-Path $Script:WPY_PATH "python.exe"
$Script:BIN_DIR = Join-Path $Script:ROOT_DIR "bin"
$Script:SRC_DIR = Join-Path $Script:ROOT_DIR "faster-qwen3-tts-main"

# --- Server Configuration ---
$Script:SERVER_IP = "127.0.0.1"
$Script:SERVER_PORT = "7869"
$Script:BASE_URL = "https://${Script:SERVER_IP}:${Script:SERVER_PORT}"

# --- Environment Variables ---
$env:PATH = "$($Script:BIN_DIR);$($Script:WPY_PATH);$($Script:WPY_PATH)\Scripts;$env:PATH"
$env:PYTHONPATH = "$($Script:SRC_DIR);$($Script:BIN_DIR);$env:PYTHONPATH"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_OFFLINE = "1"
$env:MODELSCOPE_OFFLINE = "1"

# --- Process State ---
$Script:AppProcess = $null

# --- Core Functions ---

function Start-Application {
    if ($null -ne $Script:AppProcess -and !$Script:AppProcess.HasExited) {
        Write-Host "[INFO] Application is already running" -ForegroundColor Yellow
        return
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
    }
}

function Initialize-TlsBypass {
    try {
        Add-Type -TypeDefinition @"
using System.Net;
public class TlsBypass {
    public static void Setup() {
        ServicePointManager.SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        # ⚠️ 安全风险：仅适用于本地自签名证书场景
        ServicePointManager.ServerCertificateValidationCallback = delegate { return true; };
    }
}
"@ -ErrorAction SilentlyContinue
        [TlsBypass]::Setup()
    }
    catch {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls11 -bor [System.Net.SecurityProtocolType]::Tls
    }
}

function Invoke-ApiCall {
    param(
        [string]$Endpoint,
        [string]$Method = "Post",
        [hashtable]$Payload = @{}
    )

    $url = "$($Script:BASE_URL)$Endpoint"

    try {
        Initialize-TlsBypass

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
    return Invoke-ApiCall -Endpoint "/api/model_status" -Method "Get"
}

function Invoke-LoadModel {
    Write-Host "[LOAD] Sending model load request..." -ForegroundColor Cyan

    $result = Invoke-ApiCall -Endpoint "/api/load_model" -Payload @{ m_type = "voice_design"; size = "1.7B" }

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

    $result = Invoke-ApiCall -Endpoint "/api/unload_model"

    if ($null -ne $result) {
        if ($result.status -eq "ok") {
            Write-Host "[OK] $($result.message)" -ForegroundColor Green
        }
        else {
            Write-Host "[ERROR] $($result.message)" -ForegroundColor Red
        }
    }
}

function Show-Help {
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host "         TTS MultiModel Console" -ForegroundColor Magenta
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  Hotkeys:" -ForegroundColor Cyan
    Write-Host "    [R] - Load Model" -ForegroundColor White
    Write-Host "    [U] - Unload Model" -ForegroundColor White
    Write-Host "    [Q] - Quit Application" -ForegroundColor White
    Write-Host "    [H] - Show Help" -ForegroundColor White
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Magenta
    Write-Host ""
}

function Wait-ForServer {
    param([int]$TimeoutSeconds = 180)

    Write-Host "[INFO] Waiting for server to be ready..." -ForegroundColor Yellow
    $startTime = Get-Date

    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $tcpClient.Connect($Script:SERVER_IP, [int]$Script:SERVER_PORT)
            $tcpClient.Close()
            Write-Host "[OK] Server is ready!" -ForegroundColor Green
            Start-Sleep -Seconds 3
            return $true
        }
        catch {
            Start-Sleep -Seconds 3
        }
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
