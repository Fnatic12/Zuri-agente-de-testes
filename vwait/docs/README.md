# Documentacao VWAIT

Documentos principais do projeto:

- [ARCHITECTURE.md](/home/victor-milani/vwait-ia/vwait/docs/ARCHITECTURE.md)
- [README_TESTER.md](/home/victor-milani/vwait-ia/vwait/docs/README_TESTER.md)
- [JIRA_INTEGRATION.md](/home/victor-milani/vwait-ia/vwait/docs/JIRA_INTEGRATION.md)
- [DATA_LAYOUT.md](/home/victor-milani/vwait-ia/vwait/docs/DATA_LAYOUT.md)
- [FAILURES_REPORTING.md](/home/victor-milani/vwait-ia/vwait/docs/FAILURES_REPORTING.md)
- [ARCHITECTURE_VISUAL_QA.md](/home/victor-milani/vwait-ia/vwait/docs/ARCHITECTURE_VISUAL_QA.md)
- [PIXEL_VALIDATOR_MAP.md](/home/victor-milani/vwait-ia/vwait/docs/PIXEL_VALIDATOR_MAP.md)

## Estrutura consolidada

O projeto foi reorganizado para o modelo:

```text
src/vwait/core
src/vwait/platform
src/vwait/features
src/vwait/entrypoints
scripts
tests/{unit,integration,e2e}
tools
workspace
```

## Entradas oficiais

- Streamlit: `src/vwait/entrypoints/streamlit`
- CLI: `src/vwait/entrypoints/cli`
- Launchers operacionais: `scripts/linux` e `scripts/windows`

## Notas

- `HMI/tessdata` continua como recurso de OCR
- `tools` guarda utilitarios de apoio e dependencias locais
