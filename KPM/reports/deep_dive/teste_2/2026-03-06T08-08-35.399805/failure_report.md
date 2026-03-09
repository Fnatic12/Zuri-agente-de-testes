# Failure Report - deep_dive/teste_2

Generated at: 2026-03-06T08:08:35.399805

## Precondition
Teste automatizado `deep_dive/teste_2` iniciado em bancada `desconhecido` com dataset previamente gravado e baseline visual disponivel.

## Short text
DEEP_DIVE - falha visual na acao 4 (tap) do teste teste_2 com similaridade 0.81

## Operation steps
- Acao 1: tap em (952, 1013)
- Acao 2: tap em (696, 1021)
- Acao 3: tap em (1665, 701)
- Acao 4: tap em (736, 482)
- Acao 5: tap em (624, 841)
- Acao 6: tap em (298, 645)
- Acao 7: tap em (314, 569)

## Actual Results
Acao 4 retornou '❌ Divergente' com similaridade 0.810. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\resultados\resultado_04.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\frames\frame_04.png.
Acao 5 retornou '❌ Divergente' com similaridade 0.821. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\resultados\resultado_05.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\frames\frame_05.png.
Acao 6 retornou '❌ Divergente' com similaridade 0.805. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\resultados\resultado_06.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\frames\frame_06.png.
Acao 7 retornou '❌ Divergente' com similaridade 0.822. Screenshot atual: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\resultados\resultado_07.png | esperado: C:\Users\Automation01\Desktop\zuri_agente\Data\deep_dive\teste_2\frames\frame_07.png.

## Occurrence Rate
1/1 execucao falhou

## Recovery Conditions
Nenhuma rotina formal de recuperacao registrada. A execucao seguiu apos detectar a divergencia.

## Bug Occurrence Time
Timestamp: 2026-02-24T11:00:54.353328
Elapsed from start: 12.79s

## Version Information
- adb_serial: desconhecido
- device_name: nao coletado
- system_build: nao coletado
- sw_version: nao coletado
- hw_version: nao coletado
- app_version: nao coletado

## Failed Steps
- Action 4 | tap | similarity=0.810 | ❌ Divergente
- Action 5 | tap | similarity=0.821 | ❌ Divergente
- Action 6 | tap | similarity=0.805 | ❌ Divergente
- Action 7 | tap | similarity=0.822 | ❌ Divergente
