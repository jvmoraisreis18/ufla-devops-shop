# ufla-devops-shop

Repositório da turma de **DevOps na Prática** — DCC / UFLA.

Prof. Dr. Rafael Serapilha Durelli · [rafael.durelli@ufla.br](mailto:rafael.durelli@ufla.br)

Este repositório é o **projeto fio condutor** da disciplina. Você faz um *fork*
dele na Atividade 0 e trabalha no seu fork durante as 15 semanas: a mesma
aplicação vai sendo containerizada, testada, empacotada, implantada, monitorada
e provisionada, semana após semana.

---

## Comece por aqui

1. Instale as ferramentas: **[docs/instalacao.md](docs/instalacao.md)**
   (Ubuntu/Debian, Fedora, macOS e Windows com WSL2).
2. Faça o *fork* deste repositório (botão **Fork**, canto superior direito).
3. Clone o **seu** fork e verifique a máquina:

   ```bash
   git clone git@github.com:<seu-usuario>/ufla-devops-shop.git
   cd ufla-devops-shop
   ./scripts/check-ambiente.sh
   ```

4. Siga o enunciado da **Atividade 0**, publicado no campus virtual.

---

## Estrutura

```
ufla-devops-shop/
├── app/                       # a API (FastAPI): uvicorn app:api
├── static/                    # o front estático, servido pela API em /
├── tests/                     # pytest — roda sem banco nem cache
├── requirements.txt           # dependências de execução (vão para a imagem)
├── requirements-dev.txt       # + testes, cobertura e lint (CI e desenvolvimento)
├── pyproject.toml             # configuração de ruff, pytest e cobertura
├── docs/
│   ├── instalacao.md          # roteiro de instalação por sistema operacional
│   └── aplicacao.md           # como a aplicação funciona, rotas e variáveis
├── scripts/
│   ├── check-ambiente.sh      # verificador de ambiente (Atividade 0)
│   └── baixar-dados.sh        # traz o access.log da Atividade 2
├── alunos/                    # apresentação de cada aluno (Atividade 0)
├── analises/                  # análises da Atividade 1 e (em logs/) da Atividade 2
└── .github/
    ├── pull_request_template.md
    └── workflows/             # verificação automática de cada atividade
```

## A aplicação

`ufla-devops-shop` é uma loja mínima: API em Python (FastAPI), PostgreSQL,
Redis e um front estático. Ela é o **fio condutor** das 15 semanas — cada
atividade acrescenta uma camada sobre a mesma base, e nenhuma começa do zero.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app:api --reload        # http://localhost:8000  (API + front + /docs)
pytest --cov=app                # os testes não precisam de banco nem de cache
```

Sem variáveis de ambiente ela sobe **sozinha** (SQLite + cache em memória).
Com `DATABASE_URL` e `REDIS_URL` ela usa PostgreSQL e Redis. Rotas, variáveis,
modos e os tamanhos reais de imagem estão em
**[docs/aplicacao.md](docs/aplicacao.md)** — leia antes da Atividade 4.

### Seu fork está desatualizado?

Quem fez o *fork* antes de a aplicação entrar aqui precisa **trazê-la**:
`git pull` puxa do seu fork, não deste repositório.

```bash
git remote add upstream https://github.com/rdurelli/ufla-devops-shop.git   # uma vez só
git fetch upstream && git switch main && git merge upstream/main && git push origin main
```

Ou **Sync fork → Update branch** na página do seu fork. Faça isso no início de
**toda** atividade.

## `scripts/check-ambiente.sh`

Verifica ferramentas, versões mínimas, o daemon do Docker, a configuração do Git
e os recursos da máquina. Quando algo falta, imprime o comando de instalação
para o sistema detectado.

```bash
./scripts/check-ambiente.sh                      # relatório colorido
./scripts/check-ambiente.sh | tee ambiente.txt   # salva para anexar ao PR
```

Sai com código `0` se o ambiente estiver pronto e `1` se faltar algo
obrigatório. Versões mínimas: `git` 2.30, `docker` 24.0, `kubectl` 1.28,
`kind` 0.20, `helm` 3.12, `terraform` 1.5, Docker Compose v2.

O script também é material didático: na Semana 4 (shell script) abrimos este
arquivo em aula e discutimos as construções usadas nele.

---

## Pipeline DevSecOps com GitHub Actions

O trabalho prático integra testes, análise de segurança, SBOM e publicação no
GHCR no workflow [DevSecOps CI](.github/workflows/devsecops.yml). Ele executa em
Pull Requests e em pushes na `main`, com Python 3.12 no job de testes.

### Arquitetura e controles obrigatórios

| Check obrigatório | Responsabilidade |
|---|---|
| Gitleaks | Analisa o histórico Git completo e reprova a execução ao detectar possíveis segredos. O relatório publicado contém localização e regra, sem os valores sensíveis. |
| Ruff e pytest | Executa lint, testes automatizados da aplicação, cobertura em `coverage.xml` e testes da política de publicação. |
| SonarQube Cloud e Quality Gate | Executa análise estática, importa a cobertura produzida pelo pytest e aguarda o Quality Gate. A reprovação do gate bloqueia o check. |
| Trivy - dependencias do projeto | Analisa as dependências Python efetivamente instaladas no CI, registradas com `pip freeze --all`. |
| Trivy e Syft - imagem candidata | Constrói e exporta a imagem Docker sem publicar; analisa a imagem com Trivy e gera o SBOM da mesma candidata com Syft. |

O Gitleaks e o CI iniciam as verificações. SonarQube Cloud e Trivy de dependências
dependem do CI; a análise da imagem depende do CI e do Gitleaks. A publicação no
GHCR depende da aprovação dos cinco checks.

O **Trivy 0.76.1** produz um relatório JSON com todas as severidades. O bloqueio
usa `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`: vulnerabilidades
HIGH ou CRITICAL com correção disponível reprovam a execução. LOW e MEDIUM são
registradas sem bloquear; vulnerabilidades sem correção também permanecem no
relatório completo, sem acionar esse critério de bloqueio. Erros operacionais
nas análises não são ignorados.

O **Syft 1.55.0** gera `sbom.cdx.json` em **CycloneDX JSON 1.6**, valida sua
estrutura e os componentes da aplicação e publica o SBOM como artifact. O
`provenance.json` associa o inventário ao commit, à execução e aos hashes da
imagem exportada e do SBOM.

### Publicação segura no GHCR e proteção da main

A publicação automática ocorre somente em **pushes na `main` deste repositório**,
após sucesso dos cinco controles. Pull Requests não publicam imagens. O job
recebe a candidata analisada por artifact, verifica integridade e contexto e
carrega a imagem sem reconstruí-la.

A autenticação usa o `GITHUB_TOKEN`, com `packages: write` restrito ao job de
publicação. O destino é `ghcr.io/jvmoraisreis18/ufla-shop:sha-<commit>`. O script
recusa sobrescrever uma tag SHA existente, verifica o digest remoto e registra a
rastreabilidade em `publication.json` e no resumo da execução.

A proteção configurada para a `main` exige **Pull Request e sucesso dos cinco
checks da tabela** antes do merge. Uma falha em qualquer controle obrigatório
impede a integração. Essa exigência é distinta do Quality Gate do SonarQube,
que compõe um desses checks.

### Demonstração: bloqueio e correção da CVE-2023-28859

A demonstração foi realizada na branch `teste-vulnerabilidade`, pelo
[PR #2 — Bloqueio de CVE-2023-28859](https://github.com/jvmoraisreis18/ufla-devops-shop/pull/2).
Somente a versão de `redis` em `requirements.txt` foi alterada.

| Etapa | Alteração e evidência |
|---|---|
| Introdução controlada | Commit `c04794d`: troca de `redis==8.1.0` por `redis==4.5.3`, vulnerável à **CVE-2023-28859**, classificada como **HIGH** pelo Trivy. |
| Reprovação | A [execução 40622194793](https://github.com/jvmoraisreis18/ufla-devops-shop/actions/runs/40622194793) falhou nos checks de dependências e de imagem do Trivy. Com checks obrigatórios reprovados, o merge ficou bloqueado. |
| Correção | Commit `89b2c82`: restauração de `redis==8.1.0` na mesma branch e no mesmo PR. |
| Aprovação | A [execução 40623526573](https://github.com/jvmoraisreis18/ufla-devops-shop/actions/runs/40623526573) aprovou os cinco controles após a correção. |

**Nenhuma imagem vulnerável foi publicada:** o job de publicação foi pulado nas
duas execuções do PR. O PR #2 foi encerrado sem merge; a demonstração não levou
a dependência vulnerável à `main`.

A implementação do pipeline e da publicação está no
[PR #1 — Trabalho DevSecOps](https://github.com/jvmoraisreis18/ufla-devops-shop/pull/1).
A [execução 40620239323](https://github.com/jvmoraisreis18/ufla-devops-shop/actions/runs/40620239323)
aprovou o pipeline no PR. Após sua integração, a
[execução 40620764725 na main](https://github.com/jvmoraisreis18/ufla-devops-shop/actions/runs/40620764725)
aprovou os controles e a publicação automatizada no GHCR.

### Como consultar e baixar relatórios e SBOM

1. Abra a aba [Actions](https://github.com/jvmoraisreis18/ufla-devops-shop/actions)
   e selecione uma execução de **DevSecOps CI**, ou use os links das evidências.
2. Abra cada job para consultar os passos, logs e motivos de reprovação.
3. No resumo da execução, localize **Artifacts** e clique no nome para baixar o
   arquivo ZIP. Entre no GitHub com uma conta que tenha acesso ao repositório.
4. Extraia o ZIP e consulte os arquivos correspondentes:

| Artifact | Conteúdo principal |
|---|---|
| `gitleaks-report` | `gitleaks-report.json`, sem valores de segredos. |
| `python-coverage` | `coverage.xml`, também importado pelo SonarQube Cloud. |
| `resolved-python-dependencies` | `requirements.txt` com o inventário instalado no CI. |
| `trivy-dependencies` e `trivy-image` | `vulnerabilities.json`, `blocking.txt`, logs e metadados da base de vulnerabilidades. |
| `sbom-cyclonedx-<sha>-<run_id>-<run_attempt>` | `sbom.cdx.json`, `provenance.json` e log do Syft. |
| `release-candidate-<sha>-<run_id>-<run_attempt>` | Imagem candidata aprovada, relatórios, SBOM e manifesto de integridade. |
| `ghcr-publication-<sha>-<run_id>-<run_attempt>` | Evidências da publicação, incluindo `publication.json` quando concluída com sucesso. |

A retenção configurada é de **7 dias**. Os artifacts disponíveis dependem dos
passos executados: uma falha anterior pode impedir sua geração. A candidata é
transferida apenas após aprovação da análise de imagem; os artifacts da
publicação existem quando esse job é executado. Baixe as evidências dentro do
prazo de retenção.

---

## Como entregar

Toda atividade tem **duas etapas obrigatórias**. Faltando qualquer uma delas, a
atividade é considerada não entregue.

1. **Pull Request neste repositório**, com o trabalho feito na *branch*
   `atividade-NN` do seu fork.
2. **Link do Pull Request postado no campus virtual**, na tarefa correspondente.
   O horário desta postagem é o registro oficial da entrega.

O fluxo é sempre o mesmo:

```bash
git switch -c atividade-00                       # branch da atividade
git add alunos/<seu-usuario>.md ambiente.txt     # seus arquivos
git commit -m "feat: apresentacao e ambiente de <seu-usuario>"
git push -u origin atividade-00
```

Depois abra o Pull Request pelo GitHub, com o título no padrão
`Atividade 0 -- Seu Nome`.

### Verificação automática

Assim que o PR é aberto, o GitHub Actions roda sozinho e comenta o resultado em
cerca de um minuto. Se aparecer ✗ vermelho, leia o comentário, corrija, faça um
novo commit e dê `push` na mesma branch — o PR se atualiza sozinho. Você pode
repetir isso quantas vezes quiser antes do prazo.

A verificação automática **não é a nota**. Ela cobre o que a máquina consegue
julgar; a avaliação do professor complementa nos aspectos que ela não julga —
clareza, justificativa das decisões e qualidade da documentação.

### Atrasos e descarte

Atraso: desconto de 1,0 ponto por dia corrido, contado pelo horário da postagem
no campus virtual. Descarte: a menor nota entre as atividades do semestre é
descartada no cálculo final, sem necessidade de justificativa.

---

## Onde pedir ajuda

No **fórum da atividade**, no campus virtual. Pergunta pública gera resposta que
serve para a turma toda — e quase sempre alguém já passou pelo mesmo problema.

Ao relatar um erro, inclua:

1. o que você estava tentando fazer;
2. o comando exato que executou;
3. a mensagem de erro **completa**, copiada como texto (não como foto da tela);
4. o que você já tentou.

Esta é a mesma estrutura de um bom *issue* e de um bom *postmortem*.

---

## Uso de IA generativa

Permitido e incentivado. Em contrapartida, você deve ser capaz de explicar
qualquer linha entregue: a arguição final pergunta o *porquê* das decisões, não
a sintaxe.
