#!/usr/bin/pwsh
# import-ova-vsphere-template.ps1
# vim: set tabstop=4 shiftwidth=4 expandtab:

<#
.SYNOPSIS
    Imports an OVA or reuses one already in the Content Library and converts it into a vSphere template.

.DESCRIPTION
    This script connects to a vCenter Server, imports the specified OVA into a
    Content Library, deploys a temporary VM from that library item, and converts
    the VM to a vSphere template in the requested inventory folder.

    The deployment step selects any available ESXi host, then converts the VM
    to a template and moves that template into the Templates inventory folder.

    This is the `vSphere Template` branch derived from the `vSphere OVA` branch.
    The template name is expected to follow the `-base.tmpl` convention, such
    as `centos10s-base.tmpl`.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$library,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ova,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$templateName,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$folder,

    [string]$vCenterServer,
    [string]$vCenterUser,
    [SecureString]$vCenterPassword,
    [switch]$UseExistingLibraryItem
)

if (-not $vCenterServer) { $vCenterServer = $env:vcenter_hostname }
if (-not $vCenterUser) { $vCenterUser = $env:vcenter_username }
if (-not $vCenterPassword -and $env:vcenter_password) {
    $vCenterPassword = ConvertTo-SecureString $env:vcenter_password -AsPlainText -Force
}

if (-not $vCenterServer -or -not $vCenterUser -or -not $vCenterPassword) {
    Write-Error "vCenter connection parameters not provided."
    exit 1
}

if (-not $UseExistingLibraryItem -and -not (Test-Path $ova)) {
    Write-Error "OVA file '$ova' not found."
    exit 1
}

try {
    $credential = New-Object System.Management.Automation.PSCredential ($vCenterUser, $vCenterPassword)
}
catch {
    Write-Error "Failed to create credential object: $_"
    exit 1
}

$PSDefaultParameterValues = @{
    "Connect-VIServer:Server"     = $vCenterServer
    "Connect-VIServer:Credential" = $credential
}

try {
    Connect-VIServer -ErrorAction Stop | Out-Null
}
catch {
    Write-Error "Failed to connect to vCenter Server '$vCenterServer': $_"
    exit 1
}

try {
    if ($UseExistingLibraryItem) {
        $ovaName = [System.IO.Path]::GetFileNameWithoutExtension($ova)
        $ovaFile = "$ovaName.ova"
        $sha1 = "library-item"
        $contentLibrary = Get-ContentLibrary -Name $library -ErrorAction Stop
        $importedItem = Get-ContentLibraryItem -ContentLibrary $contentLibrary -Name $ovaName -ErrorAction Stop
        $itemType = [string]$importedItem.ItemType
        if ($itemType -and $itemType -notmatch "(?i)^(ova|ovf)$") {
            throw "Content library item '$ovaName' has unsupported type '$itemType'."
        }
    }
    else {
    $ovaPath = (Resolve-Path $ova).Path
    $ovaFile = Split-Path -Path $ovaPath -Leaf
    $ovaName = $ovaFile -replace '\.ova$', ''

    $contentLibrary = Get-ContentLibrary -Name $library -ErrorAction Stop

    # Gate the upload on content, not on existence.  The OVA name is stable
    # across rebuilds (image_name is "<host>-base", with no version or
    # timestamp), so "an item exists" says nothing about whether it matches the
    # OVA just built -- but its recorded SHA1 does.  Same "<sha1>  <name>" note
    # format as import-ova-vsphere.ps1.
    $sha1 = (Get-FileHash -Algorithm SHA1 $ovaPath).Hash.ToLower()
    $expectedNotes = "$sha1  $ovaName"

    # Local record of what was last imported, used as a fallback in case vCenter
    # does not persist the -Notes value into the item's Description.  Keyed by
    # library name so the same OVA imported into two libraries is not confused.
    $markerPath = "$ovaPath.imported"
    $expectedMarker = "$sha1  $library"

    $existingItem = Get-ContentLibraryItem -ContentLibrary $contentLibrary -Name $ovaName -ErrorAction SilentlyContinue

    # PowerCLI surfaces the -Notes value as the item's Description; there is no
    # Notes property on ContentLibraryItem, so reading .Notes would always be
    # $null and force a needless re-upload every run.
    #
    # Match on the hash appearing anywhere in the description rather than on an
    # exact string equality, so that any whitespace or formatting normalisation
    # vCenter applies to the description does not defeat the check.
    $recordedNotes = if ($existingItem) { [string]$existingItem.Description } else { '' }
    $notesMatch = $recordedNotes -and ($recordedNotes -match [regex]::Escape($sha1))

    $markerMatch = $false
    if (Test-Path -LiteralPath $markerPath) {
        $markerContent = [string](Get-Content -LiteralPath $markerPath -Raw -ErrorAction SilentlyContinue)
        $markerMatch = ($markerContent.Trim() -eq $expectedMarker)
    }

    # Require the item to actually still be in the library.  A marker on its own
    # is not enough -- the item may have been removed out of band, in which case
    # the upload has to happen regardless of what was recorded locally.
    if ($existingItem -and ($notesMatch -or $markerMatch)) {
        Write-Host "Content library item '$ovaName' already matches this OVA (SHA1 $sha1); skipping upload."
        $importedItem = $existingItem
    }
    else {
        if ($existingItem) {
            # Logged at Host level: the Ansible task runs with no_log, so this is
            # only visible when the script is run directly, which is exactly when
            # you are trying to work out why it re-uploaded.
            Write-Host "Content library item '$ovaName' does not match this OVA; re-importing."
            Write-Host "  expected SHA1 : '$sha1'"
            Write-Host "  recorded notes: '$recordedNotes'"
            Remove-ContentLibraryItem -ContentLibraryItem $existingItem -Confirm:$false -ErrorAction Stop
        }

        # Splatted, as in import-ova-vsphere.ps1.  DisableOvfCertificateChecks is
        # a switch: writing "-DisableOvfCertificateChecks $true" would set the
        # switch and then try to bind $true positionally, which fails with "A
        # positional parameter cannot be found that accepts argument 'True'".
        # A hashtable binds switches correctly.
        $importParams = @{
            ContentLibrary              = $contentLibrary
            Name                        = $ovaName
            DisableOvfCertificateChecks = $true
            Files                       = $ovaPath
            ItemType                    = 'OVA'
            Notes                       = $expectedNotes
            Confirm                     = $false
        }

        $importedItem = New-ContentLibraryItem @importParams
    }

    # Record what is now in the library, so the next run can skip the upload even
    # if vCenter did not preserve the description.  Written on both paths so the
    # marker self-populates for items imported before this was added.  Failure to
    # write is not fatal -- it only costs one needless upload next time.
    Set-Content -LiteralPath $markerPath -Value $expectedMarker -NoNewline -ErrorAction SilentlyContinue

    }
    $folderObj = Get-Folder -Name $folder -ErrorAction Stop
    $vmHostObj = Get-VMHost | Where-Object {
        $_.ConnectionState -eq "Connected" -and -not $_.ExtensionData.Runtime.InMaintenanceMode
    } | Select-Object -First 1

    if (-not $vmHostObj) {
        throw "No connected ESXi host outside maintenance mode is available for template deployment."
    }

    # -DeletePermanently is required.  Without it Remove-Template only
    # unregisters the template from inventory and leaves its datastore folder
    # behind; vSphere then cannot reuse that folder name for the replacement and
    # appends _1, _2, ... instead.  That is what accumulates the
    # centos10s-base.tmpl_9 style directories on the datastore.
    $existingTemplate = Get-Template -Name $templateName -ErrorAction SilentlyContinue
    if ($existingTemplate) {
        Write-Verbose "Removing existing template '$templateName' and its datastore files."
        Remove-Template -Template $existingTemplate -DeletePermanently -Confirm:$false -ErrorAction Stop | Out-Null
    }

    # A run that died between New-VM and Set-VM -ToTemplate leaves a plain VM
    # holding the name and its datastore folder, which causes the same problem.
    $staleVM = Get-VM -Name $templateName -ErrorAction SilentlyContinue
    if ($staleVM) {
        Write-Verbose "Removing stale VM '$templateName' left by a previous run."
        Remove-VM -VM $staleVM -DeletePermanently -Confirm:$false -ErrorAction Stop | Out-Null
    }

    $vm = New-VM `
        -Name $templateName `
        -VMHost $vmHostObj `
        -ContentLibraryItem $importedItem `
        -ErrorAction Stop

    # Include a timestamp in local time so the template's Notes preserve when it was created.
    $createdAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    Set-VM -VM $vm -Notes "Template created from $ovaFile (SHA1 $sha1) at $createdAt" -Confirm:$false | Out-Null
    $template = Set-VM -VM $vm -ToTemplate -Name $templateName -Confirm:$false
    Move-Inventory -Item $template -Destination $folderObj -Confirm:$false | Out-Null

    Write-Host "Successfully created vSphere template '$templateName' in folder '$folder' from OVA '$ovaFile'."
}
catch {
    Write-Error "An error occurred during vSphere template creation: $_"
    exit 1
}
finally {
    try {
        Disconnect-VIServer -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    }
    catch {
        Write-Warning "Failed to disconnect from vCenter Server: $_"
    }
}
