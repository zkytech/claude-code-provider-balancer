# -*- coding: utf-8 -*-
"""
Main entry point for running the Claude Proxy application using Uvicorn.
Displays a startup banner with configuration details.
"""
import uvicorn
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

from claude_proxy.config import settings
from claude_proxy.api import app
from claude_proxy.logging_config import console, logger


# --- Main Execution Block ---
if __name__ == "__main__":

    # --- Startup Screen using Rich ---
    console.print(
        r"""[bold blue]
           /$$                           /$$
          | $$                          | $$
  /$$$$$$$| $$  /$$$$$$  /$$   /$$  /$$$$$$$  /$$$$$$         /$$$$$$   /$$$$$$   /$$$$$$  /$$   /$$ /$$   /$$
 /$$_____/| $$ |____  $$| $$  | $$ /$$__  $$ /$$__  $$       /$$__  $$ /$$__  $$ /$$__  $$|  $$ /$$/| $$  | $$
| $$      | $$  /$$$$$$$| $$  | $$| $$  | $$| $$$$$$$$      | $$  \ $$| $$  \__/| $$  \ $$ \  $$$$/ | $$  | $$
| $$      | $$ /$$__  $$| $$  | $$| $$  | $$| $$_____/      | $$  | $$| $$      | $$  | $$  >$$  $$ | $$  | $$
|  $$$$$$$| $$|  $$$$$$$|  $$$$$$/|  $$$$$$$|  $$$$$$$      | $$$$$$$/| $$      |  $$$$$$/ /$$/\  $$|  $$$$$$$
 \_______/|__/ \_______/ \______/  \_______/ \_______/      | $$____/ |__/       \______/ |__/  \__/ \____  $$
                                                            | $$                                     /$$  | $$
                                                            | $$                                    |  $$$$$$/
                                                            |__/                                     \______/ 
    [/]""",
        justify="left",
    )

    # Create a panel with configuration details
    config_details = Text.assemble(
        ("   Version       : ", "default"),
        (f'v{settings.app_version}', "bold red"),
        ("\n   Big Model     : ", "default"),
        (settings.big_model_name, "magenta"),
        ("\n   Small Model   : ", "default"),
        (settings.small_model_name, "cyan"),
        ("\n   Log Level     : ", "default"),
        (settings.log_level, "yellow"),
        ("\n   Listening on  : ", "default"),
        (f"http://{settings.host}:{settings.port}", "bold green"),
        ("\n   Reload        : ", "default"),
        ("Enabled", "bold orange1") if settings.reload else ("Disabled", "dim"),
    )
    console.print(
        Panel(
            config_details,
            title="Configuration",
            border_style="blue",
            title_align="left",
            expand=False
        )
    )
    console.print(f"\n\n")
    console.print(Rule(f"Starting uvicorn server...", style="dim blue"))

    # --- Run Uvicorn ---
    try:
        uvicorn.run(
            # Use "src.main:app" if running with `python -m src.main`
            # Use "__main__:app" if running with `python src/main.py`
            # Let's try to detect based on how the script is run, or default to module path
            app="__main__:app" if __package__ is None else "claude_proxy.api:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_config=None,  # Disable Uvicorn's default logging config
            access_log=False,  # Disable Uvicorn's access log; rely on our middleware/logging
        )
    except Exception as e:
        logger.critical(f"Failed to start Uvicorn server: {e}", exc_info=True)
        exit(1)
