param(
    [int]$MaxDepth = 12,
    [int]$MaxElements = 3000,
    [int]$TimeBudgetMs = 8000,
    [string]$Window = "",
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

function Write-Payload([string]$Json) {
    if ($OutFile) {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutFile, $Json, $utf8)
    }
    else {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        Write-Output $Json
    }
}

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes

    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $script:items = New-Object System.Collections.ArrayList
    $script:limit = $MaxElements
    $script:started = [Environment]::TickCount
    $script:timeout = $false

    function Get-Rect($el) {
        try {
            $r = $el.Current.BoundingRectangle
            if ([double]::IsNaN($r.X) -or [double]::IsInfinity($r.X) -or [double]::IsNaN($r.Width)) {
                return @(0, 0, 0, 0)
            }
            return @([int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
        }
        catch {
            return @(0, 0, 0, 0)
        }
    }

    function Add-Element($el, [int]$depth, [int]$parentIndex) {
        if ($script:timeout) { return }
        if ($script:items.Count -ge $script:limit) { return }
        if (([Environment]::TickCount - $script:started) -gt $TimeBudgetMs) {
            $script:timeout = $true
            return
        }
        $name = ""
        $ct = ""
        $aid = ""
        $cls = ""
        $enabled = $true
        $offscreen = $false
        try {
            $name = [string]$el.Current.Name
            $ct = [string]$el.Current.ControlType.ProgrammaticName
            if ($ct.StartsWith("ControlType.")) { $ct = $ct.Substring(12) }
            $aid = [string]$el.Current.AutomationId
            $cls = [string]$el.Current.ClassName
            $enabled = [bool]$el.Current.IsEnabled
            $offscreen = [bool]$el.Current.IsOffscreen
        }
        catch {
            return
        }
        $rect = Get-Rect $el
        $idx = $script:items.Count
        $null = $script:items.Add([pscustomobject]@{
                name          = $name
                control_type  = $ct
                rect          = $rect
                automation_id = $aid
                class_name    = $cls
                parent        = $parentIndex
                depth         = $depth
                enabled       = $enabled
                offscreen     = $offscreen
            })
        if ($depth -ge $MaxDepth) { return }
        try {
            $child = $walker.GetFirstChild($el)
            while ($null -ne $child) {
                Add-Element $child ($depth + 1) $idx
                if ($script:timeout) { break }
                if ($script:items.Count -ge $script:limit) { break }
                $child = $walker.GetNextSibling($child)
            }
        }
        catch {
            return
        }
    }

    $top = $walker.GetFirstChild($root)
    while ($null -ne $top) {
        $topName = ""
        try { $topName = [string]$top.Current.Name } catch { $topName = "" }
        $matched = $true
        if ($Window -ne "") {
            $matched = $topName -like "*$Window*"
        }
        if ($matched) {
            Add-Element $top 0 -1
        }
        if ($script:timeout) { break }
        if ($script:items.Count -ge $script:limit) { break }
        $top = $walker.GetNextSibling($top)
    }

    $screenRect = Get-Rect $root
    $psVersion = $PSVersionTable.PSVersion.ToString()
    $payload = [pscustomobject]@{
        ok       = $true
        backend  = "ps"
        ps       = $psVersion
        screen   = @($screenRect[2], $screenRect[3])
        count     = $script:items.Count
        truncated = (($script:items.Count -ge $script:limit) -or $script:timeout)
        timeout   = [bool]$script:timeout
        elements  = $script:items
    }
    Write-Payload ($payload | ConvertTo-Json -Depth 8 -Compress)
}
catch {
    $payload = [pscustomobject]@{
        ok      = $false
        backend = "ps"
        error   = [string]$_.Exception.Message
    }
    Write-Payload ($payload | ConvertTo-Json -Depth 4 -Compress)
    exit 1
}
