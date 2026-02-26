' ============================================================
'  StockGuru Shortcut Creator — Location-Agnostic Version
'  Run this ONCE to put StockGuru on your Desktop!
' ============================================================

Dim shell, fso, scriptDir, desktop, shortcut
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

' --- Automatically detect the current folder ---
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktop   = shell.SpecialFolders("Desktop")

' --- Create the Shortcut ---
Set shortcut = shell.CreateShortcut(desktop & "\StockGuru Intelligence.lnk")

shortcut.TargetPath       = "wscript.exe"
shortcut.Arguments        = """" & scriptDir & "\StockGuru.vbs"""
shortcut.WorkingDirectory = scriptDir
shortcut.Description      = "Launch StockGuru Intelligence Hub"
shortcut.IconLocation     = "C:\Windows\System32\shell32.dll, 280" ' Chart/Monitor Icon

shortcut.Save()

MsgBox "✅ StockGuru Shortcut Created!" & Chr(13) & Chr(13) & _
       "Location: " & desktop & "\StockGuru Intelligence.lnk" & Chr(13) & Chr(13) & _
       "You can now double-click it anytime to start.", _
       64, "StockGuru Setup"

Set shell = Nothing
Set fso   = Nothing
