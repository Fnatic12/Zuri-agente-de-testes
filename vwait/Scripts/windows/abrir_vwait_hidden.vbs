Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))
launcher = fso.BuildPath(scriptDir, "iniciar_vwait.bat")
shell.CurrentDirectory = projectRoot
shell.Run "cmd.exe /c """ & launcher & """", 0, False
