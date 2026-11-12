"""Temporary no-op for the Person A profile gate until that branch is merged."""
from fastapi import Depends


def require_profile_complete():
    return None
