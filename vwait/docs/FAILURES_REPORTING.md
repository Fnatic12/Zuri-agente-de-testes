# Failures Reporting

Os relatórios estruturados de falha agora pertencem ao módulo `failures`.

## Artefatos gerados

- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.json`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.md`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_report.csv`
- `workspace/reports/failures/<categoria>/<teste>/<timestamp>/failure_control.json`

## Fonte de dados

- `Data/runs/tester/<categoria>/<teste>/<run_id>/execucao_log.json`
- `Data/runs/tester/<categoria>/<teste>/<run_id>/test_meta.json` (opcional)
- `Data/runs/tester/<categoria>/<teste>/<run_id>/execution_context.json` (opcional)
- `Data/runs/tester/<categoria>/<teste>/<run_id>/status/<serial>.json` (opcional)
- `Data/catalog/tester/<categoria>/<teste>/expected/final.png`
- `Data/catalog/tester/<categoria>/<teste>/recorded/frames/*`

## Entry point CLI

Para regenerar todos os relatórios de falha:

```bash
python src/vwait/entrypoints/cli/generate_failure_reports.py
```
