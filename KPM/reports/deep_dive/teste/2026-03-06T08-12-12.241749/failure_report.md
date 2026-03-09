# Failure Report - deep_dive/teste

Generated at: 2026-03-06T08:12:12.241749

## Precondition
Teste automatizado `deep_dive/teste` iniciado em bancada `desconhecido` com dataset previamente gravado e baseline visual disponivel.

## Short text
DEEP_DIVE - falha visual na acao 3 (tap) do teste teste com similaridade 0.72

## Operation steps
- Acao 1: tap em (997, 1047)
- Acao 2: tap em (696, 1023)
- Acao 3: tap em (1677, 707)
- Acao 4: swipe_inicio em (1383, 595)
- Acao 6: tap em (1165, 416)
- Acao 7: swipe_inicio em (288, 448)
- Acao 9: swipe_inicio em (284, 412)
- Acao 11: tap em (650, 298)
- Acao 12: tap em (214, 845)
- Acao 13: swipe_inicio em (246, 831)
- Acao 15: tap em (218, 751)
- Acao 16: tap em (224, 867)

## Actual Results
Acao 3 retornou '❌ Divergente' com similaridade 0.717. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\resultados\resultado_03.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\frames\frame_03.png.
Acao 15 retornou '❌ Divergente' com similaridade 0.831. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\resultados\resultado_11.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\frames\frame_11.png.
Acao 16 retornou '❌ Divergente' com similaridade 0.803. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\resultados\resultado_12.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste\frames\frame_12.png.

## Occurrence Rate
1/1 execucao falhou

## Recovery Conditions
Nenhuma rotina formal de recuperacao registrada. A execucao seguiu apos detectar a divergencia.

## Bug Occurrence Time
Timestamp: 2026-02-23T16:27:36.137138
Elapsed from start: 9.16s

## Version Information
- adb_serial: desconhecido
- device_name: nao coletado
- system_build: nao coletado
- sw_version: nao coletado
- hw_version: nao coletado
- app_version: nao coletado

## Failed Steps
- Action 3 | tap | similarity=0.717 | ❌ Divergente
- Action 15 | tap | similarity=0.831 | ❌ Divergente
- Action 16 | tap | similarity=0.803 | ❌ Divergente
