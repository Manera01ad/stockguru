' ============================================================
'  StockGuru Launcher — Ultra-Robust Version
'  This script automatically finds and runs START.bat
' ============================================================

Dim shell, fso, scriptDir, batPath
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

' --- Automatically detect the folder ---
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath   = scriptDir & "\START.bat"

' --- Run the START.bat file ---
' Quoting the path correctly for folders with spaces
shell.Run """" & batPath & """", 1, False

Set shell = Nothing
Set fso   = Nothing
