"""Routers — one module per §5 endpoint group.

Each module exports `router` (a FastAPI APIRouter). app/main.py wires
them all under the /api/v1 prefix.
"""
