param(
    [Parameter(Mandatory = $true)][string]$SpecFile,
    [Parameter(Mandatory = $true)][string]$OutFile
)

$ErrorActionPreference = "Stop"

function Write-Payload([string]$Json) {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($OutFile, $Json, $utf8)
}

function Get-Rect($el) {
    try {
        $r = $el.Current.BoundingRectangle
        if ([double]::IsNaN($r.X) -or [double]::IsInfinity($r.X)) { return @(0, 0, 0, 0) }
        return @([int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
    }
    catch {
        return @(0, 0, 0, 0)
    }
}

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type -AssemblyName WindowsBase
    Add-Type -ErrorAction SilentlyContinue @"
using System;
using System.Runtime.InteropServices;
public class Win32Oacu {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

    $spec = Get-Content -Raw -Encoding UTF8 $SpecFile | ConvertFrom-Json
    $match = $spec.match
    $op = [string]$spec.op

    if ($op -eq "focused_set_value") {
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        $hwnd = 0
        if ($null -ne $focused) {
            try { $hwnd = [int]$focused.Current.NativeWindowHandle } catch { $hwnd = 0 }
            $pattern = $null
            if ($focused.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                $pattern.SetValue([string]$spec.value)
                Write-Payload (@{ ok = $true; method = "FocusedValuePattern"; hwnd = $hwnd } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable"; hwnd = $hwnd } | ConvertTo-Json -Compress)
        exit 0
    }

    if ($op -eq "set_value_point") {
        $p = $spec.point
        try {
            $point = [System.Windows.Point]::new([double]$p[0], [double]$p[1])
            $element = [System.Windows.Automation.AutomationElement]::FromPoint($point)
            if ($null -ne $element) {
                $hwnd = 0
                try { $hwnd = [int]$element.Current.NativeWindowHandle } catch { $hwnd = 0 }
                $pattern = $null
                if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                    $pattern.SetValue([string]$spec.value)
                    Write-Payload (@{ ok = $true; method = "PointValuePattern"; hwnd = $hwnd } | ConvertTo-Json -Compress)
                    exit 0
                }
                Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable"; hwnd = $hwnd } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        catch { }
        Write-Payload (@{ ok = $false; error = "element_not_found"; code = "element_not_found" } | ConvertTo-Json -Compress)
        exit 0
    }

    if ($op -eq "focus_point") {
        $p = $spec.point
        try {
            $point = [System.Windows.Point]::new([double]$p[0], [double]$p[1])
            $element = [System.Windows.Automation.AutomationElement]::FromPoint($point)
            if ($null -ne $element) {
                $element.SetFocus()
                $hwnd = 0
                try { $hwnd = [int]$element.Current.NativeWindowHandle } catch { $hwnd = 0 }
                $invoked = $false
                $pattern = $null
                try {
                    if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
                        $pattern.Invoke()
                        $invoked = $true
                    }
                    elseif ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
                        $pattern.Select()
                        $invoked = $true
                    }
                    elseif ($element.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern, [ref]$pattern)) {
                        $pattern.DoDefaultAction()
                        $invoked = $true
                    }
                }
                catch { }
                Write-Payload (@{ ok = $true; method = "FromPoint+SetFocus"; hwnd = $hwnd; invoked = $invoked } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        catch { }
        Write-Payload (@{ ok = $false; error = "element_not_found"; code = "element_not_found" } | ConvertTo-Json -Compress)
        exit 0
    }

    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

    $wantName = ""
    $wantType = ""
    $wantAid = ""
    $wantRect = @(0, 0, 0, 0)
    if ($match) {
        $wantName = [string]$match.name
        $wantType = [string]$match.control_type
        $wantAid = [string]$match.automation_id
        if ($match.rect) { $wantRect = @([int]$match.rect[0], [int]$match.rect[1], [int]$match.rect[2], [int]$match.rect[3]) }
    }

    $script:best = $null
    $script:bestScore = 0
    $script:seen = 0

    function Score-Element($el) {
        $score = 0
        $identity = $false
        try {
            $name = [string]$el.Current.Name
            $aid = [string]$el.Current.AutomationId
            $ct = [string]$el.Current.ControlType.ProgrammaticName
            if ($ct.StartsWith("ControlType.")) { $ct = $ct.Substring(12) }
        }
        catch {
            return 0
        }
        if ($wantAid -ne "" -and $aid -eq $wantAid) { $score += 100; $identity = $true }
        if ($wantName -ne "") {
            if ($name -eq $wantName) { $score += 60; $identity = $true }
            elseif ($name.StartsWith($wantName)) { $score += 35; $identity = $true }
            elseif ($name -like "*$wantName*") { $score += 25; $identity = $true }
        }
        if (-not $identity -and ($wantName -ne "" -or $wantAid -ne "")) { return 0 }
        if ($wantType -ne "" -and $ct -eq $wantType) { $score += 10 }
        if ($wantRect[2] -gt 0) {
            $r = Get-Rect $el
            if ($r[2] -gt 0) {
                $dx = [math]::Abs(($r[0] + [int]($r[2] / 2)) - ($wantRect[0] + [int]($wantRect[2] / 2)))
                $dy = [math]::Abs(($r[1] + [int]($r[3] / 2)) - ($wantRect[1] + [int]($wantRect[3] / 2)))
                $dist = $dx + $dy
                if ($dist -le 50) { $score += 20 }
                elseif ($dist -le 200) { $score += 5 }
            }
        }
        return $score
    }

    function Visit($el, [int]$depth) {
        if ($script:seen -ge 2500) { return }
        $script:seen++
        $score = Score-Element $el
        if ($score -gt $script:bestScore) {
            $script:bestScore = $score
            $script:best = $el
        }
        if ($depth -ge 15) { return }
        try {
            $child = $walker.GetFirstChild($el)
            while ($null -ne $child) {
                Visit $child ($depth + 1)
                if ($script:seen -ge 2500) { return }
                $child = $walker.GetNextSibling($child)
            }
        }
        catch { return }
    }

    $top = $walker.GetFirstChild($root)
    while ($null -ne $top) {
        Visit $top 0
        $top = $walker.GetNextSibling($top)
    }

    if ($null -eq $script:best -or $script:bestScore -lt 20) {
        Write-Payload (@{ ok = $false; error = "element_not_found"; code = "element_not_found"; seen = $script:seen } | ConvertTo-Json -Compress)
        exit 0
    }

    $el = $script:best
    $method = ""
    $value = $spec.value
    $direction = [string]$spec.direction
    $times = 1
    if ($spec.times) { $times = [int]$spec.times }
    if ($times -lt 1) { $times = 1 }

    switch ($op) {
        "click" {
            $done = $false
            $method = ""
            $pattern = $null
            foreach ($candidate in @(
                    @{ Pattern = [System.Windows.Automation.InvokePattern]::Pattern; Action = "Invoke" },
                    @{ Pattern = [System.Windows.Automation.SelectionItemPattern]::Pattern; Action = "Select" },
                    @{ Pattern = [System.Windows.Automation.ExpandCollapsePattern]::Pattern; Action = "Expand" },
                    @{ Pattern = [System.Windows.Automation.TogglePattern]::Pattern; Action = "Toggle" },
                    @{ Pattern = [System.Windows.Automation.LegacyIAccessiblePattern]::Pattern; Action = "DoDefaultAction" }
                )) {
                if ($done) { break }
                $pattern = $null
                try {
                    if ($el.TryGetCurrentPattern($candidate.Pattern, [ref]$pattern)) {
                        switch ($candidate.Action) {
                            "Invoke" { $pattern.Invoke() }
                            "Select" { $pattern.Select() }
                            "Expand" { $pattern.Expand() }
                            "Toggle" { $pattern.Toggle() }
                            "DoDefaultAction" { $pattern.DoDefaultAction() }
                        }
                        $done = $true
                        $method = $candidate.Action
                    }
                }
                catch { }
            }
            if (-not $done) {
                Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable" } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        "invoke" {
            $pattern = $null
            if ($el.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
                $pattern.Invoke()
                $method = "InvokePattern"
            }
            else {
                Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable" } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        "set_value" {
            $pattern = $null
            if ($el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                $pattern.SetValue([string]$value)
                $method = "ValuePattern"
            }
            else {
                Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable" } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        "scroll" {
            $pattern = $null
            if ($el.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$pattern)) {
                $h = [System.Windows.Automation.ScrollAmount]::NoAmount
                $v = [System.Windows.Automation.ScrollAmount]::NoAmount
                if ($direction -eq "up" -or $direction -eq "down") {
                    $v = [System.Windows.Automation.ScrollAmount]::SmallIncrement
                }
                else {
                    $h = [System.Windows.Automation.ScrollAmount]::SmallIncrement
                }
                for ($i = 0; $i -lt $times; $i++) { $pattern.Scroll($h, $v) }
                $method = "ScrollPattern"
            }
            else {
                Write-Payload (@{ ok = $false; error = "pattern_unavailable"; code = "pattern_unavailable" } | ConvertTo-Json -Compress)
                exit 0
            }
        }
        "activate" {
            $el.SetFocus()
            try {
                $hwnd = [IntPtr]$el.Current.NativeWindowHandle
                if ($hwnd -ne [IntPtr]::Zero) { [Win32Oacu]::SetForegroundWindow($hwnd) | Out-Null }
            }
            catch { }
            $method = "SetFocus+Foreground"
        }
        default {
            Write-Payload (@{ ok = $false; error = "unsupported_op"; code = "unsupported_op" } | ConvertTo-Json -Compress)
            exit 0
        }
    }

    $matchedType = [string]$el.Current.ControlType.ProgrammaticName
    if ($matchedType.StartsWith("ControlType.")) { $matchedType = $matchedType.Substring(12) }
    $matched = @{
        name          = [string]$el.Current.Name
        control_type  = $matchedType
        automation_id = [string]$el.Current.AutomationId
        score         = $script:bestScore
    }
    Write-Payload (@{ ok = $true; method = $method; matched = $matched } | ConvertTo-Json -Depth 4 -Compress)
}
catch {
    Write-Payload (@{ ok = $false; error = [string]$_.Exception.Message; code = "ps_error" } | ConvertTo-Json -Compress)
    exit 1
}
