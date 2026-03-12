#!/usr/bin/pwsh
# import-ova-vsphere.ps1
# vim: set tabstop=4 shiftwidth=4 expandtab:

<#
.SYNOPSIS
    Imports an OVA file into a vSphere Content Library.

.DESCRIPTION
    This script connects to a vCenter Server, validates the OVA file, and imports it into the specified Content Library.
    If an item with the same name already exists, it is removed before importing the new one.
    The script calculates a SHA1 hash of the OVA file and includes it in the item notes for integrity verification.

.PARAMETER library
    The name of the Content Library where the OVA will be imported.

.PARAMETER ova
    The path to the OVA file to import.

.PARAMETER vCenterServer
    The hostname or IP address of the vCenter Server. Can be provided via environment variable 'vcenter_hostname'.

.PARAMETER vCenterUser
    The username for vCenter authentication. Can be provided via environment variable 'vcenter_username'.

.PARAMETER vCenterPassword
    The password for vCenter authentication. Can be provided via environment variable 'vcenter_password'.

.EXAMPLE
    .\import-ova-vsphere.ps1 -library "MyLibrary" -ova "C:\path\to\file.ova"

.EXAMPLE
    $env:vcenter_hostname = "vcenter.example.com"
    $env:vcenter_username = "admin"
    $env:vcenter_password = "password"
    .\import-ova-vsphere.ps1 -library "MyLibrary" -ova "file.ova"

.NOTES
    Requires VMware PowerCLI module to be installed.
    Ensure you have appropriate permissions on the vCenter Server and Content Library.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$library,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ova,

    [string]$vCenterServer,
    [string]$vCenterUser,
    [SecureString]$vCenterPassword
)

# Use command line parameters if provided, otherwise fall back to environment variables
if (-not $vCenterServer) { $vCenterServer = $env:vcenter_hostname }
if (-not $vCenterUser) { $vCenterUser = $env:vcenter_username }
if (-not $vCenterPassword) {
    if ($env:vcenter_password) {
        $vCenterPassword = ConvertTo-SecureString $env:vcenter_password -AsPlainText -Force
    }
}

# Validate required parameters
if (-not $vCenterServer -or -not $vCenterUser -or -not $vCenterPassword) {
    Write-Error "vCenter connection parameters not provided. Please provide via command line or environment variables (vcenter_hostname, vcenter_username, vcenter_password)"
    exit 1
}

# Validate OVA file exists
if (-not (Test-Path $ova)) {
    Write-Error "OVA file '$ova' not found."
    exit 1
}

# Create secure credential object
try {
    $credential = New-Object System.Management.Automation.PSCredential ($vCenterUser, $vCenterPassword)
}
catch {
    Write-Error "Failed to create credential object: $_"
    exit 1
}

# Set default parameter values for VMware cmdlets
$PSDefaultParameterValues = @{
    "Connect-VIServer:Server"     = $vCenterServer
    "Connect-VIServer:Credential" = $credential
}

Write-Host "Attempting to connect to vCenter Server '$vCenterServer' as user '$vCenterUser'..."

try {
    Connect-VIServer -ErrorAction Stop
    Write-Host "Successfully connected to vCenter Server '$vCenterServer'."
}
catch {
    Write-Error "Failed to connect to vCenter Server '$vCenterServer' as user '$vCenterUser': $_"
    exit 1
}

try {
    # Resolve and validate OVA path
    $ovaPath = (Resolve-Path $ova).Path
    Write-Verbose "OVA file path: $ovaPath"

    $ovaFile = Split-Path -Path $ovaPath -Leaf
    Write-Verbose "OVA file name: $ovaFile"

    $ovaName = $ovaFile -replace '\.ova$', ''
    Write-Verbose "Content Library item name: $ovaName"

    # Calculate SHA1 hash for integrity verification
    $sha1Hash = Get-FileHash -Algorithm SHA1 $ovaPath
    $notes = "$($sha1Hash.Hash.ToLower())  $ovaName"
    Write-Verbose "SHA1 hash calculated: $($sha1Hash.Hash.ToLower())"

    # Check if content library exists
    try {
        $contentLibrary = Get-ContentLibrary -Name $library -ErrorAction Stop
        Write-Verbose "Content Library '$library' found."
    }
    catch {
        Write-Error "Content Library '$library' not found: $_"
        exit 1
    }

    # Remove existing item if it exists
    try {
        $existingItem = Get-ContentLibraryItem -ContentLibrary $contentLibrary -Name $ovaName -ErrorAction Stop
        Write-Verbose "Existing item '$ovaName' found. Removing..."
        Remove-ContentLibraryItem -ContentLibraryItem $existingItem -Confirm:$false
        Write-Verbose "Existing item removed."
    }
    catch {
        Write-Verbose "Content Library item '$ovaName' not found in library '$library' - this is expected for new uploads."
    }

    # Import the OVA file
    $params = @{
        ContentLibrary              = $contentLibrary
        Name                        = $ovaName
        DisableOvfCertificateChecks = $true
        Files                       = $ovaPath
        ItemType                    = 'OVA'
        Notes                       = $notes
        Confirm                     = $false
    }

    Write-Verbose "Importing OVA file into Content Library..."
    New-ContentLibraryItem @params
    Write-Host "Successfully imported OVA '$ovaFile' as '$ovaName' into Content Library '$library'."
}
catch {
    Write-Error "An error occurred during OVA import: $_"
    exit 1
}
finally {
    # Disconnect from vCenter Server
    try {
        Disconnect-VIServer -Confirm:$false -ErrorAction SilentlyContinue
        Write-Verbose "Disconnected from vCenter Server."
    }
    catch {
        Write-Warning "Failed to disconnect from vCenter Server: $_"
    }
}

