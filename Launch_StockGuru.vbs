Set WshShell = CreateObject("WScript.Shell")
strPath = Wscript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objFile = objFSO.GetFile(strPath)
strFolder = objFSO.GetParentFolderName(objFile)

' Change directory to the script folder
WshShell.CurrentDirectory = strFolder

' Run START.bat with window hidden (0)
' This runs the server in the background and opens the browser automatically
WshShell.Run "cmd /c START.bat", 0, False

Set WshShell = Nothing
