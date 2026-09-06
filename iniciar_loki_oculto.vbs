' Lanca o iniciar_loki.bat com a janela do console totalmente escondida - o
' .bat em si ja sobe o processo real (mascot.process_main) escondido via
' pythonw, mas o CONSOLE DO PROPRIO .bat (cmd.exe processando o script)
' sempre aparece quando aberto direto (ex.: atalho da area de trabalho).
' Esse .vbs existe so pra esconder esse console tambem - mesmo padrao de
' iniciar_iris_oculto.vbs/iniciar_eris_oculto.vbs.
'
' Um atalho da area de trabalho pro LOKI deve apontar pra esse arquivo, nao
' pro .bat direto.
'
' Resolve o caminho da PROPRIA pasta em tempo de execucao - funciona em
' qualquer maquina/pasta onde o projeto for clonado, sem cravar caminho no
' codigo.

Set objShell = CreateObject("WScript.Shell")
Set oFso = CreateObject("Scripting.FileSystemObject")
strPastaAtual = oFso.GetParentFolderName(WScript.ScriptFullName)
objShell.Run """" & strPastaAtual & "\iniciar_loki.bat""", 0, False
