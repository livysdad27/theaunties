"""Entry point for running theAunties with: python -m theaunties"""

import asyncio
import logging
import sys

import click
import uvicorn

from theaunties.config import get_settings


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """theAunties — Autonomous research agents."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat_cmd)


@cli.command("chat")
def chat_cmd():
    """Start the interactive chat interface."""
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level))

    from theaunties.agent.context import ContextManager
    from theaunties.chat.cli import ChatCLI
    from theaunties.chat.handler import ChatHandler
    from theaunties.db.database import get_engine, get_session_factory, init_db
    from theaunties.llm.claude import ClaudeStubClient
    from theaunties.llm.gemini import GeminiStubClient
    from theaunties.llm.router import LLMRouter

    engine = get_engine(settings.db_path)
    init_db(engine)
    session = get_session_factory(engine)()

    if settings.use_stubs:
        gemini = GeminiStubClient(model=settings.llm_discovery_model)
        claude = ClaudeStubClient(model=settings.llm_synthesis_model)
    else:
        from theaunties.llm.gemini import GeminiClient
        from theaunties.llm.claude import ClaudeClient
        gemini = GeminiClient(api_key=settings.gemini_api_key, model=settings.llm_discovery_model)
        claude = ClaudeClient(api_key=settings.anthropic_api_key, model=settings.llm_synthesis_model)

    llm_router = LLMRouter(gemini_client=gemini, claude_client=claude)
    context_mgr = ContextManager(context_dir=settings.context_dir)
    handler = ChatHandler(llm_router=llm_router, context_manager=context_mgr, db_session=session)
    cli_app = ChatCLI(handler=handler)

    try:
        asyncio.run(cli_app.run_interactive())
    finally:
        session.close()


@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
def serve_cmd(host: str, port: int):
    """Start the FastAPI server with scheduler."""
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level))
    uvicorn.run("theaunties.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()
