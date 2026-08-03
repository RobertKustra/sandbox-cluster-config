param(
  [Parameter(Mandatory = $false)]
  [string]$MinikubeIp,

  [Parameter(Mandatory = $false)]
  [switch]$Remove,

  [Parameter(Mandatory = $false)]
  [switch]$DryRun,

  [Parameter(Mandatory = $false)]
  [string]$HostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
)

$MarkerStart = "# sandbox-cluster-hosts-start"
$MarkerEnd = "# sandbox-cluster-hosts-end"

$SandboxHosts = @(
  "sandbox-nginx.dev.local",
  "sandbox-nginx.test.local",
  "sandbox-nginx.prod.local",
  "sandbox-vllm.llm.local",
  "grafana.monitoring.local",
  "alertmanager.monitoring.local",
  "jaeger.monitoring.local"
)

if (-not (Test-Path -Path $HostsPath)) {
  Write-Error "Hosts file not found at $HostsPath"
  exit 1
}

if (-not $Remove -and [string]::IsNullOrWhiteSpace($MinikubeIp)) {
  Write-Error "MinikubeIp is required unless -Remove is provided."
  exit 1
}

if (-not $Remove -and ($MinikubeIp -notmatch '^(\d{1,3}\.){3}\d{1,3}$')) {
  Write-Error "Invalid MinikubeIp value: $MinikubeIp"
  exit 1
}

if (-not $DryRun) {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

  if (-not $isAdmin) {
    Write-Error "Run this script in an elevated PowerShell (Run as Administrator)."
    exit 1
  }
}

$newline = "`r`n"
$newBlockLines = @($MarkerStart)
if (-not $Remove) {
  foreach ($entryHost in $SandboxHosts) {
    $newBlockLines += "$MinikubeIp $entryHost"
  }
}
$newBlockLines += $MarkerEnd
$newBlock = ($newBlockLines -join $newline)

$content = Get-Content -Path $HostsPath -Raw -Encoding Ascii
$pattern = [regex]::Escape($MarkerStart) + '.*?' + [regex]::Escape($MarkerEnd) + "\\r?\\n?"
$regex = [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)

if ($Remove) {
  if ($regex.IsMatch($content)) {
    $updated = $regex.Replace($content, "")
    if ($DryRun) {
      Write-Host "--- entries that would be removed from $HostsPath ---"
      Write-Host $newBlock
      exit 0
    }

    [System.IO.File]::WriteAllText($HostsPath, $updated, [System.Text.Encoding]::ASCII)
    Write-Host "Removed sandbox entries from $HostsPath"
  }
  else {
    Write-Host "No sandbox entries found in $HostsPath - nothing to remove."
  }
  exit 0
}

if ($regex.IsMatch($content)) {
  $updated = $regex.Replace($content, $newBlock + $newline)
  $action = "Updated"
}
else {
  $separator = ""
  if ($content.Length -gt 0 -and -not $content.EndsWith($newline)) {
    $separator = $newline
  }
  $updated = $content + $separator + $newBlock + $newline
  $action = "Added"
}

if ($DryRun) {
  Write-Host "--- entries that would be written to $HostsPath ---"
  Write-Host $newBlock
  exit 0
}

[System.IO.File]::WriteAllText($HostsPath, $updated, [System.Text.Encoding]::ASCII)
Write-Host "$action sandbox entries in $HostsPath"
Write-Host ""
Write-Host "Active entries in ${HostsPath}:"
foreach ($entryHost in $SandboxHosts) {
  Write-Host "$MinikubeIp $entryHost"
}
