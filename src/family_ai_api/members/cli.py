import argparse
import sys
from pathlib import Path

from family_ai_api.config import get_settings
from family_ai_api.members.store import MemberStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Family AI members and tokens.")
    parser.add_argument("--db", type=Path, default=None, help="override members DB path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a member and print its token")
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=["admin", "member"], default="member")

    subparsers.add_parser("list", help="list members without tokens")

    rotate = subparsers.add_parser("rotate", help="rotate a member token")
    rotate.add_argument("--name", required=True)

    revoke = subparsers.add_parser("revoke", help="revoke a member")
    revoke.add_argument("--name", required=True)

    args = parser.parse_args(argv)
    settings = get_settings()
    store = MemberStore(args.db or Path(settings.members_db_path))

    try:
        if args.command == "create":
            try:
                member, token = store.add(args.name, args.role)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print(f"member: {member.name} (id={member.id}, role={member.role})")
            print(f"token (shown once): {token}")
            return 0

        if args.command == "list":
            for member in store.list():
                status = "revoked" if member.revoked else "active"
                print(
                    f"{member.id}\t{member.name}\t{member.role}\t"
                    f"{status}\t{member.created_at}"
                )
            return 0

        if args.command == "rotate":
            token = store.rotate(args.name)
            if token is None:
                print(f"member not found: {args.name}", file=sys.stderr)
                return 1
            print(f"token for {args.name} (shown once): {token}")
            return 0

        if args.command == "revoke":
            if not store.revoke(args.name):
                print(f"member not found or already revoked: {args.name}", file=sys.stderr)
                return 1
            print(f"revoked: {args.name}")
            return 0
    finally:
        store.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
