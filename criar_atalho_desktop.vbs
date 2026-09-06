' Cria o atalho "LOKI" na Area de Trabalho do usuario atual, apontando pra
' iniciar_loki_oculto.vbs NESTA MESMA PASTA - onde quer que o projeto tenha
' sido clonado (usa WshShell.SpecialFolders("Desktop"), que ja resolve
' certo mesmo com a Area de Trabalho redirecionada pro OneDrive). Roda uma
' vez so, depois de clonar o repositorio - da pra rodar de novo sem
' problema (so sobrescreve o atalho).

Set oWshShell = CreateObject("WScript.Shell")
Set oFso = CreateObject("Scripting.FileSystemObject")

strPastaAtual = oFso.GetParentFolderName(WScript.ScriptFullName)
strDesktop = oWshShell.SpecialFolders("Desktop")

Set oAtalho = oWshShell.CreateShortcut(strDesktop & "\LOKI.lnk")
oAtalho.TargetPath = strPastaAtual & "\iniciar_loki_oculto.vbs"
oAtalho.WorkingDirectory = strPastaAtual
oAtalho.Description = "Iniciar LOKI standalone (sem a GAIA)"

' So assume um icone proprio se existir um .ico de verdade - um .lnk nao
' renderiza .png de forma confiavel via IconLocation (mesmo padrao de
' criar_atalho_desktop.vbs do Project-IRIS). Hoje so existe assets\
' icone_loki.png (usado pela janela/bandeja em runtime, aceito direto pelo
' QIcon) - sem .ico ainda, o atalho fica com o icone genérico do Windows
' pra .vbs.
strIcone = strPastaAtual & "\assets\icone_loki.ico"
If oFso.FileExists(strIcone) Then
    oAtalho.IconLocation = strIcone
End If

oAtalho.Save

MsgBox "Atalho ""LOKI"" criado na sua Area de Trabalho!", vbInformation, "LOKI"
