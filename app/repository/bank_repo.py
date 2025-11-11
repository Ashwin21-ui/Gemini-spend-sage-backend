from app.schema.bank_statement import AccountDetails, Transaction
from datetime import datetime

def safe_parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except:
        return None

def save_bank_statement(db, data):
    account = data["account_details"]

    account_record = AccountDetails(
        account_holder_name=account.get("account_holder_name"),
        account_number=account.get("account_number"),
        bank_name=account.get("bank_name"),
        branch=account.get("branch"),
        ifsc_code=account.get("ifsc_code"),
        statement_start_date=safe_parse_date(account.get("statement_start_date")),
        statement_end_date=safe_parse_date(account.get("statement_end_date")),
        currency=account.get("currency"),
    )

    db.add(account_record)
    db.flush()  # get account id

    for t in data.get("transactions", []):
        TransactionRecord = Transaction(
            account_id=account_record.id,
            date=safe_parse_date(t.get("date")),
            description=t.get("description"),
            reference_no=t.get("reference_no"),
            amount_value=t.get("amount", {}).get("value"),
            amount_type=t.get("amount", {}).get("type"),
            balance_after_transaction=t.get("balance_after_transaction"),
        )
        db.add(TransactionRecord)

    db.commit()
    return account_record.id
