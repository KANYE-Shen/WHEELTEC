param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class SimulationWindows {
  public delegate bool EnumProc(IntPtr hwnd, IntPtr value);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc callback, IntPtr value);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int width, int height, uint flags);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct Rect { public int Left, Top, Right, Bottom; }
}
'@
[SimulationWindows]::SetProcessDPIAware() | Out-Null
$windows = [System.Collections.Generic.Dictionary[string,IntPtr]]::new()
$script:visibleWindowCount = 0
$callback = [SimulationWindows+EnumProc]{
  param($windowHandle, $value)
  if ([SimulationWindows]::IsWindowVisible($windowHandle)) {
    $script:visibleWindowCount++
    $title = [Text.StringBuilder]::new(512)
    [SimulationWindows]::GetWindowText($windowHandle, $title, $title.Capacity) | Out-Null
    $name = $title.ToString()
    if ($name -match '^Gazebo(?:\s|$)') { $windows['Gazebo'] = $windowHandle }
    if ($name -match '(?:^| - )RViz(?:\s|$)') { $windows['RViz'] = $windowHandle }
  }
  return $true
}
[SimulationWindows]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$results = @()
foreach ($name in @('Gazebo', 'RViz')) {
  if (-not $windows.ContainsKey($name)) { throw "No visible Windows window named $name; visible desktop windows: $script:visibleWindowCount" }
  $windowHandle = $windows[$name]
  $bounds = [SimulationWindows+Rect]::new()
  [SimulationWindows]::GetWindowRect($windowHandle, [ref]$bounds) | Out-Null
  $area = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $width = [Math]::Min($bounds.Right - $bounds.Left, $area.Width - 80)
  $height = [Math]::Min($bounds.Bottom - $bounds.Top, $area.Height - 80)
  [SimulationWindows]::SetWindowPos($windowHandle, [IntPtr]::Zero, $area.Left+40, $area.Top+40, $width, $height, 0x40) | Out-Null
  [SimulationWindows]::SetForegroundWindow($windowHandle) | Out-Null
  Start-Sleep -Milliseconds 900
  [SimulationWindows]::GetWindowRect($windowHandle, [ref]$bounds) | Out-Null
  $width = $bounds.Right - $bounds.Left
  $height = $bounds.Bottom - $bounds.Top
  $bitmap = [Drawing.Bitmap]::new($width, $height)
  $graphics = [Drawing.Graphics]::FromImage($bitmap)
  try {
    $hdc = $graphics.GetHdc()
    try { [SimulationWindows]::PrintWindow($windowHandle, $hdc, 2) | Out-Null }
    finally { $graphics.ReleaseHdc($hdc) }
    $colors = [Collections.Generic.HashSet[int]]::new()
    for ($x=20; $x -lt $width-20; $x+=43) {
      for ($y=60; $y -lt $height-20; $y+=43) { $colors.Add($bitmap.GetPixel($x,$y).ToArgb()) | Out-Null }
    }
    $method = 'PrintWindow'
    if ($colors.Count -lt 8) {
      $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bitmap.Size)
      $method = 'CopyFromScreen'
    }
    $path = Join-Path $OutputDirectory ($name.ToLowerInvariant() + '-windows.png')
    $bitmap.Save($path, [Drawing.Imaging.ImageFormat]::Png)
    $results += [pscustomobject]@{Title=$name;Path=$path;Method=$method;Width=$width;Height=$height}
  }
  finally { $graphics.Dispose(); $bitmap.Dispose() }
}
$results | ConvertTo-Json
