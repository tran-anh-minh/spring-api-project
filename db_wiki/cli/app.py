import typer

app = typer.Typer(help="DB Wiki — turn undocumented databases into queryable knowledge.")


def main() -> None:
    app()
