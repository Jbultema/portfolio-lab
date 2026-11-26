"""Explicit terminal cash settlements; never forward-filled prices or free exits."""

import math

import pandas as pd

from portfolio_lab.contracts import ContractError


def terminal_records(records, instruments, index):
    output = {}
    for record in records or []:
        security = record.get("security_id")
        session = pd.Timestamp(record.get("settlement_session"))
        value = record.get("value_per_adjusted_share")
        if (security not in instruments or pd.isna(session) or session.tzinfo is not None
                or session != session.normalize() or session not in index
                or not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0 or security in output):
            raise ContractError("Invalid, duplicate or unpriced terminal cash settlement")
        output[security] = (session, float(value))
    return output
