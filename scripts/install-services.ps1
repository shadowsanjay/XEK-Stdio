param(
  [ValidateSet('dependencies','ollama','comfy','speech','all')][string]$Component='dependencies',
  [string]$PythonExe='python',
  [ValidateSet('cpu','cu124')][string]$TorchBackend='cpu'
)
$ErrorActionPreference='Stop'
$xekRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $xekRoot
function Invoke-XekCommand([string]$Executable,[string[]]$Arguments) {
  & $Executable @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable (exit $LASTEXITCODE)" }
}
if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
  throw 'Install Python 3.12 from python.org or pass -PythonExe with its full executable path.'
}
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
  Invoke-XekCommand $PythonExe @('-m','venv','.venv')
}
$xekPython=Join-Path $xekRoot '.venv/Scripts/python.exe'
Invoke-XekCommand $xekPython @('-m','pip','install','-e','.[setup,test,transcription]')
if (-not (Test-Path -LiteralPath '.env')) { Invoke-XekCommand $xekPython @('scripts/configure_local.py') }
Invoke-XekCommand $xekPython @('scripts/configure_models.py','--apply')
Invoke-XekCommand $xekPython @('scripts/configure_ffmpeg.py','--download')
Invoke-XekCommand $xekPython @('scripts/doctor.py')
New-Item -ItemType Directory -Path '.runtime' -Force | Out-Null
if ($Component -in @('ollama','all')) {
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
      throw 'Install Ollama from https://ollama.com/download/windows; winget is unavailable.'
    }
    # Normal installer may request user consent. Never accepts license/permission prompts silently.
    Invoke-XekCommand 'winget' @('install','--id','Ollama.Ollama','--exact','--source','winget')
  }
  Write-Output 'Ollama installed. Open a fresh terminal if its executable is not yet on PATH. No model pulled.'
}
if ($Component -in @('comfy','all')) {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git from git-scm.com first.' }
  $xekComfy=Join-Path $xekRoot '.runtime/ComfyUI'
  if (-not (Test-Path -LiteralPath $xekComfy)) {
    Invoke-XekCommand 'git' @('clone','https://github.com/Comfy-Org/ComfyUI.git',$xekComfy)
  }
  if (-not (Test-Path -LiteralPath "$xekComfy/.venv/Scripts/python.exe")) {
    Invoke-XekCommand $PythonExe @('-m','venv',"$xekComfy/.venv")
  }
  $xekComfyPython=Join-Path $xekComfy '.venv/Scripts/python.exe'
  if ($TorchBackend -eq 'cu124') {
    Invoke-XekCommand $xekComfyPython @('-m','pip','install','torch==2.6.0','torchvision==0.21.0','torchaudio==2.6.0','--index-url','https://download.pytorch.org/whl/cu124')
  } else {
    Invoke-XekCommand $xekComfyPython @('-m','pip','install','torch','torchvision','torchaudio','--index-url','https://download.pytorch.org/whl/cpu')
  }
  Invoke-XekCommand $xekComfyPython @('-m','pip','install','-r',"$xekComfy/requirements.txt")
  $xekGguf=Join-Path $xekComfy 'custom_nodes/ComfyUI-GGUF'
  if (-not (Test-Path -LiteralPath $xekGguf)) {
    Invoke-XekCommand 'git' @('clone','https://github.com/city96/ComfyUI-GGUF.git',$xekGguf)
  }
  Invoke-XekCommand $xekComfyPython @('-m','pip','install','-r',"$xekGguf/requirements.txt")
  Invoke-XekCommand $xekComfyPython @('-c','import torch; print("Torch:",torch.__version__,"CUDA:",torch.cuda.is_available())')
  Write-Output 'ComfyUI and GGUF nodes installed in .runtime. Model weights were not downloaded.'
}
if ($Component -in @('speech','all')) {
  $xekSpeech=Join-Path $xekRoot '.runtime/speech'
  if (-not (Test-Path -LiteralPath "$xekSpeech/Scripts/python.exe")) {
    Invoke-XekCommand $PythonExe @('-m','venv',$xekSpeech)
  }
  $xekSpeechPython=Join-Path $xekSpeech 'Scripts/python.exe'
  Invoke-XekCommand $xekSpeechPython @('-m','pip','install','torch','torchaudio','--index-url','https://download.pytorch.org/whl/cpu')
  Invoke-XekCommand $xekSpeechPython @('-m','pip','install','-r','services/speech/requirements.txt')
  Write-Output 'Speech dependencies installed in a separate environment. Authorize Indic Parler-TTS access on Hugging Face before downloading weights.'
}
Invoke-XekCommand $xekPython @('scripts/doctor.py')
Write-Output 'Review the report, free the required RAM, then run download_models.py with --download for the selected profile.'
