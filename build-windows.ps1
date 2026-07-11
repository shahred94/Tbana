param(
    [ValidatePattern("^\d+\.\d+\.\d+$")]
    [string]$Version = "1.1.1"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python environment not found. Run install.bat first."
}

$PreviousErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import PyInstaller" 2>$null
$PyInstallerCheck = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorPreference

if ($PyInstallerCheck -ne 0) {
    & $Python -m pip install "pyinstaller==6.14.2"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller installation failed."
    }
}

$PreviousErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import _tkinter, tkinter; assert tkinter.TkVersion"
$TkinterCheck = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorPreference

if ($TkinterCheck -ne 0) {
    throw @"
Tkinter is not available in the Python installation used by .venv.
Install Python from python.org with the 'tcl/tk and IDLE' feature enabled,
recreate .venv, and run this build again.
"@
}

$DistDir = "dist-v$Version"
$BuildDir = "build-v$Version"

function Remove-BuildOutput {
    param([string]$RelativePath)

    $Target = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $Target)) {
        return
    }

    $ResolvedRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $ResolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if (-not $ResolvedTarget.StartsWith(
        $ResolvedRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to clean build output outside the project: $ResolvedTarget"
    }

    for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
        try {
            Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
            return
        }
        catch {
            if ($Attempt -eq 5) {
                throw
            }
            Start-Sleep -Seconds 1
        }
    }
}

Remove-BuildOutput $DistDir

& $Python -m PyInstaller `
    --noconfirm `
    --distpath $DistDir `
    --workpath $BuildDir `
    "TBanaStream.spec"
if ($LASTEXITCODE -ne 0) {
    throw "TBana Stream executable build failed."
}

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $InnoCandidates |
    Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -First 1

if (-not $Iscc) {
    Write-Warning "Inno Setup 6 was not found. The executable is ready in $DistDir\TBana Stream."
    Write-Warning "Install Inno Setup 6, then run this script again to create the installer."
    exit 2
}

& $Iscc `
    "/DMyAppVersion=$Version" `
    "/DMyDistDir=$DistDir" `
    "installer\TBanaStream.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed."
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  Executable: $DistDir\TBana Stream\TBana Stream.exe"
Write-Host "  Installer:  release\TBana-Stream-Setup-$Version.exe"
