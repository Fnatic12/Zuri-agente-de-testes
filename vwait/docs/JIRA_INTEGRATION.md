# Jira Integration

## Objetivo

Esta integracao cria uma camada simples e reutilizavel para:

- validar conexao com Jira Cloud
- listar tipos de issue do projeto
- criar issues a partir do painel
- anexar artefatos locais ao card

## Configuracao

1. Copie [.env.jira.example](/home/victor-milani/vwait-ia/vwait/.env.jira.example) para `.env.jira`
2. Preencha os dados reais do seu workspace
3. Nao commite `.env.jira`

Variaveis suportadas:

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY`
- `JIRA_ISSUE_TYPE`
- `JIRA_DEFAULT_LABELS`
- `JIRA_TIMEOUT_S`
- `JIRA_VERIFY_SSL`

## Estrutura de codigo

- [config.py](/home/victor-milani/vwait-ia/vwait/app/integrations/jira/config.py): leitura e validacao de configuracao
- [client.py](/home/victor-milani/vwait-ia/vwait/app/integrations/jira/client.py): chamadas REST ao Jira
- [service.py](/home/victor-milani/vwait-ia/vwait/app/integrations/jira/service.py): regras de uso pela aplicacao
- [models.py](/home/victor-milani/vwait-ia/vwait/app/integrations/jira/models.py): contratos internos

## Uso esperado

O fluxo atual fica no painel `Controle de Falhas`.

Uso esperado:

1. carregar `JiraService.from_env()`
2. testar a conexao com `test_connection()`
3. abrir uma falha no modal de edicao
4. montar um `JiraIssueDraft`
5. chamar `create_issue()`

## Seguranca

- use sempre token novo quando houver exposicao acidental
- mantenha o token apenas em `.env.jira` ou nas variaveis do ambiente
- nunca envie o token para o frontend
