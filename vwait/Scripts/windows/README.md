# Windows Scripts

## Para testers

Use estes dois scripts:

- `setup_vwait.bat`
- `iniciar_vwait.bat`

Fluxo:

```bat
Scripts\windows\setup_vwait.bat
Scripts\windows\iniciar_vwait.bat
```

O setup:
- cria `.venv`
- recria `.venv` quebrada ou orfa quando o Python base do Windows mudou
- instala as dependencias do runtime
- valida o ADB

O launcher:
- sobe `Menu Chat` em `http://localhost:8502`
- sobe `Menu Tester` em `http://localhost:8503`
- repara o ambiente automaticamente antes de abrir, quando possivel

## Visual QA

Wrappers adicionais:

- `visual_qa_build_index.bat`
- `visual_qa_classify.bat`
- `visual_qa_validate.bat`

Exemplos:

```bat
Scripts\windows\visual_qa_build_index.bat
Scripts\windows\visual_qa_classify.bat C:\path\to\screenshot.png
Scripts\windows\visual_qa_validate.bat C:\path\to\screenshot.png
```

Todos os scripts preferem `.venv\Scripts\python.exe` quando disponivel.
