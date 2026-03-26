"""
Bank Statement Repository — Re-export shim for backward compatibility.

All implementation lives in bank_repo_async.py.
This module exists so that any code importing from bank_repo
continues to work without modification.
"""

from app.repository.bank_repo_async import (
    save_bank_statement_async,
    get_account_by_id_async,
    get_user_accounts_async,
    safe_parse_date,
)

__all__ = [
    "save_bank_statement_async",
    "get_account_by_id_async",
    "get_user_accounts_async",
    "safe_parse_date",
]
