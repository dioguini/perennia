# Cria o atalho "Perennia" no Ambiente de trabalho. Chamado por criar_atalho_windows.bat.
# (Sem acentos de proposito: o PowerShell do Windows le este ficheiro como ANSI.)
$root = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $root "packaging\perennia.ico"
$exe  = Join-Path $root "dist\Perennia\Perennia.exe"
$args = ""

if (Test-Path $exe) {
    $target = $exe                      # a app empacotada (build_windows.bat)
} else {
    $target = Join-Path $root ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $target)) { $target = Join-Path $root "venv\Scripts\pythonw.exe" }
    if (-not (Test-Path $target)) {
        Write-Host "Nao encontrei o ambiente virtual do projeto (.venv)."
        Write-Host "Cria-o primeiro (RUN.md, seccao 2) ou faz o build (build_windows.bat)."
        exit 1
    }
    $args = '"' + (Join-Path $root "main.py") + '"'
}

$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "Perennia.lnk"
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $target
$sc.Arguments = $args
$sc.WorkingDirectory = $root
if (Test-Path $icon) { $sc.IconLocation = $icon }
$sc.Description = "Perennia - treino indoor"
$sc.Save()
Write-Host "Atalho criado: $link"
Write-Host "Aponta para: $target $args"
