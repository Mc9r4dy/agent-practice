[CmdletBinding()]
param(
    [string]$ContractTestScenario
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedRoot = 'F:\project_shuqi'
$Base = '25351d020a9ef413d9288010028acba579fe7938'
$Marker = '^Harden rollback and environment security contracts$'
$LogPath = '01_db-security-ops-teaching-agent/04_开发日志.md'
$AgentRoot = '01_db-security-ops-teaching-agent'
$ComposeFile = "$AgentRoot/infra/compose.yaml"
$EnvFile = "$AgentRoot/.env"
$ProjectName = 'shuqi-db-agent'
$WorkspaceContainer = 'shuqi-workspace'
$MysqlContainer = 'shuqi-mysql-sandbox'
$MysqlVolume = 'shuqi-db-agent-mysql-data'
$script:Scenario = $null
$script:ContractMode = -not [string]::IsNullOrWhiteSpace($ContractTestScenario)

if ($script:ContractMode) {
    $script:Scenario = Get-Content -LiteralPath $ContractTestScenario -Raw -Encoding UTF8 | ConvertFrom-Json
}

function New-NativeResult {
    param(
        [int]$ExitCode,
        [object[]]$Lines
    )
    [pscustomobject]@{
        ExitCode = $ExitCode
        Lines = @($Lines | ForEach-Object { [string]$_ })
    }
}

function Get-ScenarioProperty {
    param([string]$Name)
    $property = $script:Scenario.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "Contract scenario is missing '$Name'"
    }
    return $property.Value
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    $output = @(& $File @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    return New-NativeResult -ExitCode $exitCode -Lines $output
}

function Invoke-GitQuery {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    if ($script:ContractMode) {
        [Console]::Out.WriteLine("QUERY:$Name")
        $result = Get-ScenarioProperty -Name $Name
        return New-NativeResult -ExitCode ([int]$result.exitCode) -Lines @($result.lines)
    }
    return Invoke-Native -File 'git' -Arguments $Arguments
}

function Assert-NativeSucceeded {
    param(
        [Parameter(Mandatory)]$Result,
        [Parameter(Mandatory)][string]$Evidence
    )
    if ($Result.ExitCode -ne 0) {
        throw "$Evidence (native exit $($Result.ExitCode))"
    }
}

function Get-NormalizedPath {
    param([Parameter(Mandatory)][string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('\', '/'))
}

function Get-MySql57Boundary {
    if ($script:ContractMode) {
        [Console]::Out.WriteLine('QUERY:mysql57')
        $mock = Get-ScenarioProperty -Name 'mysql57'
        return [pscustomobject]@{ Status = [string]$mock.status; ProcessId = [int]$mock.pid }
    }
    $service = Get-Service -Name MySQL57 -ErrorAction Stop
    $serviceProcess = Get-CimInstance Win32_Service -Filter "Name='MySQL57'" -ErrorAction Stop
    return [pscustomobject]@{ Status = [string]$service.Status; ProcessId = [int]$serviceProcess.ProcessId }
}

function Get-Port3306Listeners {
    if ($script:ContractMode) {
        [Console]::Out.WriteLine('QUERY:listeners3306')
        return @((Get-ScenarioProperty -Name 'listeners3306') | ForEach-Object {
            [pscustomobject]@{
                LocalAddress = [string]$_.localAddress
                LocalPort = [int]$_.localPort
                OwningProcess = [int]$_.owningProcess
            }
        })
    }
    return @(Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction Stop)
}

function Get-ListenerSignatures {
    param([Parameter(Mandatory)][object[]]$Listeners)
    return @($Listeners | ForEach-Object {
        "$($_.LocalAddress)|$($_.LocalPort)|$($_.OwningProcess)"
    } | Sort-Object)
}

function Invoke-RollbackPreflight {
    $rootResult = Invoke-GitQuery -Name 'root' -Arguments ('rev-parse --show-toplevel' -split ' ')
    Assert-NativeSucceeded -Result $rootResult -Evidence 'Cannot resolve repository root'
    if ($rootResult.Lines.Count -ne 1 -or [string]::IsNullOrWhiteSpace($rootResult.Lines[0])) {
        throw 'Repository root query must return exactly one path'
    }
    $expectedRootNormalized = Get-NormalizedPath -Path $ExpectedRoot
    $actualRoot = Get-NormalizedPath -Path $rootResult.Lines[0]
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($actualRoot, $expectedRootNormalized)) {
        throw "Rollback requires exact repository root '$expectedRootNormalized'; actual '$actualRoot'"
    }
    Set-Location -LiteralPath $actualRoot

    $branchResult = Invoke-GitQuery -Name 'branch' -Arguments @('branch', '--show-current')
    Assert-NativeSucceeded -Result $branchResult -Evidence 'Cannot resolve current branch'
    if ($branchResult.Lines.Count -ne 1 -or $branchResult.Lines[0] -cne 'main') {
        throw 'Rollback requires the exact main branch'
    }

    $statusResult = Invoke-GitQuery -Name 'status' -Arguments ('status --porcelain=v1 --untracked-files=all' -split ' ')
    Assert-NativeSucceeded -Result $statusResult -Evidence 'Cannot inspect full worktree status'
    if ($statusResult.Lines.Count -ne 0) {
        throw 'Rollback requires a clean worktree including all untracked files'
    }

    $headResult = Invoke-GitQuery -Name 'head' -Arguments @('rev-parse', 'HEAD')
    Assert-NativeSucceeded -Result $headResult -Evidence 'Cannot resolve pre-rollback HEAD'
    if ($headResult.Lines.Count -ne 1 -or $headResult.Lines[0] -notmatch '^[0-9a-f]{40}$') {
        throw 'Pre-rollback HEAD must be one full SHA'
    }
    $preRollbackHead = $headResult.Lines[0]

    $remoteResult = Invoke-GitQuery -Name 'remote' -Arguments @('ls-remote', 'origin', 'refs/heads/main')
    Assert-NativeSucceeded -Result $remoteResult -Evidence 'Cannot resolve remote main'
    if ($remoteResult.Lines.Count -ne 1) {
        throw 'Remote main must resolve exactly once before rollback'
    }
    $remoteParts = @($remoteResult.Lines[0] -split '\s+')
    if ($remoteParts.Count -lt 2 -or $remoteParts[0] -cne $preRollbackHead -or $remoteParts[1] -cne 'refs/heads/main') {
        throw 'Remote main must exactly match pre-rollback HEAD'
    }

    $mysql57 = Get-MySql57Boundary
    if ($mysql57.Status -cne 'Running' -or $mysql57.ProcessId -le 0) {
        throw 'MySQL57 must be running with a valid positive PID'
    }
    $listeners3306 = @(Get-Port3306Listeners)
    if ($listeners3306.Count -eq 0) {
        throw 'At least one TCP/3306 listener owned by MySQL57 is required'
    }
    $foreignListeners = @($listeners3306 | Where-Object { $_.OwningProcess -ne $mysql57.ProcessId })
    if ($foreignListeners.Count -ne 0) {
        throw 'Every TCP/3306 listener must belong to MySQL57'
    }

    if ($script:ContractMode) {
        return [pscustomobject]@{
            Root = $actualRoot
            PreRollbackHead = $preRollbackHead
            MySql57Pid = $mysql57.ProcessId
            Port3306 = Get-ListenerSignatures -Listeners $listeners3306
        }
    }

    $mysqlInspect = Invoke-Native -File 'docker' -Arguments @('inspect', $MysqlContainer)
    Assert-NativeSucceeded -Result $mysqlInspect -Evidence 'Cannot inspect teaching MySQL baseline'
    $mysql = ($mysqlInspect.Lines -join "`n") | ConvertFrom-Json
    if ($mysql.Count -ne 1 -or $mysql[0].State.Health.Status -cne 'healthy') {
        throw 'Healthy teaching MySQL baseline required'
    }
    $dataMount = @($mysql[0].Mounts | Where-Object { $_.Destination -eq '/var/lib/mysql' })
    if ($dataMount.Count -ne 1 -or $dataMount[0].Name -cne $MysqlVolume) {
        throw 'Teaching volume baseline mismatch'
    }
    $volumeInspect = Invoke-Native -File 'docker' -Arguments @('volume', 'inspect', $MysqlVolume)
    Assert-NativeSucceeded -Result $volumeInspect -Evidence 'Teaching volume baseline missing'

    $listeners3307 = @(Get-NetTCPConnection -State Listen -LocalPort 3307 -ErrorAction Stop)
    $port3307 = Get-ListenerSignatures -Listeners $listeners3307
    if ($port3307.Count -ne 1 -or -not $port3307[0].StartsWith('127.0.0.1|3307|')) {
        throw 'Loopback-only TCP/3307 teaching listener baseline mismatch'
    }

    return [pscustomobject]@{
        Root = $actualRoot
        PreRollbackHead = $preRollbackHead
        MySqlId = [string]$mysql[0].Id
        MySqlVolume = [string]$dataMount[0].Name
        MySql57Pid = $mysql57.ProcessId
        Port3306 = Get-ListenerSignatures -Listeners $listeners3306
        Port3307 = $port3307
    }
}

function Ensure-LocalProcessExclusion {
    $gitDirResult = Invoke-Native -File 'git' -Arguments @('rev-parse', '--git-dir')
    Assert-NativeSucceeded -Result $gitDirResult -Evidence 'Cannot resolve Git metadata directory'
    if ($gitDirResult.Lines.Count -ne 1) { throw 'Git metadata directory must resolve exactly once' }
    $gitDir = Get-NormalizedPath -Path $gitDirResult.Lines[0]
    $excludePath = Join-Path $gitDir 'info/exclude'
    $excludeDirectory = Split-Path -Parent $excludePath
    if (-not (Test-Path -LiteralPath $excludeDirectory)) {
        New-Item -ItemType Directory -Path $excludeDirectory -Force | Out-Null
    }
    $existing = if (Test-Path -LiteralPath $excludePath) {
        @(Get-Content -LiteralPath $excludePath -Encoding UTF8)
    } else { @() }
    if (@($existing | Where-Object { $_.Trim() -ceq '.superpowers/' }).Count -eq 0) {
        [IO.File]::AppendAllText(
            $excludePath,
            ".superpowers/`r`n",
            [Text.UTF8Encoding]::new($false)
        )
    }
    $verified = @(Get-Content -LiteralPath $excludePath -Encoding UTF8 | Where-Object { $_.Trim() -ceq '.superpowers/' })
    if ($verified.Count -ne 1) {
        throw 'Failed to establish exactly one local .superpowers exclusion without deleting evidence'
    }
}

function Assert-FullStatusClean {
    $status = Invoke-Native -File 'git' -Arguments ('status --porcelain=v1 --untracked-files=all' -split ' ')
    Assert-NativeSucceeded -Result $status -Evidence 'Cannot inspect full worktree status'
    if ($status.Lines.Count -ne 0) {
        throw "Full worktree status is not clean: $($status.Lines -join '; ')"
    }
}

function Assert-IndexReadyForRollbackCommit {
    $status = Invoke-Native -File 'git' -Arguments ('status --porcelain=v1 --untracked-files=all' -split ' ')
    Assert-NativeSucceeded -Result $status -Evidence 'Cannot inspect pre-commit full status'
    if ($status.Lines.Count -eq 0) { throw 'Rollback produced no staged changes' }
    foreach ($line in $status.Lines) {
        if ($line.Length -lt 3 -or $line[0] -notmatch '[MADRC]' -or $line[1] -cne ' ') {
            throw "Pre-commit status includes unstaged, untracked, ignored, or unresolved work: $line"
        }
    }
}

function Restore-PreRollbackTrackedState {
    param([Parameter(Mandatory)][string]$PreRollbackHead)
    if ($script:ContractMode) {
        [Console]::Out.WriteLine('RECOVERY:tracked-state')
        $mockFailures = $script:Scenario.PSObject.Properties['recoveryFailures']
        if ($null -eq $mockFailures) { return @() }
        return @($mockFailures.Value | ForEach-Object { [string]$_ })
    }
    $failures = [Collections.Generic.List[string]]::new()
    $gitDirResult = Invoke-Native -File 'git' -Arguments @('rev-parse', '--git-dir')
    if ($gitDirResult.ExitCode -ne 0 -or $gitDirResult.Lines.Count -ne 1) {
        $failures.Add('cannot resolve Git metadata directory for abort verification')
    } else {
        $sequencerPath = Join-Path (Get-NormalizedPath -Path $gitDirResult.Lines[0]) 'sequencer'
        if (Test-Path -LiteralPath $sequencerPath) {
            $AbortCommand = 'git revert --abort'
            $abortParts = $AbortCommand -split ' '
            $abortResult = Invoke-Native -File $abortParts[0] -Arguments $abortParts[1..($abortParts.Count - 1)]
            if ($abortResult.ExitCode -ne 0) {
                $failures.Add("revert abort failed with native exit $($abortResult.ExitCode)")
            }
            if (Test-Path -LiteralPath $sequencerPath) {
                $failures.Add('revert sequencer remains after checked abort')
            }
        }
    }

    $restore = Invoke-Native -File 'git' -Arguments @(
        'restore', "--source=$PreRollbackHead", '--staged', '--worktree', '--', '.'
    )
    if ($restore.ExitCode -ne 0) {
        $failures.Add("tracked restore failed with native exit $($restore.ExitCode)")
    }
    $worktreeDiff = Invoke-Native -File 'git' -Arguments @('diff', '--quiet')
    if ($worktreeDiff.ExitCode -ne 0) { $failures.Add('worktree differs from pre-rollback HEAD') }
    $indexDiff = Invoke-Native -File 'git' -Arguments @('diff', '--cached', '--quiet')
    if ($indexDiff.ExitCode -ne 0) { $failures.Add('index differs from pre-rollback HEAD') }
    $head = Invoke-Native -File 'git' -Arguments @('rev-parse', 'HEAD')
    if ($head.ExitCode -ne 0 -or $head.Lines.Count -ne 1 -or $head.Lines[0] -cne $PreRollbackHead) {
        $failures.Add('HEAD no longer equals pre-rollback HEAD and cannot be moved automatically')
    }
    $status = Invoke-Native -File 'git' -Arguments ('status --porcelain=v1 --untracked-files=all' -split ' ')
    if ($status.ExitCode -ne 0) {
        $failures.Add("full recovery status failed with native exit $($status.ExitCode)")
    } elseif ($status.Lines.Count -ne 0) {
        $failures.Add("full recovery status is not clean: $($status.Lines -join '; ')")
    }
    return @($failures)
}

function Invoke-Compose {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $prefix = @('compose', '--project-name', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile)
    return Invoke-Native -File 'docker' -Arguments @($prefix + $Arguments)
}

function Assert-WorkspaceSystemTrust {
    $trust = Invoke-Native -File 'docker' -Arguments @(
        'exec', '-u', 'vscode', $WorkspaceContainer,
        'git', 'config', '--system', '--get-all', 'safe.directory'
    )
    Assert-NativeSucceeded -Result $trust -Evidence 'Cannot inspect restored workspace system Git trust'
    if ($trust.Lines.Count -ne 1 -or $trust.Lines[0] -cne '/workspace') {
        throw 'Restored workspace system Git trust must contain only /workspace'
    }
}

function Restore-PreRollbackWorkspace {
    param([Parameter(Mandatory)]$Baseline)
    if ($script:ContractMode) {
        [Console]::Out.WriteLine('RECOVERY:workspace')
        return
    }
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        throw "Pre-rollback environment file missing: $EnvFile"
    }
    if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
        throw "Pre-rollback Compose file missing: $ComposeFile"
    }
    $config = Invoke-Compose -Arguments @('config', '--quiet')
    Assert-NativeSucceeded -Result $config -Evidence 'Pre-rollback Compose config cannot be restored'
    $recreate = Invoke-Compose -Arguments @('up', '-d', '--build', '--no-deps', '--force-recreate', 'workspace')
    Assert-NativeSucceeded -Result $recreate -Evidence 'Pre-rollback workspace recreation failed'
    $tests = Invoke-Native -File 'docker' -Arguments @('exec', '-u', 'vscode', $WorkspaceContainer, 'pytest', '-q')
    Assert-NativeSucceeded -Result $tests -Evidence 'Pre-rollback workspace pytest failed during recovery'
    Assert-WorkspaceSystemTrust
    Assert-RuntimeUnchanged -Baseline $Baseline
}

function Invoke-AutomaticRecovery {
    param(
        [Parameter(Mandatory)]$Baseline,
        [Parameter(Mandatory)][bool]$WorkspaceMutationAttempted
    )
    $recoveryFailures = [Collections.Generic.List[string]]::new()
    foreach ($failure in @(Restore-PreRollbackTrackedState -PreRollbackHead $Baseline.PreRollbackHead)) {
        $recoveryFailures.Add($failure)
    }
    if ($WorkspaceMutationAttempted) {
        try { Restore-PreRollbackWorkspace -Baseline $Baseline } catch { $recoveryFailures.Add($_.Exception.Message) }
    }
    return @($recoveryFailures)
}

function Invoke-ContractRollbackSimulation {
    param([Parameter(Mandatory)]$Baseline)
    $failureProperty = $script:Scenario.PSObject.Properties['workflowFailure']
    if ($null -eq $failureProperty) {
        [Console]::Out.WriteLine('MUTATION:rollback-boundary')
        return
    }
    $workspaceProperty = $script:Scenario.PSObject.Properties['workspaceMutationAttempted']
    $workspaceMutationAttempted = $false
    if ($null -ne $workspaceProperty) { $workspaceMutationAttempted = [bool]$workspaceProperty.Value }
    [Console]::Out.WriteLine('MUTATION:rollback-attempt')
    $originalFailure = [string]$failureProperty.Value
    $recoveryFailures = @(Invoke-AutomaticRecovery -Baseline $Baseline -WorkspaceMutationAttempted $workspaceMutationAttempted)
    if ($recoveryFailures.Count -ne 0) {
        throw "MANUAL RECOVERY REQUIRED; original='$originalFailure'; preRollbackHead='$($Baseline.PreRollbackHead)'; workspaceMutationAttempted=$workspaceMutationAttempted; recoveryFailures='$($recoveryFailures -join ' | ')'"
    }
    throw "Rollback failed and automatic pre-rollback restoration was verified: $originalFailure"
}

function Assert-RuntimeUnchanged {
    param([Parameter(Mandatory)]$Baseline)
    $mysqlInspect = Invoke-Native -File 'docker' -Arguments @('inspect', $MysqlContainer)
    Assert-NativeSucceeded -Result $mysqlInspect -Evidence 'Cannot inspect teaching MySQL after rollback'
    $mysql = ($mysqlInspect.Lines -join "`n") | ConvertFrom-Json
    $mount = @($mysql[0].Mounts | Where-Object { $_.Destination -eq '/var/lib/mysql' })
    if ($mysql.Count -ne 1 -or $mysql[0].Id -cne $Baseline.MySqlId -or
        $mysql[0].State.Health.Status -cne 'healthy' -or $mount.Count -ne 1 -or
        $mount[0].Name -cne $Baseline.MySqlVolume) {
        throw 'Teaching MySQL identity, health, or volume changed'
    }
    $volume = Invoke-Native -File 'docker' -Arguments @('volume', 'inspect', $MysqlVolume)
    Assert-NativeSucceeded -Result $volume -Evidence 'Teaching volume missing after rollback'

    $mysql57 = Get-MySql57Boundary
    if ($mysql57.Status -cne 'Running' -or $mysql57.ProcessId -ne $Baseline.MySql57Pid) {
        throw 'MySQL57 status or PID changed during rollback'
    }
    $port3306 = Get-ListenerSignatures -Listeners @(Get-Port3306Listeners)
    $port3307 = Get-ListenerSignatures -Listeners @(Get-NetTCPConnection -State Listen -LocalPort 3307 -ErrorAction Stop)
    if (Compare-Object $Baseline.Port3306 $port3306) { throw 'TCP/3306 listeners changed' }
    if (Compare-Object $Baseline.Port3307 $port3307) { throw 'TCP/3307 listeners changed' }
}

function Invoke-Rollback {
    param([Parameter(Mandatory)]$Baseline)
    $rollbackMutationAttempted = $false
    $workspaceMutationAttempted = $false
    $commitSucceeded = $false
    try {
        Ensure-LocalProcessExclusion

        $markerResult = Invoke-Native -File 'git' -Arguments @('log', '--format=%H%x09%s', "--grep=$Marker")
        Assert-NativeSucceeded -Result $markerResult -Evidence 'Cannot resolve rollback marker'
        if ($markerResult.Lines.Count -ne 1) { throw 'Rollback marker must resolve to exactly one commit' }
        $rollbackHead = @($markerResult.Lines[0] -split "`t", 2)[0]
        if ($rollbackHead -notmatch '^[0-9a-f]{40}$') { throw 'Rollback marker SHA is invalid' }

        $baseAncestor = Invoke-Native -File 'git' -Arguments @('merge-base', '--is-ancestor', $Base, $rollbackHead)
        Assert-NativeSucceeded -Result $baseAncestor -Evidence 'Fixed baseline is not an ancestor of rollback marker'
        $headAncestor = Invoke-Native -File 'git' -Arguments @('merge-base', '--is-ancestor', $rollbackHead, $Baseline.PreRollbackHead)
        Assert-NativeSucceeded -Result $headAncestor -Evidence 'Rollback marker is not on current HEAD history'
        $merges = Invoke-Native -File 'git' -Arguments @('rev-list', '--merges', "$Base..$($Baseline.PreRollbackHead)")
        Assert-NativeSucceeded -Result $merges -Evidence 'Cannot inspect rollback range merges'
        if ($merges.Lines.Count -ne 0) { throw 'Rollback range must be linear and contain no merge commits' }
        $commitList = Invoke-Native -File 'git' -Arguments @('rev-list', "$Base..$rollbackHead")
        Assert-NativeSucceeded -Result $commitList -Evidence 'Cannot resolve rollback commit list'
        if ($commitList.Lines.Count -eq 0) { throw 'Rollback commit list is empty' }

        $RevertCommand = 'git revert --no-commit'
        $revertParts = $RevertCommand -split ' '
        $rollbackMutationAttempted = $true
        $revert = Invoke-Native -File $revertParts[0] -Arguments @($revertParts[1..($revertParts.Count - 1)] + $commitList.Lines)
        Assert-NativeSucceeded -Result $revert -Evidence 'Rollback revert failed'

        $preserveLog = Invoke-Native -File 'git' -Arguments @(
            'restore', "--source=$($Baseline.PreRollbackHead)", '--staged', '--worktree', '--', $LogPath
        )
        Assert-NativeSucceeded -Result $preserveLog -Evidence 'Failed to preserve complete development log'
        $confirmation = Read-Host "Append the actual rollback record to $LogPath, then type ROLLBACK-LOG-APPENDED"
        if ($confirmation -cne 'ROLLBACK-LOG-APPENDED') { throw 'Rollback log confirmation cancelled' }
        $stageLog = Invoke-Native -File 'git' -Arguments @('add', '--', $LogPath)
        Assert-NativeSucceeded -Result $stageLog -Evidence 'Failed to stage appended rollback log'
        $logDiff = Invoke-Native -File 'git' -Arguments @('diff', '--cached', '--quiet', '--', $LogPath)
        if ($logDiff.ExitCode -ne 1) { throw 'Appended rollback log could not be verified' }

        if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw "Rolled-back environment missing: $EnvFile" }
        if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) { throw "Rolled-back Compose config missing: $ComposeFile" }
        $config = Invoke-Compose -Arguments @('config', '--quiet')
        Assert-NativeSucceeded -Result $config -Evidence 'Rolled-back Compose configuration is invalid'
        $workspaceMutationAttempted = $true
        $recreate = Invoke-Compose -Arguments @('up', '-d', '--build', '--no-deps', '--force-recreate', 'workspace')
        Assert-NativeSucceeded -Result $recreate -Evidence 'Workspace-only rollback recreation failed'
        $tests = Invoke-Native -File 'docker' -Arguments @('exec', '-u', 'vscode', $WorkspaceContainer, 'pytest', '-q')
        Assert-NativeSucceeded -Result $tests -Evidence 'Post-rollback pytest failed'
        Assert-WorkspaceSystemTrust
        Assert-RuntimeUnchanged -Baseline $Baseline

        Assert-IndexReadyForRollbackCommit
        $CommitCommand = 'git commit'
        $commitParts = $CommitCommand -split ' '
        $commit = Invoke-Native -File $commitParts[0] -Arguments @($commitParts[1..($commitParts.Count - 1)] + @('-m', 'Rollback complete environment stage'))
        Assert-NativeSucceeded -Result $commit -Evidence 'Rollback commit failed'
        $commitSucceeded = $true
    } catch {
        $originalFailure = $_.Exception.Message
        if ($rollbackMutationAttempted -and -not $commitSucceeded) {
            $recoveryFailures = @(Invoke-AutomaticRecovery -Baseline $Baseline -WorkspaceMutationAttempted $workspaceMutationAttempted)
            if ($recoveryFailures.Count -ne 0) {
                throw "MANUAL RECOVERY REQUIRED; original='$originalFailure'; preRollbackHead='$($Baseline.PreRollbackHead)'; workspaceMutationAttempted=$workspaceMutationAttempted; recoveryFailures='$($recoveryFailures -join ' | ')'"
            }
            throw "Rollback failed and automatic pre-rollback restoration was verified: $originalFailure"
        }
        throw
    }

    Assert-FullStatusClean
    $PushCommand = 'git push'
    $pushParts = $PushCommand -split ' '
    $push = Invoke-Native -File $pushParts[0] -Arguments @($pushParts[1..($pushParts.Count - 1)] + @('origin', 'main'))
    if ($push.ExitCode -ne 0) {
        throw "MANUAL RECOVERY REQUIRED; rollback commit exists locally but push failed with native exit $($push.ExitCode)"
    }
    $local = Invoke-Native -File 'git' -Arguments @('rev-parse', 'HEAD')
    Assert-NativeSucceeded -Result $local -Evidence 'Cannot resolve rollback commit SHA'
    $remote = Invoke-Native -File 'git' -Arguments @('ls-remote', 'origin', 'refs/heads/main')
    Assert-NativeSucceeded -Result $remote -Evidence 'Cannot verify pushed remote main'
    if ($local.Lines.Count -ne 1 -or $remote.Lines.Count -ne 1 -or
        @($remote.Lines[0] -split '\s+')[0] -cne $local.Lines[0]) {
        throw 'MANUAL RECOVERY REQUIRED; local and remote rollback SHAs differ'
    }
    Assert-FullStatusClean
}

try {
    $baseline = Invoke-RollbackPreflight
    if ($script:ContractMode) {
        Invoke-ContractRollbackSimulation -Baseline $baseline
        exit 0
    }
    Invoke-Rollback -Baseline $baseline
    Write-Host 'Rollback completed with verified runtime and remote state.'
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
