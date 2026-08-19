"""Pydantic request/response schemas.

Cross-module by design (per apps/api/README.md): API contract shapes live
here, ORM models live in src/models/. A route file never returns a model
instance directly - always through a schema, so the database and the wire
contract can change independently.
"""
