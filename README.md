# GLOBAL OSINT

Fundação para uma plataforma de inteligência de fontes abertas, com rastreabilidade de fontes, evidências e histórico de eventos. Esta primeira entrega implementa apenas a persistência e o cadastro de fontes; não coleta dados nem produz avaliações automatizadas.

## Requisitos

- Python 3.11 ou superior
- Sem dependências de terceiros

## Início rápido

```powershell
python -m globalosint.cli init-db
python -m globalosint.cli source add --name "OMS" --url "https://www.who.int/" --kind institutional --languages en,fr --axes health
python -m globalosint.cli source list
python -m globalosint.cli dashboard
```

Execute os comandos a partir da pasta `src` ou instale o projeto com `python -m pip install -e .`.

O banco SQLite padrão fica em `data/globalosint.sqlite3`. Defina `GLOBALOSINT_DB_PATH` para usar outro caminho. O banco e a pasta de dados não são versionados.

O dashboard abre em `http://127.0.0.1:8765`, lê o banco local e não oferece rotas para alterar dados. Use `--host` ou `--port` para ajustar o endereço.

## Integração com FreshRSS

O coletor consulta a API compatível com Google Reader do FreshRSS em modo somente leitura, importa artigos publicados na janela configurada e salva cada publicação como uma observação `unreviewed`. Assinaturas novas aparecem como fontes `candidate`; nenhum artigo é promovido automaticamente a evento ou fato. A API e o endpoint de conteúdo são descritos na [documentação oficial do FreshRSS](https://freshrss.github.io/FreshRSS/en/developers/06_GoogleReader_API.html).

No FreshRSS, habilite o acesso externo via API e crie/redefina a senha específica da API. Configure a URL completa fornecida pelo FreshRSS (terminada em `/api/greader.php`) e as credenciais no ambiente, sem colocá-las no Git:

```powershell
$env:FRESHRSS_API_URL = "https://rss.example.org/api/greader.php"
$env:FRESHRSS_USERNAME = "seu-usuario"
$env:FRESHRSS_PASSWORD = "senha-especifica-da-api"
python -m globalosint.cli freshrss-sync --since-hours 24 --max-items 500
```

O coletor usa HTTPS fora de localhost, pagina até o limite configurado, deduplica por fonte e ID externo, registra falhas e mantém a origem rastreável. Ele lê os artigos que o FreshRSS já buscou; a atualização periódica dos feeds continua a cargo do FreshRSS. Não há instância FreshRSS nem credenciais configuradas neste repositório, então a conexão real depende da configuração acima.

## Estado atual

- SQLite com tabelas para fontes, eventos, evidências, vínculos entre fontes e eventos, histórico e execuções de coleta.
- Source Registry com cadastro, avaliação inicial e estados candidate/approved/rejected.
- CLI para inicializar o banco e cadastrar/listar fontes.
- Vocabulário dos seis eixos e sete idiomas configurados.
- Nenhum coletor, integração social, Global Watch, detecção de eventos ou relatório automatizado foi implementado nesta fase.

## Desenvolvimento

```powershell
python -m unittest discover -s tests -v
```

Consulte [`docs/methodology.md`](docs/methodology.md) para os princípios de rastreabilidade e limites metodológicos.
