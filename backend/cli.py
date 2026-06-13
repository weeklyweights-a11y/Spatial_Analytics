"""CLI for admin tasks."""

import argparse
import uuid

from passlib.context import CryptContext
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import Base, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def create_user(username: str, password: str, role: str) -> None:
    """Insert a new dashboard user."""
    if role not in ("admin", "operator", "viewer"):
        raise SystemExit("Role must be admin, operator, or viewer")
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            raise SystemExit(f"User {username} already exists")
        user = User(
            id=uuid.uuid4(),
            username=username,
            password_hash=pwd_context.hash(password),
            role=role,
        )
        session.add(user)
        session.commit()
        print(f"Created user {username} with role {role}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SpatialScore CLI")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create-user")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--role", required=True)

    args = parser.parse_args()
    if args.command == "create-user":
        create_user(args.username, args.password, args.role)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
