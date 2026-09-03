"""Running the agent locally from a terminal.

The transport is deliberately thin: the agent knows nothing about who is talking
to it. In phase 2 an OpenAI-compatible shim for OpenWebUI takes this place, and
the agent itself does not change.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid

from .agent import build_agent
from .config import get_settings
from .memory import open_memory


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


async def run_once(prompt: str, *, thread_id: str, verbose: bool) -> None:
    """Run a single prompt and print the final answer."""
    async with open_memory() as (store, checkpointer):
        agent = await build_agent(store=store, checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
            stream_mode="values",
        ):
            messages = chunk.get("messages") or []
            if not messages:
                continue
            last = messages[-1]
            if verbose and getattr(last, "tool_calls", None):
                for call in last.tool_calls:
                    print(f"  -> {call['name']}", file=sys.stderr)

        state = await agent.aget_state(config)
        final = (state.values.get("messages") or [])[-1]
        print(getattr(final, "content", ""))


async def repl(thread_id: str, verbose: bool) -> None:
    """Run an interactive loop on a single conversation thread."""
    async with open_memory() as (store, checkpointer):
        agent = await build_agent(store=store, checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        print(f"Agentic SDLC Scout. Thread: {thread_id}. Empty line exits.\n")

        while True:
            try:
                # Blocking input is intentional: the REPL has nothing to do
                # between turns, and a thread hop would only add latency.
                prompt = input("> ").strip()  # noqa: ASYNC250
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not prompt:
                return

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]}, config=config
            )
            print("\n" + getattr(result["messages"][-1], "content", "") + "\n")


def main() -> None:
    """CLI entry point: one-shot prompt, or a REPL when no prompt is given."""
    parser = argparse.ArgumentParser(prog="scout", description="Agentic SDLC Scout")
    parser.add_argument("prompt", nargs="*", help="the prompt; without it a REPL starts")
    parser.add_argument("--thread", default=None, help="thread id to continue a conversation")
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool calls")
    args = parser.parse_args()

    _configure_logging(args.verbose)
    settings = get_settings()
    if not settings.openai_api_key:
        message = "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in."
        print(message, file=sys.stderr)
        raise SystemExit(1)

    thread_id = args.thread or f"cli-{uuid.uuid4().hex[:8]}"
    if args.prompt:
        asyncio.run(run_once(" ".join(args.prompt), thread_id=thread_id, verbose=args.verbose))
    else:
        asyncio.run(repl(thread_id, args.verbose))


if __name__ == "__main__":
    main()
