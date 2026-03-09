# KPM Failure Reporting

Esta pasta concentra a geracao de relatorios estruturados de falha a partir da execucao automatizada.

## Artefatos gerados

- `KPM/reports/<categoria>/<teste>/<timestamp>/failure_report.json`
- `KPM/reports/<categoria>/<teste>/<timestamp>/failure_report.md`
- `KPM/reports/<categoria>/<teste>/<timestamp>/failure_report.csv`

## Fonte de dados atual

- `Data/<categoria>/<teste>/execucao_log.json`
- `Data/<categoria>/<teste>/test_meta.json` (opcional)
- `Data/<categoria>/<teste>/execution_context.json` (opcional)
- `Data/<categoria>/<teste>/status_<serial>.json` (opcional)

## Campos do relatorio

- `precondition`
- `short_text`
- `operation_steps`
- `actual_results`
- `occurrence_rate`
- `recovery_conditions`
- `bug_occurrence_time`
- `version_information`

## Proximo passo recomendado

Enriquecer o runner para sempre gerar `execution_context.json` e `test_meta.json`.
