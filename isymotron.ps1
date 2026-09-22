<#
isymotron -- Windows shim.

The command surface now lives in ONE place: tools/isymotron_cli.py, whose verb
table is the single source of truth and whose completeness is a test. This shim
keeps the one verb that genuinely needs PowerShell -- `install`, which sets the
user PATH and reports the execution policy -- and delegates everything else, so
`isymotron <verb>` behaves the same on Windows and Linux.

    isymotron help
    isymotron host status
    isymotron keys list
    isymotron process verify <pid> --baseline proc.baseline.json
#>

$repo = $PSScriptRoot
$py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

if ($args.Count -ge 1 -and [string]$args[0] -eq 'install') {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })
    if ($entries -contains $repo) {
        Write-Output "already installed: $repo is on the user PATH"
    } else {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $repo) -join ';'), 'User')
        Write-Output "installed: $repo added to the user PATH"
    }
    $policy = Get-ExecutionPolicy -Scope CurrentUser
    if ($policy -eq 'Restricted') {
        Write-Output ''
        Write-Output "error: your execution policy is Restricted and scripts will not run."
        Write-Output "       fix it once, for your user only:"
        Write-Output "       Set-ExecutionPolicy RemoteSigned -Scope CurrentUser"
    }
    Write-Output ''
    Write-Output "open a NEW PowerShell window, then:  isymotron help"
    return
}

# Everything else is the Python CLI's job -- including help, the menu and the
# exit codes. Propagate the exit code unchanged.
& $py (Join-Path $repo 'tools\isymotron_cli.py') @args
exit $LASTEXITCODE
