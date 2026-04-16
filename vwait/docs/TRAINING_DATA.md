# TrainingData

`TrainingData/` e uma saida opcional da coleta do Menu Tester para preparar episodios de aprendizado supervisionado.

`Data/` continua sendo a estrutura operacional da plataforma. A exportacao supervisionada nao altera a semantica da `Data/`; ela apenas cria uma copia organizada dos artefatos relevantes em `TrainingData/`.

## Como usar

No Menu Tester, em `Exportacao supervisionada (TrainingData)`:

1. Marque `Salvar tambem para TrainingData`.
2. Preencha `Categoria/DOMINIO`.
3. Preencha `Fluxo/Caso de teste`.
4. Preencha `Objetivo do episodio`.
5. Preencha `Criterio de sucesso final`.
6. Opcionalmente informe intencao e resultado esperado por passo, uma linha por passo.

Se o checkbox nao estiver marcado, a coleta normal continua exatamente como antes.

## Exemplos de preenchimento

`Salvar tambem para TrainingData`

Marque quando esta coleta tambem deve virar um episodio para treino supervisionado. Exemplo de uso: gravar normalmente em `Data/` e, ao mesmo tempo, criar uma copia estruturada em `TrainingData/` para ensinar um agente no futuro.

`Categoria/DOMINIO`

Use o dominio funcional do radio que esta sendo testado. Exemplos: `tuner`, `bluetooth`, `audio`, `navigation`, `camera`.

`Fluxo/Caso de teste`

Use o nome do fluxo que o agente devera aprender a executar. Exemplos: `validar_funcoes_padrao_do_tuner`, `parear_dispositivo_bluetooth`, `ajustar_volume`.

`Objetivo do episodio`

Descreva o objetivo em linguagem natural, como se fosse o prompt futuro para o agente. Exemplo: `Validar se o Tuner abre corretamente, troca de estacao e mantem a tela principal funcional.`

`Criterio de sucesso final`

Descreva como saber que o episodio terminou corretamente. Exemplo: `O radio deve estar na tela do Tuner, sem erro visual, com estacao/frequencia visivel e botoes respondendo.`

`Intencao por passo`

Opcional. Escreva uma linha por toque/gesto, na mesma ordem da coleta. Exemplo:

```text
Abrir o menu principal
Entrar na tela do Tuner
Selecionar proxima estacao
Voltar para a tela anterior
```

`Resultado esperado por passo`

Opcional. Escreva uma linha por toque/gesto, alinhada com a intencao correspondente. Exemplo:

```text
Menu principal aparece na tela
Tela do Tuner e exibida
Frequencia muda para a proxima estacao
Tela anterior e exibida sem falhas
```

`Observacoes`

Opcional. Use para contexto extra da coleta. Exemplo: `Teste gravado com radio em portugues, tema escuro, sem rede conectada e volume em 10.`

Se intencao ou resultado esperado por passo ficarem vazios, o VWAIT cria fallbacks automaticamente, como `fallback_step_1` e `state_changed_after_step_1`.

## Estrutura

```text
TrainingData/
  taxonomy/
    categories.json
    flows.json
  episodes/
    <categoria>/
      <fluxo>/
        <episode_id>/
          episode.json
          environment.json
          summary.json
          source_refs.json
          final_expected.png
          steps/
            0001/
              step.json
              before.png
              after.png
  manifests/
    all_episodes.jsonl
```

## Arquivos principais

`episode.json` identifica o episodio, categoria, fluxo, objetivo, criterio de sucesso final, tester e quantidade de passos.

`environment.json` guarda metadados automaticos do ambiente, como device, fonte de input, versao do sistema, build e resolucao.

`summary.json` guarda status da exportacao, duracao aproximada, quantidade de passos e se houve anotacao manual por passo.

`source_refs.json` mantem rastreabilidade com a origem operacional em `Data/`.

`steps/<NNNN>/step.json` guarda intencao, resultado esperado, timestamps e referencia da acao gravada. Se a intencao ou resultado esperado nao forem preenchidos, o sistema usa fallbacks como `fallback_step_1` e `state_changed_after_step_1`.

`manifests/all_episodes.jsonl` indexa todos os episodios exportados.

`taxonomy/categories.json` e `taxonomy/flows.json` registram categorias e fluxos vistos na UI, sem duplicar entradas.
