param([switch]$WithModels,[switch]$CpuComfy,[switch]$BootstrapOnly)
$ErrorActionPreference='Stop'
$xekRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $xekRoot
$xekPython=Join-Path $xekRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $xekPython)) { throw 'Run install-services.ps1 first.' }
$xekLogs=Join-Path $xekRoot 'data/logs'
New-Item -ItemType Directory -Path $xekLogs -Force | Out-Null
function Start-XekService([string]$Name,[string]$Exe,[string[]]$Arguments,[string]$WorkingDirectory=$xekRoot,[string]$HealthUrl='') {
  if ($HealthUrl) {
    try {
      $xekHealth=Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 3 -UseBasicParsing
      if ($xekHealth.StatusCode -eq 200) { Write-Output "$Name is already reachable; reusing the service."; return }
    } catch { } # An unavailable service is launched below; readiness still requires a health check.
  }
  $xekArgs=@{FilePath=$Exe; ArgumentList=$Arguments; WorkingDirectory=$WorkingDirectory;
    WindowStyle='Hidden'; PassThru=$true; RedirectStandardOutput=(Join-Path $xekLogs "$Name.log");
    RedirectStandardError=(Join-Path $xekLogs "$Name-error.log")}
  $xekProcess=Start-Process @xekArgs
  Write-Output "$Name launched (PID $($xekProcess.Id)). Check health and logs; launch is not readiness."
}
if ($WithModels) {
  $xekPlan=(& $xekPython -c 'import json; from xek.hardware import inspect_hardware,recommend; print(json.dumps(recommend(inspect_hardware())))') | ConvertFrom-Json
  if (-not $BootstrapOnly -and -not $xekPlan.download_allowed) { throw ($xekPlan.blockers -join '; ') }
  $xekOllama=(Get-Command ollama -ErrorAction SilentlyContinue).Source
  if (-not $xekOllama) {
    $xekOllama=Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
    if (-not (Test-Path -LiteralPath $xekOllama)) { throw 'Install Ollama first.' }
  }
  Start-XekService 'ollama' $xekOllama @('serve') $xekRoot 'http://localhost:11434/api/tags'
  $xekComfy=Join-Path $xekRoot '.runtime/ComfyUI'
  $xekComfyPython=Join-Path $xekComfy '.venv/Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $xekComfyPython)) { throw 'Install ComfyUI first.' }
  $xekCuda=(& $xekComfyPython -c 'import torch; print(int(torch.cuda.is_available()))')
  $xekMode=if ($CpuComfy -or $xekCuda -ne '1') {'--cpu'} else {$xekPlan.comfy_flags[0]}
  Start-XekService 'comfy' $xekComfyPython @('main.py','--listen','127.0.0.1','--port','8188',$xekMode) $xekComfy 'http://127.0.0.1:8188/system_stats'
  $xekSpeechPython=Join-Path $xekRoot '.runtime/speech/Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $xekSpeechPython)) { throw 'Install the separate speech environment first.' }
  Start-XekService 'speech' $xekSpeechPython @('-m','uvicorn','services.speech.server:app','--host','127.0.0.1','--port','8001') $xekRoot 'http://localhost:8001/health'
}
Start-XekService 'api' $xekPython @('-m','uvicorn','xek.main:app','--host','127.0.0.1','--port','8000') $xekRoot 'http://localhost:8000/health'
if ($BootstrapOnly) { Write-Output 'Bootstrap mode starts service endpoints without loading/downloading weights. Inference still needs the model and hardware checks.' }
Write-Output 'Start the frontend with pnpm run dev in apps/web. Run scripts/doctor.py to verify readiness.'
