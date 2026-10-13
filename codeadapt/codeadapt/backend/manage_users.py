"""CLI administrative tool to safely manage users and provision researcher accounts.

Usage:
    python manage_users.py create-researcher --username <user> --email <email> --password <pass>
    python manage_users.py list-users
"""
import argparse
import getpass
import os
import sys

# Ensure backend modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auth
import store


def create_researcher(username=None, email=None, password=None):
    store.init()
    if not username:
        username = input("Enter researcher username: ").strip()
    if not email:
        email = input("Enter researcher email: ").strip()
    if not password:
        password = getpass.getpass("Enter researcher password: ").strip()
        confirm = getpass.getpass("Confirm researcher password: ").strip()
        if password != confirm:
            print("Error: Passwords do not match.")
            sys.exit(1)

    try:
        res = auth.create_researcher_user(username, email, password)
        print(f"Success: Researcher account {res['username']} ({res['email']}) successfully {res['action']}.")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


def list_users():
    store.init()
    with store._connect() as conn:
        rows = conn.execute("SELECT user_id, username, email, role, created_at FROM users").fetchall()
    print(f"{'User ID':<22} {'Username':<18} {'Role':<12} {'Email'}")
    print("-" * 75)
    for r in rows:
        print(f"{r['user_id']:<22} {r['username']:<18} {r['role']:<12} {r['email']}")


def main():
    parser = argparse.ArgumentParser(description="CodeAdapt User Management CLI")
    subparsers = parser.add_subparsers(dest="command")

    cr = subparsers.add_parser("create-researcher", help="Create or promote a researcher account")
    cr.add_argument("--username", help="Researcher username")
    cr.add_argument("--email", help="Researcher email")
    cr.add_argument("--password", help="Researcher password")

    subparsers.add_parser("list-users", help="List all registered accounts")

    args = parser.parse_args()
    if args.command == "create-researcher":
        create_researcher(args.username, args.email, args.password)
    elif args.command == "list-users":
        list_users()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
