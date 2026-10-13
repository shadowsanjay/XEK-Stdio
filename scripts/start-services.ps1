param([switch]$WithModels,[switch]$CpuComfy)
$ErrorActionPreference='Stop'
$xekRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $xekRoot
$xekPython=Join-Path $xekRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $xekPython)) { throw 'Run install-services.ps1 first.' }
$xekLogs=Join-Path $xekRoot 'data/logs'
New-Item -ItemType Directory -Path $xekLogs -Force | Out-Null
function Start-XekService([string]$Name,[string]$Exe,[string[]]$Arguments,[string]$WorkingDirectory=$xekRoot) {
  $xekArgs=@{FilePath=$Exe; ArgumentList=$Arguments; WorkingDirectory=$WorkingDirectory;
    WindowStyle='Hidden'; PassThru=$true; RedirectStandardOutput=(Join-Path $xekLogs "$Name.log");
    RedirectStandardError=(Join-Path $xekLogs "$Name-error.log")}
  $xekProcess=Start-Process @xekArgs
  Write-Output "$Name launched (PID $($xekProcess.Id)). Check health and logs; launch is not readiness."
}
if ($WithModels) {
  $xekPlan=(& $xekPython -c 'import json; from xek.hardware import inspect_hardware,recommend; print(json.dumps(recommend(inspect_hardware())))') | ConvertFrom-Json
  if (-not $xekPlan.download_allowed) { throw ($xekPlan.blockers -join '; ') }
  $xekOllama=(Get-Command ollama -ErrorAction SilentlyContinue).Source
  if (-not $xekOllama) { throw 'Install Ollama and open a fresh terminal first.' }
  Start-XekService 'ollama' $xekOllama @('serve')
  $xekComfy=Join-Path $xekRoot '.runtime/ComfyUI'
  $xekComfyPython=Join-Path $xekComfy '.venv/Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $xekComfyPython)) { throw 'Install ComfyUI first.' }
  $xekMode=if ($CpuComfy) {'--cpu'} else {$xekPlan.comfy_flags[0]}
  Start-XekService 'comfy' $xekComfyPython @('main.py','--listen','127.0.0.1','--port','8188',$xekMode) $xekComfy
  $xekSpeechPython=Join-Path $xekRoot '.runtime/speech/Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $xekSpeechPython)) { throw 'Install the separate speech environment first.' }
  Start-XekService 'speech' $xekSpeechPython @('-m','uvicorn','services.speech.server:app','--host','127.0.0.1','--port','8001')
}
Start-XekService 'api' $xekPython @('-m','uvicorn','xek.main:app','--host','127.0.0.1','--port','8000')
Write-Output 'Start the frontend with pnpm run dev in apps/web. Run scripts/doctor.py to verify readiness.'
