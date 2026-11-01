' Portable neuron-memory viewer launcher (project layout).
' Paths derived from this script; overrides: NEURON_HOME, NEURON_PYTHON,
' NEURON_DB, NEURON_VIEWER_PORT. Skips a second instance when health answers.
' Usage: wscript open-viewer.vbs [/nobrowser]

Option Explicit
Dim fso, sh, env, scripts, root, home, py, db, port, up, http

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
Set env = sh.Environment("PROCESS")

scripts = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scripts)

home = env("NEURON_HOME")
If home = "" Then
  If fso.FileExists(root & "\plugin\python\neuron_memory\__init__.py") Then
    home = root & "\plugin\python"
  Else
    home = root
  End If
End If

py = env("NEURON_PYTHON")
If py = "" Then
  If fso.FileExists(root & "\.venv\Scripts\python.exe") Then
    py = root & "\.venv\Scripts\python.exe"
  ElseIf fso.FileExists(home & "\runtime\python.exe") Then
    py = home & "\runtime\python.exe"
  Else
    py = "python.exe"
  End If
End If

db = env("NEURON_DB")
If db = "" Then
  If fso.FileExists(fso.GetParentFolderName(root) & "\.neuron-memory\neuron.db") Then
    db = fso.GetParentFolderName(root) & "\.neuron-memory\neuron.db"
  Else
    db = env("USERPROFILE") & "\.neuron-memory\neuron.db"
  End If
End If

port = env("NEURON_VIEWER_PORT")
If port = "" Then port = "8420"

up = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP")
http.Open "GET", "http://127.0.0.1:" & port & "/api/health", False
http.Send
If http.Status = 200 Then up = True
On Error GoTo 0

If Not up Then
  sh.CurrentDirectory = home
  sh.Run """" & py & """ -m viewer.server --db """ & db & """ --port " & port, 0, False
  WScript.Sleep 2500
End If

If Not WScript.Arguments.Named.Exists("nobrowser") Then
  sh.Run "http://127.0.0.1:" & port & "/", 1, False
End If
