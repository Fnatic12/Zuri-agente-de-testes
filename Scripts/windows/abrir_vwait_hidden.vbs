Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))
pythonw = fso.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe")
launcher = fso.BuildPath(scriptDir, "start_vwait_apps.py")
shell.Run """" & pythonw & """ """ & launcher & """", 0, False
