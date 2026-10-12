"""Independent read-only assurance package for the G1 synthetic offline preview R1."""

from __future__ import annotations

from pathlib import Path

TASK_ID = "V06_G1_GEMINI_OFFLINE_ASSURANCE_R1"
CONTROLLER_DISPATCH_SHA = "4a487fcef182edc6c68486ff53d4a64caa10debc"
EXACT_START_SHA = "861a9d148f72db00e6079e53af78220bdd7e84ce"
PARENT_C3_SHA = "84c4764a2f1c46c81f43b144f5daf1f54cccc5d3"
OWN_NAMESPACE = "g1_offline_assurance_r1"
OWN_SCRATCH = Path("/tmp/btc-g1_offline_assurance_r1")
