# 清理损坏/editable 的 echotools 安装后，从 PyPI 重装。
# 典型症状：pip 报 uninstall-no-record-file / echotools None
param(
    [string]$Version = "2.3.81",
    [string]$Index = "https://pypi.org/simple"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

$EggInfo = Join-Path $Root "src/echotools.egg-info"
if (Test-Path -LiteralPath $EggInfo) {
    Remove-Item -LiteralPath $EggInfo -Recurse -Force
    Write-Host "removed editable egg-info: $EggInfo"
}

python -c @"
import site
from pathlib import Path

def broken_dist_info(path: Path) -> bool:
    if not path.is_dir() or not path.name.startswith('echotools-'):
        return False
    names = {p.name for p in path.iterdir()}
    return 'METADATA' not in names and 'RECORD' not in names

for base in site.getsitepackages() + [site.getusersitepackages()]:
    root = Path(base)
    if not root.is_dir():
        continue
    for child in root.glob('echotools-*.dist-info'):
        if broken_dist_info(child):
            print(child)
"@ | ForEach-Object {
    if ($_ -and (Test-Path -LiteralPath $_)) {
        Remove-Item -LiteralPath $_ -Recurse -Force
        Write-Host "removed broken dist-info: $_"
    }
}

python -m pip install --upgrade --force-reinstall --no-cache-dir "echotools==$Version" -i $Index
