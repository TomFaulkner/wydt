"""WYDT CLI - Command-line interface for What You Did Today.

This module provides a Click-based CLI for managing the WYDT daily journal application.

Commands:
    serve     Start the WYDT web server
    init-db   Initialize the database
    create   Create a new daily entry
    list     List daily entries
    get      Get a specific entry
    search   Search entries by keyword

Examples:
    # Start the server
    wydt serve

    # Start server on custom port
    wydt serve --port 8080

    # Initialize database
    wydt init-db

    # Create entry for today
    wydt create "Working on the WYDT project"

    # Create entry for specific date
    wydt create "Meeting with team" --date 2026-03-05

    # List recent entries
    wydt list

    # List entries with limit
    wydt list --limit 10

    # Search entries
    wydt search "meeting"

    # Get specific entry
    wydt get 2026-03-05
"""

import os
import logging
from datetime import date, datetime
from typing import Optional

import click
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("wydt")


def get_app():
    """Get the Flask application instance.
    
    Returns:
        Flask: The configured Flask application.
    """
    from wydt import create_app
    return create_app()


def get_db():
    """Get the database instance.
    
    Returns:
        SQLAlchemy: The database instance.
    """
    from wydt.models import db
    return db


def validate_date(ctx, param, value):
    """Validate date string in YYYY-MM-DD format."""
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise click.BadParameter("Date must be in YYYY-MM-DD format")


# =============================================================================
# CLI Group
# =============================================================================

@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--env-file",
    type=click.Path(exists=True),
    help="Path to .env file (defaults to .env in current directory)",
)
def cli(env_file: Optional[str]):
    """WYDT - What You Did Today - Personal daily journal with AI summaries.
    
    A command-line interface for managing your daily journal entries.
    Use --help with any command for more details.
    """
    if env_file:
        load_dotenv(env_file)
    elif os.path.exists(".env"):
        load_dotenv()


# =============================================================================
# Serve Command
# =============================================================================

@cli.command()
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to bind to (default: 0.0.0.0)",
)
@click.option(
    "--port",
    type=int,
    default=5000,
    help="Port to bind to (default: 5000)",
)
@click.option(
    "--debug/--no-debug",
    default=True,
    help="Enable debug mode (default: enabled)",
)
def serve(host: str, port: int, debug: bool):
    """Start the WYDT web server.
    
    Starts the Flask development server for the WYDT web application.
    The web interface is available at http://localhost:5000 (or the specified port).
    
    Args:
        host: IP address to bind to. Use 0.0.0.0 for all interfaces.
        port: Port number to bind to.
        debug: Enable Flask debug mode with reloading.
    
    Examples:
        # Start server with defaults
        wydt serve
        
        # Start on custom port
        wydt serve --port 8080
        
        # Production mode
        wydt serve --debug=False --port 8000
    """
    click.echo(f"Starting WYDT server on {host}:{port}")
    if debug:
        click.echo("Debug mode enabled")
    
    app = get_app()
    app.run(host=host, port=port, debug=debug)


# =============================================================================
# Init DB Command
# =============================================================================

@cli.command()
@click.option(
    "--force/--no-force",
    default=False,
    help="Force recreate tables (deletes existing data)",
)
def init_db(force: bool):
    """Initialize the database.
    
    Creates all necessary database tables for the WYDT application.
    By default, this is safe to run multiple times (it won't overwrite existing data).
    Use --force to drop and recreate all tables (⚠️ this deletes all data).
    
    Args:
        force: If True, drop all existing tables before creating new ones.
    
    Examples:
        # Initialize database (safe)
        wydt init-db
        
        # Recreate tables (destructive)
        wydt init-db --force
    """
    app = get_app()
    
    with app.app_context():
        db = get_db()
        
        if force:
            click.echo("⚠️ Dropping all existing tables...")
            db.drop_all()
        
        click.echo("Creating database tables...")
        db.create_all()
        click.echo("✓ Database initialized successfully")


# =============================================================================
# Create Command
# =============================================================================

@cli.command()
@click.argument("content")
@click.option(
    "--date",
    callback=validate_date,
    default=None,
    help="Date for the entry (default: today)",
)
@click.option(
    "--regenerate/--no-regenerate",
    default=True,
    help="Regenerate AI summary and keywords (default: enabled)",
)
def create(content: str, date: Optional[date], regenerate: bool):
    """Create a new daily journal entry.
    
    Creates or updates a daily journal entry with the specified content.
    If an entry already exists for the date, it will be updated.
    An AI summary and keywords are automatically generated unless --no-regenerate is set.
    
    Args:
        content: The journal entry text (what you did today).
        date: The date for the entry in YYYY-MM-DD format. Defaults to today.
        regenerate: Whether to generate AI summary and keywords.
    
    Examples:
        # Create entry for today
        wydt create "Working on the WYDT project"
        
        # Create entry for specific date
        wydt create "Meeting with team" --date 2026-03-05
        
        # Update without regenerating summary
        wydt create "Updated content" --no-regenerate
    """
    entry_date = date if date else date.today()
    
    app = get_app()
    
    with app.app_context():
        from wydt.models import DailyLog
        from wydt.llm import generate_summary_and_keywords
        
        log = DailyLog.get_or_create(entry_date)
        log.content = content
        
        if regenerate and content.strip():
            log.summary, log.keywords = generate_summary_and_keywords(content)
        
        log.updated_at = datetime.utcnow()
        get_db().session.commit()
        
        click.echo(f"✓ Entry created for {entry_date.isoformat()}")
        
        if log.summary:
            click.echo(f"  Summary: {log.summary}")
        
        if log.keywords:
            click.echo(f"  Keywords: {log.keywords}")


# =============================================================================
# List Command
# =============================================================================

@cli.command()
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of entries to show (default: 10)",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def list_entries(limit: int, format: str):
    """List recent daily journal entries.
    
    Lists the most recent journal entries, ordered by date (newest first).
    
    Args:
        limit: Maximum number of entries to return.
        format: Output format - 'text' for human-readable, 'json' for machine-readable.
    
    Examples:
        # List 10 most recent entries
        wydt list
        
        # List 30 entries
        wydt list --limit 30
        
        # Get JSON output
        wydt list --format json
    """
    app = get_app()
    
    with app.app_context():
        from wydt.models import DailyLog
        
        logs = (
            DailyLog.query
            .order_by(DailyLog.date.desc())
            .limit(limit)
            .all()
        )
        
        if format == "json":
            import json
            click.echo(json.dumps([log.to_dict() for log in logs], indent=2))
        else:
            if not logs:
                click.echo("No entries found")
                return
            
            for log in logs:
                click.echo(f"\n{log.date.isoformat()}")
                click.echo(f"  {log.content[:100]}{'...' if len(log.content) > 100 else ''}")
                if log.summary:
                    click.echo(f"  → {log.summary}")


# =============================================================================
# Get Command
# =============================================================================

@cli.command()
@click.argument("date_str")
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def get(date_str: str, format: str):
    """Get a specific daily journal entry.
    
    Retrieves the journal entry for a specific date.
    
    Args:
        date_str: The date in YYYY-MM-DD format.
        format: Output format - 'text' for human-readable, 'json' for machine-readable.
    
    Examples:
        # Get entry for specific date
        wydt get 2026-03-05
        
        # Get entry as JSON
        wydt get 2026-03-05 --format json
    """
    try:
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise click.ClickException("Invalid date format. Use YYYY-MM-DD")
    
    app = get_app()
    
    with app.app_context():
        from wydt.models import DailyLog
        
        log = DailyLog.query.filter_by(date=entry_date).first()
        
        if not log:
            raise click.ClickException(f"No entry found for {date_str}")
        
        if format == "json":
            import json
            click.echo(json.dumps(log.to_dict(), indent=2))
        else:
            click.echo(f"Date: {log.date.isoformat()}")
            click.echo(f"\nContent:\n{log.content}")
            
            if log.summary:
                click.echo(f"\nSummary: {log.summary}")
            
            if log.keywords:
                click.echo(f"Keywords: {log.keywords}")
            
            if log.updated_at:
                click.echo(f"\nUpdated: {log.updated_at}")


# =============================================================================
# Search Command
# =============================================================================

@cli.command()
@click.argument("query")
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of results (default: 10)",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def search(query: str, limit: int, format: str):
    """Search daily journal entries by keyword.
    
    Searches through content, summaries, and keywords for matching entries.
    
    Args:
        query: Search keyword or phrase.
        limit: Maximum number of results to return.
        format: Output format - 'text' for human-readable, 'json' for machine-readable.
    
    Examples:
        # Search for meetings
        wydt search meeting
        
        # Search and get JSON
        wydt search "project work" --format json
        
        # Get more results
        wydt search python --limit 20
    """
    app = get_app()
    
    with app.app_context():
        from wydt.models import DailyLog
        
        logs = (
            DailyLog.query
            .filter(
                (DailyLog.content.ilike(f"%{query}%"))
                | (DailyLog.summary.ilike(f"%{query}%"))
                | (DailyLog.keywords.ilike(f"%{query}%"))
            )
            .order_by(DailyLog.date.desc())
            .limit(limit)
            .all()
        )
        
        if format == "json":
            import json
            click.echo(json.dumps([log.to_dict() for log in logs], indent=2))
        else:
            if not logs:
                click.echo(f"No results found for '{query}'")
                return
            
            click.echo(f"Found {len(logs)} result(s) for '{query}'\n")
            
            for log in logs:
                click.echo(f"{log.date.isoformat()}")
                click.echo(f"  {log.content[:100]}{'...' if len(log.content) > 100 else ''}")
                if log.summary:
                    click.echo(f"  → {log.summary}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()