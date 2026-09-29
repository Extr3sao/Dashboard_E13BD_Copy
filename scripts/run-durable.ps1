param(
  [Parameter(Mandatory = $true)][string]$RunId,
  [Parameter(Mandatory = $true)][string]$CommandLine,
  [string]$WorkingDirectory = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$runsDirectory = Join-Path $WorkingDirectory 'scratch\verification-runs'
$runDirectory = Join-Path $runsDirectory $RunId
New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null

$receiptPath = Join-Path $runDirectory 'receipt.json'
$stdoutPath = Join-Path $runDirectory 'stdout.log'
$stderrPath = Join-Path $runDirectory 'stderr.log'
$start = Get-Date
$sourceCommit = (git -C $WorkingDirectory rev-parse HEAD).Trim()
$treeHash = (git -C $WorkingDirectory rev-parse 'HEAD^{tree}').Trim()
$sourceFingerprint = (git -C $WorkingDirectory diff --binary HEAD | git hash-object --stdin).Trim()
$receipt = [ordered]@{
  run_id = $RunId
  command = $CommandLine
  working_directory = $WorkingDirectory
  start_time = $start.ToUniversalTime().ToString('o')
  end_time = $null
  duration_seconds = $null
  pid = $null
  exit_code = $null
  status = 'RUNNING'
  source_commit = $sourceCommit
  tree_hash = $treeHash
  source_fingerprint = $sourceFingerprint
  stdout_path = $stdoutPath
  stderr_path = $stderrPath
}
$receipt | ConvertTo-Json | Set-Content -Encoding utf8 $receiptPath

$previousLocation = Get-Location
Set-Location -LiteralPath $WorkingDirectory
$receipt.pid = $PID
$receipt | ConvertTo-Json | Set-Content -Encoding utf8 $receiptPath
try {
  & cmd.exe /d /c $CommandLine 1> $stdoutPath 2> $stderrPath
  $exitCode = $LASTEXITCODE
} finally {
  Set-Location -LiteralPath $previousLocation
}

$end = Get-Date
$receipt.end_time = $end.ToUniversalTime().ToString('o')
$receipt.duration_seconds = [math]::Round(($end - $start).TotalSeconds, 3)
$receipt.exit_code = $exitCode
$receipt.status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
$receipt | ConvertTo-Json | Set-Content -Encoding utf8 $receiptPath
