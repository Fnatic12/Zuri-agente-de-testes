# Arquitetura VWAIT

Esta e a estrutura alvo consolidada do projeto apos a reestruturacao.

## Estrutura principal

```text
vwait/
  src/
    vwait/
      core/
      platform/
      features/
      entrypoints/
  scripts/
  tests/
    unit/
    integration/
    e2e/
  docs/
  requirements/
  tools/
  workspace/
```

## Responsabilidades

- `src/vwait/core`: configuracao, paths e recursos compartilhados de baixo acoplamento
- `src/vwait/platform`: integracoes tecnicas com SO, ADB e infraestrutura
- `src/vwait/features`: modulos de produto organizados por feature
- `src/vwait/entrypoints`: pontos de entrada oficiais CLI e Streamlit
- `scripts`: launchers operacionais para Linux e Windows
- `tests`: suites separadas por nivel
- `tools`: utilitarios de apoio e dependencias externas locais
- `workspace`: artefatos e relatorios gerados em runtime

## Features principais

- `chat`
- `tester`
- `execution`
- `logs`
- `failures`
- `hmi`
- `visual_qa`

## Convencoes

- nova logica de produto deve nascer em `src/vwait/features/...`
- novos pontos de entrada devem nascer em `src/vwait/entrypoints/...`
- scripts operacionais devem ficar em `scripts/...`
- utilitarios operacionais e dependencias locais devem ir para `tools/...`
- dados de runtime devem ficar em `workspace/...` quando fizer sentido

## Compatibilidade restante

- `HMI/tessdata` permanece como recurso de OCR
