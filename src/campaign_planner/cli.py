import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .runner import run, snapshot
from .storage import Storage
from .tools import PROJECT_ROOT


def main(argv=None):
    # UTF-8 JSON is stable when Windows redirects output to a file or another process.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="内容任务规划 Agent（mock 仅验证流程）")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "resume"):
        sub = commands.add_parser(name)
        sub.add_argument("--input", required=True) if name == "run" else sub.add_argument(
            "--request-id", required=True
        )
        sub.add_argument("--mode", choices=["mock", "live"], default="mock")
        sub.add_argument("--db")
        sub.add_argument("--output-dir")
        sub.add_argument("--now", help="固定模拟时钟；续跑不得改变原起始时间")
        sub.add_argument("--faults", help="测试故障 JSON 文件，不能由模型修改")
        sub.add_argument("--max-model-calls", type=int, default=20)
        sub.add_argument("--max-tool-calls", type=int, default=32)
        sub.add_argument("--materials")
        sub.add_argument("--rules")
    show = commands.add_parser("show")
    show.add_argument("--request-id", required=True)
    show.add_argument("--mode", choices=["mock", "live"], default="mock")
    show.add_argument("--db")
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            store = Storage(args.db or PROJECT_ROOT / "outputs" / args.mode / "state.sqlite")
            try:
                state = store.get(args.request_id)
                result = (
                    snapshot(state, store)
                    if state
                    else dict(status="invalid_input", reason="request_not_found")
                )
            finally:
                store.close()
        else:
            raw = json.loads(Path(args.input).read_text(encoding="utf-8")) if args.command == "run" else None
            result = run(
                raw,
                mode=args.mode,
                db=args.db,
                output=args.output_dir,
                now=args.now,
                faults=json.loads(Path(args.faults).read_text(encoding="utf-8")) if args.faults else None,
                max_models=args.max_model_calls,
                max_tools=args.max_tool_calls,
                resume_id=args.request_id if args.command == "resume" else None,
                rules_path=args.rules,
                materials_path=args.materials,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 2
    except (ValueError, OSError) as exc:
        print(json.dumps(dict(status="invalid_input", reason=str(exc)), ensure_ascii=False), file=sys.stderr)
        return 2
