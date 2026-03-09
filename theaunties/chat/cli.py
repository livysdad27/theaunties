"""Rich-based terminal chat client for theAunties."""

import asyncio
import logging

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme

from theaunties.chat.handler import ChatHandler, ChatState

logger = logging.getLogger(__name__)

THEME = Theme({
    "user": "bold cyan",
    "assistant": "bold green",
    "system": "dim yellow",
    "error": "bold red",
})


class ChatCLI:
    """Rich terminal chat interface for theAunties."""

    def __init__(self, handler: ChatHandler):
        self._handler = handler
        self._console = Console(theme=THEME)
        self._running = False

    def display_welcome(self) -> None:
        """Show the welcome message."""
        self._console.print(
            Panel(
                "[bold]theAunties[/bold] — Autonomous Research Agents\n\n"
                "Describe what you want to track and I'll set up a research agent for you.\n"
                "Type [bold cyan]quit[/bold cyan] or [bold cyan]exit[/bold cyan] to leave.\n"
                "Type [bold cyan]status[/bold cyan] to see current topic info.\n"
                "Type [bold cyan]run[/bold cyan] to trigger a manual research run.",
                title="Welcome",
                border_style="green",
            )
        )

    def display_message(self, role: str, message: str) -> None:
        """Display a chat message."""
        if role == "user":
            self._console.print(f"\n[user]You:[/user] {message}")
        elif role == "assistant":
            self._console.print(f"\n[assistant]Auntie:[/assistant]")
            self._console.print(Markdown(message))
        elif role == "system":
            self._console.print(f"\n[system]{message}[/system]")

    def display_status(self) -> None:
        """Show current handler state."""
        state = self._handler.state
        topic_id = self._handler.active_topic_id

        if state == ChatState.IDLE:
            self._console.print("[system]No active topic. Describe what you'd like to track.[/system]")
        elif state == ChatState.AWAITING_CONFIRMATION:
            self._console.print("[system]Waiting for your confirmation (yes/no).[/system]")
        elif state == ChatState.ACTIVE:
            self._console.print(f"[system]Active topic ID: {topic_id}. You can refine or ask questions.[/system]")

    async def run_interactive(self) -> None:
        """Run the interactive chat loop."""
        self._running = True
        self.display_welcome()

        while self._running:
            try:
                user_input = Prompt.ask("\n[user]You[/user]")
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[system]Goodbye![/system]")
                break

            if not user_input.strip():
                continue

            command = user_input.strip().lower()
            if command in ("quit", "exit", "q"):
                self._console.print("[system]Goodbye![/system]")
                break
            elif command == "status":
                self.display_status()
                continue
            elif command == "run":
                self._console.print("[system]Manual run triggered (not yet wired).[/system]")
                continue
            elif command == "help":
                self.display_welcome()
                continue

            # Send to chat handler
            try:
                response = await self._handler.handle_message(user_input)
                self.display_message("assistant", response.message)
            except Exception as e:
                self._console.print(f"[error]Error: {e}[/error]")
                logger.exception("Chat error")

    def stop(self) -> None:
        """Stop the interactive loop."""
        self._running = False
