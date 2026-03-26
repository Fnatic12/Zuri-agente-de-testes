# VWAIT para Testers

## Pacote

Entregue o projeto zipado sem o historico real de `Data/`.

Recomendado no pacote:
- manter `Data/` apenas com estrutura inicial e templates
- nao incluir capturas antigas, logs antigos nem datasets do ambiente de desenvolvimento

Cada tester vai gerar o proprio workspace em `Data/` apos descompactar o projeto.

## Instalacao

No Windows:

1. Extraia o `.zip`
2. Abra a pasta do projeto
3. Execute `Scripts\windows\setup_vwait.bat`
4. Depois execute `Scripts\windows\iniciar_vwait.bat`

## Dependencias externas

O setup instala as dependencias Python do runtime, mas o tester ainda precisa ter:
- Python 3.11+
- ADB (`adb.exe`)

Se o Python do Windows for removido, atualizado ou movido, a `.venv` pode ficar orfa.
Nesse caso, rode `Scripts\windows\setup_vwait.bat` novamente para o projeto recriar o ambiente.

O setup aceita ADB nestes formatos:
- `ADB_PATH` definido no Windows
- `adb.exe` no `PATH`
- `tools\platform-tools\adb.exe` dentro do projeto

## Operacao

- O launcher abre o `Menu Chat` e o `Menu Tester`
- As coletas e execucoes continuam sendo gravadas em `Data/`
- Para consolidar o trabalho de um tester, basta recolher a pasta `Data/`

## Observacao

Neste momento o projeto continua usando `Data/` dentro da raiz do repositorio como workspace local. Isso foi mantido de proposito para nao quebrar o fluxo atual do coletor, do runner e do dashboard.
