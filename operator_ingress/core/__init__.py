"""Operator Ingress core — business logic and protocol orchestration.

Core modules know only the ports defined in ports.py; they never import
operator_ingress.adapters.* directly (assembly wiring lives in __main__.py).
Verb handlers must NOT write phase_state, mode, or consensus on session
objects — use the Layer1Port port interface exclusively.
"""
from __future__ import annotations
