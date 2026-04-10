# VWAIT para Testers

Guia rapido para instalar, abrir e usar o VWAIT em um ambiente novo.

Este README foi pensado para quem vai receber o projeto pela primeira vez e precisa saber exatamente:
- o que instalar
- quais scripts executar
- quais telas vao abrir
- onde ficam os dados gerados

## O que e o VWAIT

O VWAIT abre um conjunto de paineis para execucao e analise de testes:
- `Menu Chat`
- `Menu Tester`
- `Dashboard`
- `Painel de Logs`
- `Controle de Falhas`
- `Validação HMI`

Os dois paineis principais que abrem automaticamente sao:
- `http://localhost:8502` para o `Menu Chat`
- `http://localhost:8503` para o `Menu Tester`

Os paineis auxiliares rodam nestas portas:
- `http://localhost:8504` para o `Dashboard`
- `http://localhost:8505` para o `Painel de Logs`
- `http://localhost:8506` para o `Controle de Falhas`

## Antes de entregar o pacote para outro tester

Ao gerar o `.zip` do projeto:
- mantenha `Data/` apenas com estrutura inicial e templates
- nao envie historico real de capturas, logs ou datasets internos
- nao envie artefatos desnecessarios do ambiente de desenvolvimento

Cada tester vai gerar o proprio workspace local dentro de `Data/`.

## Requisitos

Para rodar o projeto, a maquina precisa ter:
- Python `3.11+`
- `ADB` disponivel

O ADB pode estar em qualquer um destes formatos:
- variavel de ambiente `ADB_PATH`
- `adb.exe` ou `adb` no `PATH`
- `tools/platform-tools/adb.exe` no Windows
- `tools/platform-tools/adb` no Linux

## Instalacao no Windows

Este e o fluxo recomendado para testers.

### Passo a passo

1. Extraia o `.zip` do projeto.
2. Abra a pasta raiz do projeto.
3. Execute `Scripts\windows\setup_vwait.bat`.
4. Depois execute `Scripts\windows\iniciar_vwait.bat`.

### O que o setup faz

O script `setup_vwait.bat`:
- cria a `.venv`
- recria a `.venv` se ela estiver quebrada ou orfa
- instala as dependencias do runtime
- valida os imports principais
- valida o ADB
- atualiza o arquivo `.env.tester`

### O que o launcher faz

O script `iniciar_vwait.bat`:
- verifica se a `.venv` esta pronta
- tenta reparar o ambiente automaticamente se precisar
- sobe os apps Streamlit nas portas do projeto
- abre o navegador nas telas principais

## Instalacao no Linux

Se o projeto ja vier com a `.venv` pronta, use diretamente o launcher:

```bash
Scripts/linux/iniciar_vwait.sh
```

Se a `.venv` ainda nao existir, prepare o ambiente antes:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements/tester_runtime.txt
```

Depois inicie:

```bash
Scripts/linux/iniciar_vwait.sh
```

## Primeiro uso

Depois de iniciar o VWAIT:

1. Aguarde o navegador abrir.
2. Confirme que o `Menu Chat` abriu em `http://localhost:8502`.
3. Confirme que o `Menu Tester` abriu em `http://localhost:8503`.
4. Se for usar coleta ou bancada, verifique se o dispositivo aparece via `adb devices`.

## Como abrir de novo depois

Se o ambiente ja foi preparado antes:

No Windows:

```bat
Scripts\windows\iniciar_vwait.bat
```

No Linux:

```bash
Scripts/linux/iniciar_vwait.sh
```

## Onde ficam os dados do tester

O workspace local fica dentro da pasta `Data/`.

Ali ficam, por exemplo:
- coletas
- execucoes
- logs
- artefatos temporarios do fluxo

Para consolidar o trabalho de um tester, normalmente basta recolher a pasta `Data/`.

## Arquivos importantes de configuracao

- `.env.tester`
  Usado para apontar o `ADB_PATH` quando necessario.

- `.env.jira`
  Opcional. Usado apenas se o fluxo com Jira estiver configurado.

## Problemas comuns

### 1. A `.venv` parou de funcionar

Isso costuma acontecer quando o Python do Windows foi removido, atualizado ou movido.

Solucao:

```bat
Scripts\windows\setup_vwait.bat
```

### 2. O setup nao encontra o Python

Instale ou repare o Python `3.11+` e marque a opcao `Add Python to PATH`.

### 3. O setup nao encontra o ADB

Verifique uma destas opcoes:
- `ADB_PATH` apontando para o executavel do ADB
- `adb` disponivel no `PATH`
- `tools/platform-tools` copiado para dentro do projeto

### 4. O navegador nao abriu sozinho

Abra manualmente:
- `http://localhost:8502`
- `http://localhost:8503`

### 5. As portas 8502 a 8506 ja estavam em uso

Os launchers tentam limpar processos antigos automaticamente. Se ainda assim houver conflito, feche instancias antigas do VWAIT e rode o launcher novamente.

## Fluxo recomendado para um novo tester

1. Extrair o projeto.
2. Rodar o setup.
3. Rodar o launcher.
4. Confirmar acesso ao `Menu Chat` e ao `Menu Tester`.
5. Validar ADB e conectividade com a bancada.
6. Trabalhar normalmente.
7. Ao final, entregar a pasta `Data/` se for necessario consolidar os resultados.

## Observacao importante

Neste momento o projeto continua usando `Data/` dentro da raiz do repositorio como workspace local. Isso foi mantido de proposito para nao quebrar o fluxo atual do coletor, do runner e dos paineis.
