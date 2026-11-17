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
