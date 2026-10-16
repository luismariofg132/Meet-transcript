<#
.SYNOPSIS
    Builds the reproducible ClassScribe Windows standalone desktop application.

.DESCRIPTION
    Executes the pyside6-deploy / Nuitka pipeline, validates dependencies and bundle
    integrity, optionally runs automated smoke tests, and packages a portable ZIP.

.PARAMETER Python
    Path to Python 3.12 x64 executable. Defaults to .\.venv\Scripts\python.exe or system Python.

.PARAMETER Clean
    Clean prior build and deployment artifacts before building.

.PARAMETER ProduceZip
    Create portable distribution ZIP and SHA256 checksum in dist/.

.PARAMETER SkipSmokeTest
    Skip automated smoke test validation of the built bundle.
#>

[CmdletBinding()]
param (
    [string]$Python = "",
    [switch]$Clean = $true,
    [switch]$ProduceZip = $true,
    [switch]$SkipSmokeTest = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  ClassScribe Windows Standalone Build Pipeline" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Platform verification
if ($env:OS -notlike "*Windows*") {
    Write-Error "This build script must be executed on Windows 10/11 x64."
}

# 2. Python environment resolution
if (-not $Python) {
    if (Test-Path ".\.venv\Scripts\python.exe") {
        $Python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
    } elseif (Test-Path ".\.venv-build\Scripts\python.exe") {
        $Python = (Resolve-Path ".\.venv-build\Scripts\python.exe").Path
    } else {
        $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $Python -or -not (Test-Path $Python)) {
    Write-Error "Could not locate a valid Python executable. Specify -Python <path>."
}

Write-Host "Using Python: $Python" -ForegroundColor Green
$env:PYTHONOPTIMIZE = "1"

# Verify Python version and architecture (3.12 x64)
& $Python -c "import sys; assert sys.version_info[:2] == (3, 12), f'Python 3.12 required, found {sys.version}'; assert sys.maxsize > 2**32, '64-bit Python required'"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python verification failed. 64-bit Python 3.12 is required."
}

# Ensure Scripts directory is in PATH for tools like pyside6-deploy
$ScriptsDir = Split-Path -Parent $Python
$env:PATH = "$ScriptsDir;$env:PATH"

# 3. Clean prior build output safely
if ($Clean) {
    Write-Host "`n--- Cleaning previous build outputs ---" -ForegroundColor Yellow
    $DirsToClean = @(
        "dist\ClassScribe",
        "packaging\deployment"
    )
    foreach ($dir in $DirsToClean) {
        if (Test-Path $dir) {
            Write-Host "Removing: $dir"
            Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
        }
    }
}

# 4. Generate application icon if missing
if (-not (Test-Path "packaging\assets\classscribe.ico") -or -not (Test-Path "assets\classscribe.ico")) {
    Write-Host "`n--- Generating application icons ---" -ForegroundColor Yellow
    & $Python packaging\generate_icon.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to generate application icon."
    }
}

# Ensure classscribe/gui/assets/classscribe.ico exists
if (-not (Test-Path "classscribe\gui\assets\classscribe.ico")) {
    New-Item -ItemType Directory -Force -Path "classscribe\gui\assets" | Out-Null
    Copy-Item "assets\classscribe.ico" "classscribe\gui\assets\classscribe.ico" -Force
}

# 5. Execute pyside6-deploy
Write-Host "`n--- Running pyside6-deploy with Nuitka ---" -ForegroundColor Yellow
$SpecFile = "packaging\pysidedeploy.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Error "Spec file not found: $SpecFile"
}

& pyside6-deploy packaging/desktop.py -c $SpecFile --no-install
if ($LASTEXITCODE -ne 0) {
    Write-Error "pyside6-deploy build failed with exit code $LASTEXITCODE."
}

# 6. Locate output directory and place in dist/ClassScribe
Write-Host "`n--- Organizing standalone distribution ---" -ForegroundColor Yellow

$CandidateDirs = Get-ChildItem "packaging\deployment" -Directory -Filter "*.dist"
if ($CandidateDirs.Count -eq 0) {
    Write-Error "Nuitka output distribution directory not found under packaging\deployment."
}

$BuiltDist = $CandidateDirs[0].FullName
Write-Host "Built bundle located at: $BuiltDist"

$TargetDist = (Resolve-Path -Path ".").Path + "\dist\ClassScribe"
New-Item -ItemType Directory -Force -Path "dist" | Out-Null
if (Test-Path $TargetDist) {
    Remove-Item -Recurse -Force $TargetDist
}

Move-Item -Path $BuiltDist -Destination $TargetDist

# Ensure main executable is named ClassScribe.exe
if ((Test-Path "$TargetDist\desktop.exe") -and -not (Test-Path "$TargetDist\ClassScribe.exe")) {
    Move-Item "$TargetDist\desktop.exe" "$TargetDist\ClassScribe.exe"
}

# Ensure icon is present beside executable
if (-not (Test-Path "$TargetDist\classscribe.ico")) {
    Copy-Item "packaging\assets\classscribe.ico" "$TargetDist\classscribe.ico"
}

# Ensure license and third-party notices are present in bundle
if (Test-Path "LICENSE") {
    Copy-Item "LICENSE" "$TargetDist\LICENSE" -Force
}
if (Test-Path "THIRD_PARTY_NOTICES.txt") {
    Copy-Item "THIRD_PARTY_NOTICES.txt" "$TargetDist\THIRD_PARTY_NOTICES.txt" -Force
}

# 7. Automated smoke tests
if (-not $SkipSmokeTest) {
    Write-Host "`n--- Running bundle smoke tests ---" -ForegroundColor Yellow
    & $Python packaging\smoke_test.py $TargetDist
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Bundle smoke test failed."
    }
}

# 8. Produce Portable ZIP if requested
if ($ProduceZip) {
    Write-Host "`n--- Creating Portable ZIP archive ---" -ForegroundColor Yellow
    $Version = (& $Python -c "import classscribe; print(classscribe.__version__)").Trim()
    $ZipName = "ClassScribe-$Version-win64-portable.zip"
    $ZipPath = "dist\$ZipName"

    if (Test-Path $ZipPath) {
        Remove-Item -Force $ZipPath
    }

    # Compress dist\ClassScribe as root folder inside ZIP
    Compress-Archive -Path "$TargetDist" -DestinationPath $ZipPath -CompressionLevel Optimal

    # Generate SHA256 checksum
    $Hash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
    $HashFile = "$ZipPath.sha256"
    "$Hash *$ZipName" | Out-File -FilePath $HashFile -Encoding ascii

    Write-Host "Portable ZIP created: $ZipPath" -ForegroundColor Green
    Write-Host "SHA256: $Hash" -ForegroundColor Green
}

# 9. Final summary
$BundleFiles = Get-ChildItem -Recurse $TargetDist -File
$TotalSize = ($BundleFiles | Measure-Object -Property Length -Sum).Sum / 1MB
$ExeSize = (Get-Item "$TargetDist\ClassScribe.exe").Length / 1MB

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Bundle Directory: $TargetDist"
Write-Host "Main Executable:  $TargetDist\ClassScribe.exe ($([math]::Round($ExeSize, 2)) MB)"
Write-Host "Total Size:       $([math]::Round($TotalSize, 2)) MB"
Write-Host "Total Files:      $($BundleFiles.Count)"
Write-Host "=====================================================" -ForegroundColor Cyan
