# SO-101 Arm Studio 설치: 외부 모델 받기 + 가상환경 만들기 (PowerShell 에서 실행)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force third_party | Out-Null

# MuJoCo Menagerie 의 SO-101 모델만 (Apache-2.0)
if (-not (Test-Path third_party/mujoco_menagerie)) {
  git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
  git -C third_party/mujoco_menagerie sparse-checkout set robotstudio_so101
}
# 원본 SO-ARM100 시뮬레이션 파일 (참고용, Apache-2.0)
if (-not (Test-Path third_party/SO-ARM100)) {
  git clone --depth 1 --filter=blob:none --sparse https://github.com/TheRobotStudio/SO-ARM100.git third_party/SO-ARM100
  git -C third_party/SO-ARM100 sparse-checkout set Simulation/SO101
}
if (-not (Test-Path .venv)) { python -m venv .venv }
.venv/Scripts/python -m pip install -r requirements.txt
Write-Host "완료: studio/run_studio.bat 를 더블클릭하세요."
