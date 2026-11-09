"""Create portal accounts: python -m app.auth.cli create-user <username> --role owner"""

import argparse
import getpass

from app.auth.service import AuthError, create_user, reset_password
from app.core.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("--role", choices=["owner", "staff"], required=True)
    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    args = parser.parse_args(argv)

    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return 1

    with SessionLocal() as db:
        try:
            if args.command == "create-user":
                create_user(db, args.username, password, args.role)
            else:
                reset_password(db, args.username, password)
        except AuthError as exc:
            print(exc)
            return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
