<#
isymotron -- one command for the whole product.

Every verb below is a thin pass-through to a command that already exists in
this repository, run with `py` from the repository root. Nothing here holds
authority of its own: granting still goes through tools/host_cli.py or the
loopback console, and every rule of docs/AVATAR_CONTRACT.md applies.

The presentation layer is a small clap/rustc-style engine: ANSI truecolor on
an interactive terminal (brand #76B900, rustc-red errors), plain text when
the output is redirected or NO_COLOR is set (FORCE_COLOR overrides, for
debugging). The banner is a static GlyphFuck render -- see
tools/cli-banner.gf for the reproducible source; glyphfuck is NOT a runtime
dependency of this CLI.

    isymotron start --demo-host      console + floating pet + browser
    isymotron console --lan          the console, phone-ready
    isymotron test                   the acceptance suite
    isymotron host status            what THIS machine is and grants
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

# ---- style engine ---------------------------------------------------------
# rustc/clap behaviour: colour only where a human reads it.
$Redirected = [Console]::IsOutputRedirected -or [bool]$env:NO_COLOR
if ($env:FORCE_COLOR) { $Redirected = $false }
$E = [char]0x1B
if (-not $Redirected) {
    $C_RESET  = "$E[0m"
    $C_BOLD   = "$E[1m"
    $C_UL     = "$E[4m"
    $C_BRAND  = "$E[38;2;118;185;0m"    # #76B900
    $C_ACCENT = "$E[38;2;145;199;51m"   # #91C733
    $C_DIM    = "$E[38;2;120;120;128m"
    $C_RED    = "$E[1;38;2;254;63;63m"  # #FE3F3F (rustc error red)
} else {
    $C_RESET = $C_BOLD = $C_UL = $C_BRAND = $C_ACCENT = $C_DIM = $C_RED = ''
}

# GlyphFuck render of tools/cli-banner.gf (53x7 canvas, 5 content rows).
$Banner = @'
 ### ##### #   # #   # ###### ##### ####  ###### #   #
  #  #      # #  ## ## #    #   #   #  #  #    # #  ##
  #  #####   #   # # # #    #   #   ####  #    # # # #
  #      #   #   #   # #    #   #   #  #  #    # ##  #
 ### #####   #   #   # ######   #   #   # ###### #   #
'@

$Usage = "${C_BOLD}Usage:${C_RESET} isymotron ${C_DIM}[OPTIONS] [COMMAND] [ARGS]...${C_RESET}"

# The verb table. Everything below dispatches on the same names -- keep the
# two lists in sync or the CLI rots.
$Verbs = [ordered]@{
    'start'   = 'console + floating pet + browser (adds --avatar)'
    'console' = 'the local web console (--lan --demo-host --port N ...)'
    'pet'     = 'only the floating desktop pet (idles alone; follows the console)'
    'test'    = 'the acceptance suite (default: -q)'
    'build'   = 'rebuild IsyMotron.exe (smoke test included)'
    'spoof'   = 'append the hostile demo lines to an inbox'
    'host'    = 'tools/host_cli.py: status | grant | revoke | do'
    'demo'    = 'the M0 walkthrough (writes evidence/M0/)'
    'install' = 'make `isymotron` work from any new shell'
    'where'   = 'print the repository this CLI belongs to'
    'help'    = 'this help'
}

function Show-Banner {
    Write-Output ''
    Write-Output "$C_BRAND$Banner$C_RESET"
    Write-Output "  ${C_DIM}capability fabric${C_RESET}${C_BOLD} -- one command for the whole product$C_RESET"
    Write-Output ''
}

function Show-UsageError {
    param([string]$Message)
    Write-Output ''
    Write-Output "$C_RED${C_BOLD}error:$C_RESET $Message"
    Write-Output ''
    Write-Output $Usage
    Write-Output ''
    Write-Output "For more information, try 'isymotron --help'."
}

function Show-ShortHelp {
    Write-Output $Usage
    Write-Output ''
    Write-Output "${C_BOLD}${C_UL}Commands:${C_RESET}"
    foreach ($name in $Verbs.Keys) {
        Write-Output ("  {0}  {1}" -f $name.PadRight(8), $Verbs[$name])
    }
    Write-Output ''
    Write-Output "${C_BOLD}${C_UL}Options:${C_RESET}"
    Write-Output "  ${C_BOLD}-h, --help$C_RESET"
    Write-Output "          Print help (short; --help adds examples and notes)"
    Write-Output ''
    Write-Output "  ${C_BOLD}-V, --version$C_RESET"
    Write-Output '          Print version'
}

function Show-LongHelp {
    Show-ShortHelp
    Write-Output ''
    Write-Output "${C_BOLD}${C_UL}Examples:${C_RESET}"
    Write-Output "  isymotron ${C_BOLD}start${C_RESET} --demo-host"
    Write-Output "  isymotron ${C_BOLD}console${C_RESET} --lan --no-browser"
    Write-Output "  isymotron --lan                     ${C_DIM}# bare console flags pass through$C_RESET"
    Write-Output "  isymotron ${C_BOLD}host${C_RESET} status"
    Write-Output "  isymotron ${C_BOLD}spoof${C_RESET} --inbox `"$env:LOCALAPPDATA\IsyMotron\avatar\inbox.jsonl`""
    Write-Output ''
    Write-Output "${C_BOLD}${C_UL}Notes:${C_RESET}"
    Write-Output "  ${C_DIM}-$C_RESET `install` only affects new shells; the user PATH is not reloaded live."
    Write-Output "  ${C_DIM}-$C_RESET Colours render on an interactive terminal; redirected output is plain."
    Write-Output "  ${C_DIM}-$C_RESET Banner: GlyphFuck render of tools/cli-banner.gf (MIT, same author)."
}

# ---- dispatch -------------------------------------------------------------
function Invoke-InRepo {
    param([string[]]$CommandArgs)
    Push-Location $repo
    try {
        & $py @CommandArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
}

if ($Command -eq '' -or $Command -in @('help', '--help')) {
    Show-Banner
    Show-LongHelp
    return
}
elseif ($Command -eq '-h') {
    Show-ShortHelp
    return
}
elseif ($Command -in @('-V', '--version')) {
    $hash = ''
    try { $hash = (git -C $repo rev-parse --short HEAD 2>$null) } catch { }
    Write-Output "isymotron 1.0.0$(if ($hash) { " $C_DIM($hash)$C_RESET" })"
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
        Write-Output "${C_DIM}already installed:$C_RESET $repo is on the user PATH"
    } else {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $repo) -join ';'), 'User')
        Write-Output "$C_BRAND${C_BOLD}installed:$C_RESET $repo added to the user PATH"
    }
    $policy = Get-ExecutionPolicy -Scope CurrentUser
    if ($policy -eq 'Restricted') {
        Write-Output ''
        Write-Output "$C_RED${C_BOLD}error:$C_RESET your execution policy is Restricted and scripts will not run."
        Write-Output "       fix it once, for your user only:"
        Write-Output "       ${C_BOLD}Set-ExecutionPolicy RemoteSigned -Scope CurrentUser$C_RESET"
    }
    Write-Output ''
    Write-Output "open a ${C_BOLD}NEW${C_RESET} PowerShell window, then:  isymotron help"
}
elseif ($Command -like '-*') {
    # Bare console flags: `isymotron --lan --avatar` runs the console.
    Invoke-InRepo (@('-m', 'console') + @($Command) + $Rest)
}
else {
    Show-UsageError "unknown command '$Command'"
    exit 2
}
