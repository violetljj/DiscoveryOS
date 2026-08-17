[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("doctor", "bootstrap", "test", "run", "rebuild")]
    [string]$Command = "doctor",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Arguments,

    [string]$Module,
    [string]$Script,
    [string]$Code,
    [string[]]$TargetArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$VersionFile = Join-Path $ProjectRoot ".python-version"
$LockFile = Join-Path $ProjectRoot "uv.lock"
$EnvironmentPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"

function Resolve-Uv {
    $preferred = "E:\codex-tools\bin\uv.cmd"
    if (Test-Path -LiteralPath $preferred) {
        return $preferred
    }

    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    throw "ENV_BLOCKED: uv was not found. Install uv or restore E:\codex-tools\bin\uv.cmd."
}

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$UvArguments)

    & $script:UvPath @UvArguments
    if ($LASTEXITCODE -ne 0) {
        throw "ENV_BLOCKED: uv failed with exit code $LASTEXITCODE."
    }
}

function Get-ExpectedPythonVersion {
    if (-not (Test-Path -LiteralPath $VersionFile)) {
        throw "ENV_BLOCKED: missing .python-version."
    }
    return (Get-Content -Raw -LiteralPath $VersionFile).Trim()
}

function Invoke-Bootstrap {
    $expectedVersion = Get-ExpectedPythonVersion
    Push-Location $ProjectRoot
    try {
        Invoke-Uv sync --locked --python $expectedVersion
    }
    finally {
        Pop-Location
    }
}

function Invoke-Doctor {
    $failures = [System.Collections.Generic.List[string]]::new()
    $expectedVersion = Get-ExpectedPythonVersion

    Write-Host "PASS project root: $ProjectRoot"
    Write-Host "PASS uv: $(& $script:UvPath --version)"

    if (-not (Test-Path -LiteralPath $LockFile)) {
        $failures.Add("missing uv.lock")
    }
    else {
        Push-Location $ProjectRoot
        try {
            & $script:UvPath lock --check | Out-Host
            if ($LASTEXITCODE -ne 0) {
                $failures.Add("uv.lock does not match pyproject.toml")
            }
            else {
                Write-Host "PASS uv.lock is current"
            }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $failures.Add("project environment is missing; run bootstrap")
    }
    else {
        $actualVersion = (& $PythonPath -c "import platform; print(platform.python_version())").Trim()
        if ($actualVersion -ne $expectedVersion) {
            $failures.Add("Python $actualVersion does not match required $expectedVersion; run rebuild")
        }
        else {
            Write-Host "PASS Python $actualVersion"
        }

        & $PythonPath -c "import discoveryos; print('PASS import discoveryos')"
        if ($LASTEXITCODE -ne 0) {
            $failures.Add("cannot import discoveryos")
        }
    }

    if ($failures.Count -gt 0) {
        foreach ($failure in $failures) {
            Write-Error "FAIL $failure" -ErrorAction Continue
        }
        throw "ENV_BLOCKED: doctor found $($failures.Count) problem(s)."
    }
}

function Remove-ProjectEnvironment {
    if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
        return
    }

    $environmentItem = Get-Item -LiteralPath $EnvironmentPath -Force
    if ($null -ne $environmentItem.LinkType) {
        throw "REFUSED: .venv is a reparse point ($($environmentItem.LinkType))."
    }

    $resolvedEnvironment = (Resolve-Path -LiteralPath $EnvironmentPath).Path
    $expectedEnvironment = Join-Path $ProjectRoot ".venv"
    if (-not [string]::Equals($resolvedEnvironment, $expectedEnvironment, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "REFUSED: resolved environment is outside the expected project path: $resolvedEnvironment"
    }

    Remove-Item -LiteralPath $resolvedEnvironment -Recurse -Force
}

$UvPath = Resolve-Uv

switch ($Command) {
    "doctor" {
        Invoke-Doctor
    }
    "bootstrap" {
        Invoke-Bootstrap
        Invoke-Doctor
    }
    "test" {
        Invoke-Bootstrap
        Push-Location $ProjectRoot
        try {
            $env:PYTHONPATH = "src"
            & $PythonPath -m unittest discover -s tests -v @Arguments
            if ($LASTEXITCODE -ne 0) {
                throw "TEST_FAILED: unittest exited with $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }
    "run" {
        $targets = @($Module, $Script, $Code) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $targetCount = @($targets).Count
        if ($targetCount -ne 1) {
            throw "USAGE: project.ps1 run requires exactly one of -Module, -Script, or -Code."
        }
        Invoke-Bootstrap
        Push-Location $ProjectRoot
        try {
            $env:PYTHONPATH = "src"
            if ($Module) {
                & $PythonPath -m $Module @TargetArguments
            }
            elseif ($Script) {
                & $PythonPath $Script @TargetArguments
            }
            else {
                & $PythonPath -c $Code @TargetArguments
            }
            if ($LASTEXITCODE -ne 0) {
                throw "RUN_FAILED: Python exited with $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }
    "rebuild" {
        Remove-ProjectEnvironment
        Invoke-Bootstrap
        Invoke-Doctor
    }
}
