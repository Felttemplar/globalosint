"""Interface de linha de comando inicial."""

import argparse

from globalosint.database import connect, initialize
from globalosint.dashboard import serve
from globalosint.models import SourceInput, SourceKind
from globalosint.registry import add_source, list_sources


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="globalosint")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Cria ou atualiza o banco SQLite")
    source = commands.add_parser("source", help="Gerencia fontes")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add = source_commands.add_parser("add", help="Cadastra uma fonte como candidata")
    add.add_argument("--name", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--kind", choices=[item.value for item in SourceKind], default="other")
    add.add_argument("--languages", default="en")
    add.add_argument("--axes", default="")
    add.add_argument("--notes")
    source_commands.add_parser("list", help="Lista fontes cadastradas")
    dashboard = commands.add_parser("dashboard", help="Abre o painel local somente leitura")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "init-db":
        print(f"Banco inicializado: {initialize()}")
    elif args.command == "dashboard":
        serve(host=args.host, port=args.port)
    elif args.command == "source" and args.source_command == "add":
        with connect() as connection:
            item = add_source(connection, SourceInput(
                name=args.name, url=args.url, kind=SourceKind(args.kind),
                languages=tuple(filter(None, args.languages.split(","))),
                axes=tuple(filter(None, args.axes.split(","))), notes=args.notes,
            ))
        print(f"Fonte candidata cadastrada: [{item.id}] {item.name} — {item.url}")
    elif args.command == "source" and args.source_command == "list":
        with connect() as connection:
            items = list_sources(connection)
        for item in items:
            print(f"[{item.id}] {item.status.value:9} {item.kind.value:13} {item.name} — {item.url}")


if __name__ == "__main__":
    main()
