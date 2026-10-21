"""Account administration from the server console (T028).

Run from the backend folder with its virtual environment:
    python ../deploy/manage_users.py create-admin <user_id> [--name "Display Name"]
    python ../deploy/manage_users.py create <user_id> --role viewer|maintenance|engineer|admin [--name ...]
    python ../deploy/manage_users.py deactivate <user_id>
    python ../deploy/manage_users.py reset-password <user_id>
    python ../deploy/manage_users.py list
Passwords are read without echo. Actions are audited as user "console".
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from app.core.auth import NewUser, UserChange, UserStore
from app.core.db import get_engine
from app.core.security import Principal, Role
from sqlalchemy.orm import sessionmaker

CONSOLE = Principal(user_id="console", role=Role.ADMIN)


def _password() -> str:
    a = getpass.getpass("Password (10+ characters): ")
    if a != getpass.getpass("Repeat: "):
        sys.exit("Passwords differ")
    return a


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("user_id")
    c.add_argument("--name", default="Administrator")
    n = sub.add_parser("create")
    n.add_argument("user_id")
    n.add_argument("--role", required=True, choices=[r.value for r in Role])
    n.add_argument("--name", default="")
    d = sub.add_parser("deactivate")
    d.add_argument("user_id")
    r = sub.add_parser("reset-password")
    r.add_argument("user_id")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    with sessionmaker(get_engine(), expire_on_commit=False)() as s:
        store = UserStore(s)
        if args.cmd == "create-admin":
            u = store.create(
                NewUser(
                    user_id=args.user_id,
                    display_name=args.name,
                    role=Role.ADMIN,
                    password=_password(),
                ),
                CONSOLE,
            )
            print(f"Created administrator {u.user_id}")
        elif args.cmd == "create":
            u = store.create(
                NewUser(
                    user_id=args.user_id,
                    display_name=args.name or args.user_id,
                    role=Role(args.role),
                    password=_password(),
                ),
                CONSOLE,
            )
            print(f"Created {u.role.value} {u.user_id}")
        elif args.cmd == "deactivate":
            store.change(args.user_id, UserChange(active=False), CONSOLE)
            print(f"Deactivated {args.user_id}; their sessions stop working at once")
        elif args.cmd == "reset-password":
            store.change(args.user_id, UserChange(password=_password()), CONSOLE)
            print(f"Password reset for {args.user_id}; the lockout was cleared")
        else:
            for u in store.users():
                print(f"{u.user_id:20} {u.role.value:12} {'active' if u.active else 'deactivated'}")


if __name__ == "__main__":
    main()
