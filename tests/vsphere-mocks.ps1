#!/usr/bin/pwsh
# tests/vsphere-mocks.ps1
# vim: set tabstop=4 shiftwidth=4 expandtab:

# Exercise the real import helpers with local stand-ins for every PowerCLI call.
param(
    [string]$Script,
    [string]$Ova,
    [string]$Server,
    [string]$FailAt = '',
    [switch]$Existing
)

function Connect-VIServer { [CmdletBinding()] param($Server, $Credential) }
function Disconnect-VIServer { [CmdletBinding()] param($Confirm) }
function Get-ContentLibrary {
    [CmdletBinding()] param($Name)
    [pscustomobject]@{ Name = $Name }
}
function Get-ContentLibraryItem {
    [CmdletBinding()] param($ContentLibrary, $Name)
    if ($Existing) { [pscustomobject]@{ Name = $Name; Description = '' } }
}
function Remove-ContentLibraryItem {
    [CmdletBinding()] param($ContentLibraryItem, $Confirm)
}
function New-ContentLibraryItem {
    [CmdletBinding()] param($ContentLibrary, $Name, $DisableOvfCertificateChecks, $Files, $ItemType, $Notes, $Confirm)
    Add-Content -LiteralPath "$Ova.uploads" -Value $Server
    if ($FailAt -eq 'upload') { Write-Error 'simulated upload failure'; return }
    [pscustomobject]@{ Name = $Name; Description = $Notes }
}
function Get-Folder {
    [CmdletBinding()] param($Name)
    [pscustomobject]@{ Name = $Name }
}
function Get-VMHost {
    [CmdletBinding()] param($Name)
    [pscustomobject]@{
        ConnectionState = 'Connected'
        ExtensionData = @{ Runtime = @{ InMaintenanceMode = $false } }
    }
}
function Get-Template { [CmdletBinding()] param($Name) }
function Get-VM { [CmdletBinding()] param($Name) }
function New-VM {
    [CmdletBinding()] param($Name, $VMHost, $ContentLibraryItem)
    [pscustomobject]@{ Name = $Name }
}
function Set-VM {
    [CmdletBinding()] param($VM, $Notes, $Confirm, [switch]$ToTemplate, $Name)
    if ($ToTemplate -and $FailAt -eq 'template') { Write-Error 'simulated template failure'; return }
    $VM
}
function Move-Inventory {
    [CmdletBinding()] param($Item, $Destination, $Confirm)
    if ($FailAt -eq 'move') { Write-Error 'simulated placement failure'; return }
    $Item
}

$env:vcenter_hostname = $Server
$env:vcenter_username = 'test-user'
$env:vcenter_password = 'test-password'
$arguments = @{ library = 'SharedLibrary'; ova = $Ova }
if ($Script -like '*-template.ps1') {
    $arguments.templateName = 'test-template'
    $arguments.folder = 'Templates'
}
& $Script @arguments
