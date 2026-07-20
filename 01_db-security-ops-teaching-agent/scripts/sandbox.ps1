param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Preflight', 'Start', 'Status', 'Logs', 'Test', 'QuickReset', 'Rebuild', 'Stop')]
  [string]$Action
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ExpectedProjectRoot = 'F:\project_shuqi\01_db-security-ops-teaching-agent'
$ComposeFile = Join-Path $ProjectRoot 'infra\compose.yaml'
$EnvFile = Join-Path $ProjectRoot '.env'
$ProjectName = 'shuqi-db-agent'
$MysqlContainer = 'shuqi-mysql-sandbox'
$MysqlVolume = 'shuqi-db-agent-mysql-data'
$ProtectedMySqlPath = 'E:\MySql'

function Assert-ProjectRoot {
  $expected = [IO.Path]::GetFullPath($ExpectedProjectRoot)
  if (-not $ProjectRoot.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe project root: expected $expected but found $ProjectRoot"
  }

  foreach ($item in @(
      'pyproject.toml',
      '.env.example',
      'infra\compose.yaml',
      'scripts\sandbox.ps1'
    )) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $item))) {
      throw "Unsafe project root: missing $item"
    }
  }

  $composeText = Get-Content -LiteralPath $ComposeFile -Raw -Encoding utf8
  if ($composeText.Contains($ProtectedMySqlPath)) {
    throw 'Compose references protected MySQL57 path'
  }
}

function Invoke-NativeCommand {
  param(
    [Parameter(Mandatory = $true)]
    [scriptblock]$Command,
    [Parameter(Mandatory = $true)]
    [string]$FailureMessage
  )

  $previousPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = 'Continue'
    & $Command
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
  }

  if ($exitCode -ne 0) {
    throw "$FailureMessage (exit code $exitCode)"
  }
}

function Assert-DockerReady {
  Invoke-NativeCommand -FailureMessage 'Docker Desktop is not ready' -Command {
    docker info *> $null
  }
}

function New-RandomHex {
  param([int]$ByteCount = 24)

  $bytes = [byte[]]::new($ByteCount)
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($bytes)
  }
  finally {
    $rng.Dispose()
  }
  return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

function Ensure-EnvFile {
  if (Test-Path -LiteralPath $EnvFile) {
    return
  }

  $rootPassword = New-RandomHex
  $appPassword = New-RandomHex
  $readerPassword = New-RandomHex
  $lines = @(
    'SANDBOX_MYSQL_PORT=3307',
    "SANDBOX_MYSQL_ROOT_PASSWORD=$rootPassword",
    "SANDBOX_MYSQL_APP_PASSWORD=$appPassword",
    "SANDBOX_MYSQL_READER_PASSWORD=$readerPassword"
  )
  $content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
  [IO.File]::WriteAllText(
    $EnvFile,
    $content,
    [Text.UTF8Encoding]::new($false)
  )
}

function Invoke-Compose {
  param([Parameter(Mandatory = $true)][string[]]$ComposeArgs)

  Invoke-NativeCommand -FailureMessage "Compose failed: $($ComposeArgs -join ' ')" -Command {
    docker compose --project-name $ProjectName --env-file $EnvFile -f $ComposeFile @ComposeArgs
  }
}

function Assert-Port3307AvailableOrOwned {
  $listen = Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue
  if (-not $listen) {
    return
  }

  $owner = docker ps --filter "name=^/$MysqlContainer$" --format '{{.Names}}'
  if ($LASTEXITCODE -ne 0 -or $owner -ne $MysqlContainer) {
    throw 'Port 3307 is occupied by a non-project process'
  }
}

function Wait-MysqlHealthy {
  $deadline = (Get-Date).AddMinutes(3)
  do {
    $previousPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = 'Continue'
      $health = docker inspect --format '{{.State.Health.Status}}' $MysqlContainer 2>$null
      $inspectCode = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $previousPreference
    }

    if ($inspectCode -eq 0 -and $health -eq 'healthy') {
      return
    }
    Start-Sleep -Seconds 3
  } while ((Get-Date) -lt $deadline)

  throw 'MySQL sandbox health timeout'
}

function Assert-DestructiveTargets {
  Assert-ProjectRoot
  $container = docker ps -a --filter "name=^/$MysqlContainer$" --format '{{.Names}}'
  if ($LASTEXITCODE -ne 0) {
    throw 'Unable to verify container target'
  }
  if ($container -and $container -ne $MysqlContainer) {
    throw 'Unexpected container target'
  }

  $volume = docker volume ls --filter "name=^$MysqlVolume$" --format '{{.Name}}'
  if ($LASTEXITCODE -ne 0) {
    throw 'Unable to verify volume target'
  }
  if ($volume -and $volume -ne $MysqlVolume) {
    throw 'Unexpected volume target'
  }
}

Set-Location -LiteralPath $ProjectRoot
Assert-ProjectRoot

switch ($Action) {
  'Preflight' {
    Assert-DockerReady
    Assert-Port3307AvailableOrOwned
    if ((Get-Service -Name MySQL57 -ErrorAction Stop).Status -ne 'Running') {
      throw 'MySQL57 baseline changed'
    }
    'Preflight passed'
  }
  'Start' {
    Assert-DockerReady
    Assert-Port3307AvailableOrOwned
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('config', '--quiet')
    Invoke-Compose -ComposeArgs @('build', 'workspace')
    Invoke-Compose -ComposeArgs @('up', '-d')
    Wait-MysqlHealthy
    Invoke-Compose -ComposeArgs @('ps')
  }
  'Status' {
    Assert-DockerReady
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('ps')
  }
  'Logs' {
    Assert-DockerReady
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('logs', '--tail', '200')
  }
  'Test' {
    Assert-DockerReady
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('exec', '-T', 'workspace', 'pytest', '-q')
  }
  'QuickReset' {
    Assert-DockerReady
    Assert-DestructiveTargets
    Ensure-EnvFile
    Invoke-NativeCommand -FailureMessage 'Quick reset failed' -Command {
      docker exec $MysqlContainer sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot shuqi_sandbox < /docker-entrypoint-initdb.d/002_seed.sql'
    }
  }
  'Rebuild' {
    Assert-DockerReady
    Assert-DestructiveTargets
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('down', '--volumes', '--remove-orphans')
    Invoke-Compose -ComposeArgs @('up', '-d', '--build')
    Wait-MysqlHealthy
  }
  'Stop' {
    Assert-DockerReady
    Ensure-EnvFile
    Invoke-Compose -ComposeArgs @('down')
  }
}
