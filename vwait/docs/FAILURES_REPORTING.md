# Failures Reporting

Os relatórios estruturados de falha agora pertencem ao módulo `failures`.

## Artefatos gerados

- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.json`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.md`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.csv`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_control.json`

## Fonte de dados

- `Data/<categoria>/<teste>/execucao_log.json`
- `Data/<categoria>/<teste>/test_meta.json` (opcional)
- `Data/<categoria>/<teste>/execution_context.json` (opcional)
- `Data/<categoria>/<teste>/status_<serial>.json` (opcional)

## Entry point CLI

Para regenerar todos os relatórios de falha:

```bash
python src/vwait/entrypoints/cli/generate_failure_reports.py
```

## Automação legada de ticket KPM

O script antigo de automação Selenium foi movido para:

```text
tools/legacy/abrir_kpm.py
```

Ele permanece fora do fluxo principal e deve ser tratado como utilitário legado.
