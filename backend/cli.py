from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)

ROOT_DIR = Path(__file__).parent.parent
COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"


def _compose(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def _run(*cmd: str) -> None:
    try:
        subprocess.run(list(cmd), check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(code=e.returncode)


def _exec(*inner_cmd: str) -> None:
    """Run in the web container, or directly when Docker is unavailable
    (e.g., inside the devcontainer where the backend runs natively)."""
    if shutil.which("docker"):
        _run(*_compose("exec", "web", *inner_cmd))
    else:
        _run(*inner_cmd)


@app.command()
def compose_up(
    no_detach: Annotated[bool, typer.Option("--no-detach")] = False,
) -> None:
    """Start all services (detached by default)."""
    cmd = _compose("up")
    if not no_detach:
        cmd.append("-d")
    _run(*cmd)


@app.command()
def compose_down() -> None:
    """Stop and remove all services."""
    _run(*_compose("down"))


@app.command()
def logs() -> None:
    """Follow service logs."""
    _run(*_compose("logs", "-f"))


@app.command()
def serve() -> None:
    """Start the Django development server."""
    _run("python", "manage.py", "runserver", "0.0.0.0:8000")


@app.command()
def test(
    path: Annotated[Optional[str], typer.Argument()] = None,
) -> None:
    """Run pytest inside the web container."""
    cmd = ["pytest"]
    if path:
        cmd.append(path)
    _exec(*cmd)


@app.command()
def lint() -> None:
    """Run ruff check inside the web container."""
    _exec("ruff", "check", ".")


@app.command()
def format_code() -> None:
    """Run ruff format inside the web container."""
    _exec("ruff", "format", ".")


@app.command()
def shell() -> None:
    """Open the Django shell inside the web container."""
    _exec("python", "manage.py", "shell")


@app.command()
def db_backup(
    output: Annotated[str, typer.Argument()] = "backup.sql",
) -> None:
    """Dump the database to a SQL file on the host."""
    import os

    db = os.environ.get("POSTGRES_DB", "pubmed_radar")
    user = os.environ.get("POSTGRES_USER", "pubmed_radar")
    with open(output, "wb") as f:
        subprocess.run(
            _compose("exec", "-T", "db", "pg_dump", "-U", user, db),
            stdout=f,
            check=True,
        )
    typer.echo(f"Backed up to {output}")


@app.command()
def db_restore(
    file: Annotated[str, typer.Argument()],
) -> None:
    """Restore the database from a SQL file on the host."""
    import os

    db = os.environ.get("POSTGRES_DB", "pubmed_radar")
    user = os.environ.get("POSTGRES_USER", "pubmed_radar")
    with open(file, "rb") as f:
        subprocess.run(
            _compose("exec", "-T", "db", "psql", "-U", user, db),
            stdin=f,
            check=True,
        )
    typer.echo("Restore complete")


@app.command()
def generate_secret_key() -> None:
    """Print a new Django-compatible secret key."""
    import secrets

    typer.echo(secrets.token_urlsafe(50))


@app.command()
def init_workspace() -> None:
    """Copy .env.example to .env if .env does not exist."""
    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"
    if env_file.exists():
        typer.echo(".env already exists — skipping.")
        return
    if not env_example.exists():
        typer.echo(".env.example not found.", err=True)
        raise typer.Exit(code=1)
    shutil.copy(env_example, env_file)
    typer.echo(".env created from .env.example")


if __name__ == "__main__":
    app()
