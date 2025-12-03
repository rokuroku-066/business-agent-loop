from __future__ import annotations

import argparse
from pathlib import Path

from .agent.loop import AgentLoop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Business agent loop controller")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Root directory for state and storage",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path.cwd() / "config",
        help="Directory containing ip_profile.json and project_config.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start", help="Initialize storage and seed tasks")
    subparsers.add_parser("status", help="Show current task and iteration status")

    record = subparsers.add_parser("record-iteration", help="Record a placeholder iteration log")
    record.add_argument("--mode", default="explore", help="Iteration mode descriptor")

    return parser


def handle_start(agent: AgentLoop) -> None:
    agent.initialize()
    status = agent.status()
    print("Initialized agent state")
    print(status)


def handle_status(agent: AgentLoop) -> None:
    status = agent.status()
    print(status)


def handle_record_iteration(agent: AgentLoop, mode: str) -> None:
    agent.initialize()
    task = agent.next_task()
    path = agent.record_iteration(task=task, mode=mode)
    print(f"Recorded iteration at {path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    agent = AgentLoop.from_config_dir(base_dir=args.base_dir, config_dir=args.config_dir)

    if args.command == "start":
        handle_start(agent)
    elif args.command == "status":
        handle_status(agent)
    elif args.command == "record-iteration":
        handle_record_iteration(agent, mode=args.mode)
    else:
        parser.error("Unsupported command")


if __name__ == "__main__":
    main()
