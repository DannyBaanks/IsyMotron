<#
isymotron -- one command for the whole product.

Every verb below is a thin pass-through to a command that already exists in
this repository, run with `py` from the repository root. Nothing here holds
authority of its own: granting still goes through tools/host_cli.py or the
loopback console, and every rule of docs/AVATAR_CONTRACT.md applies.

    isymotron start --demo-host      console + floating pet + browser
    isymotron console --lan          the console, phone-ready
    isymotron test                   the acceptance suite
    isymotron host status            what THIS machine is and grants

Run `isymotron help` for the full list. Make the bare command work from any
new shell with `isymotron install` (adds this folder to the user PATH).
#>

# No param() and no [CmdletBinding()] on purpose: a pass-through CLI must
# accept ANY flag the subcommand understands (--lan, --port, --help...), and
# a parameter block would reject unknown ones before this body ever runs.
$Command = ''
$Rest = @()
if ($args.Count -ge 1) { $Command = [string]$args[0] }
if ($args.Count -ge 2) { $Rest = @($args[1..($args.Count - 1)]) }

$repo = $PSScriptRoot
$py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

function Invoke-InRepo {
    param([string[]]$CommandArgs)
    Push-Location $repo
    try {
        & $py @CommandArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
}

function Show-Help {
    Write-Output @'
isymotron -- one command for the whole product.

  usage: isymotron <verb> [options]
         isymotron [console flags]      flags go straight to the console

  verbs:
    start   [flags]     console + floating pet + browser (adds --avatar)
    console [flags]     the local web console (--lan --demo-host --port N
                        --no-browser --grants <path> ...)
    pet     [--port N]  only the floating desktop pet (reads avatar.token;
                        default port 8760, the console's own default)
    test    [args]      the acceptance suite (default: -q)
    build   [args]      rebuild IsyMotron.exe (smoke test included)
    spoof   [--inbox <path>]  append the hostile demo lines to an inbox
    host    <args>      tools/host_cli.py: status | grant | revoke | do
    demo                the M0 walkthrough (writes evidence/M0/)
    install             make `isymotron` work from any new shell
    where               print the repository this CLI belongs to
    help                this help

  examples:
    isymotron start --demo-host
    isymotron console --lan --no-browser
    isymotron --lan                     # same thing: flags pass through
    isymotron host status
    isymotron spoof --inbox "$env:LOCALAPPDATA\IsyMotron\avatar\inbox.jsonl"
'@
}

if ($Command -eq '' -or $Command -in @('help', '--help', '-h', '-?', '/?')) {
    Show-Help
    return
}
elseif ($Command -eq 'console') { Invoke-InRepo (@('-m', 'console') + $Rest) }
elseif ($Command -eq 'start')   { Invoke-InRepo (@('-m', 'console', '--avatar') + $Rest) }
elseif ($Command -eq 'pet')     { Invoke-InRepo (@('-m', 'console', '--avatar-worker', '--port', '8760') + $Rest) }
elseif ($Command -eq 'test')    {
    if ($Rest.Count) { Invoke-InRepo (@('-m', 'pytest') + $Rest) }
    else { Invoke-InRepo @('-m', 'pytest', '-q') }
}
elseif ($Command -eq 'build')   { Invoke-InRepo (@('build_exe.py') + $Rest) }
elseif ($Command -eq 'spoof')   { Invoke-InRepo (@('tools\avatar_spoof.py') + $Rest) }
elseif ($Command -eq 'host')    {
    if ($Rest.Count) { Invoke-InRepo (@('tools\host_cli.py') + $Rest) }
    else { Invoke-InRepo @('tools\host_cli.py', 'status') }
}
elseif ($Command -eq 'demo')    { Invoke-InRepo (@('tools\m0_demo.py') + $Rest) }
elseif ($Command -eq 'where')   { Write-Output $repo }
elseif ($Command -eq 'install') {
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
        Write-Output "warning: your execution policy is Restricted and scripts will not run."
        Write-Output "         fix it once, for your user only:"
        Write-Output "         Set-ExecutionPolicy RemoteSigned -Scope CurrentUser"
    }
    Write-Output "open a NEW PowerShell window, then:  isymotron help"
}
elseif ($Command -like '-*') {
    # Bare console flags: `isymotron --lan --avatar` runs the console.
    Invoke-InRepo (@('-m', 'console') + @($Command) + $Rest)
}
else {
    Write-Output "isymotron: unknown command '$Command'"
    Show-Help
    exit 1
}
