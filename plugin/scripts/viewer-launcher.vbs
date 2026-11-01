' Portable viewer launcher shipped inside the plugin package.
' Uses the bundled CPython; overrides: NEURON_PYTHON, NEURON_DB, NEURON_VIEWER_PORT.
' Skips starting a second instance when /api/health already answers.
' Usage: wscript viewer-launcher.vbs [/nobrowser]

Option Explicit
Dim fso, sh, env, pkg, home, py, db, port, up, http

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
Set env = sh.Environment("PROCESS")

pkg = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
home = pkg & "\python"

py = env("NEURON_PYTHON")
If py = "" Then
  If fso.FileExists(home & "\runtime\python.exe") Then
    py = home & "\runtime\python.exe"
  Else
    py = "python.exe"
  End If
End If

db = env("NEURON_DB")
If db = "" Then
  db = env("USERPROFILE") & "\.neuron-memory\neuron.db"
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
