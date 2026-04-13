# Data Layout

O workspace `Data/` agora é organizado por intenção:

```text
Data/
  catalog/
    tester/
      <categoria>/
        <teste>/
          test.json
          dataset.csv
          expected/
            final.png
          recorded/
            actions.json
            frames/
    hmi/
      captures/
        HMI_TESTE/

  runs/
    tester/
      <categoria>/
        <teste>/
          <run_id>/
            execucao_log.json
            status/
              <serial>.json
            logs/
            artifacts/
              results/
            reports/

  cache/
    hmi/

  templates/
    log_capture_sequence_template.csv

  system/
    coleta_live.log
    execucao_live.log
    execucao_live_<serial>.log
    failure_log_sequence.csv
    failure_log_sequence.raw.json
    failure_log_sequence.meta.json
```

## Regras

- `catalog/`: definição permanente do teste gravado.
- `runs/`: artefatos de uma execução específica.
- `cache/`: material temporário e descartável.
- `templates/`: modelos reutilizáveis.
- `system/`: logs e arquivos globais da aplicação.

## Convenção do tester

- `catalog/tester/<categoria>/<teste>/recorded/actions.json`
  Ações gravadas no coletor.
- `catalog/tester/<categoria>/<teste>/recorded/frames/`
  Frames base por ação.
- `catalog/tester/<categoria>/<teste>/expected/final.png`
  Tela final esperada.
- `runs/tester/<categoria>/<teste>/<run_id>/`
  Saída completa de uma execução.

## Compatibilidade

O código atual já usa este layout como padrão. Leituras legadas ainda têm fallback em alguns pontos para não quebrar fixtures e artefatos antigos, mas novos dados devem nascer apenas neste formato.
