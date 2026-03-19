Set WshShell = CreateObject("WScript.Shell")
strPath = Wscript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objFile = objFSO.GetFile(strPath)
strFolder = objFSO.GetParentFolderName(objFile)

' Change directory to the script folder
WshShell.CurrentDirectory = strFolder

' Run START.bat with normal window (1) so logs and bugs are visible
' (Use 0 to hide completely, 7 to run minimized)
WshShell.Run "cmd /c START.bat", 1, False

Set WshShell = Nothing
