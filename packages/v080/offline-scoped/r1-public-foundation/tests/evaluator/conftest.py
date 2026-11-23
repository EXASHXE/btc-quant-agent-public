from __future__ import annotations

import json

import pytest
from program_c.integrity import WORKSPACE, canonical, digest, without
from program_c.protocol import load_protocol
from program_c.validation import seal_episode


@pytest.fixture
def protocol():
    return load_protocol()


@pytest.fixture
def fixture_export():
    def load(name):
        return json.loads((WORKSPACE / "fixtures" / (name + ".json")).read_bytes())
    return load


def reseal(value):
    for row in value["episodes"] + value["control_pool"]:
        seal_episode(row)
    value["export_sha256"] = digest(without(value, "export_sha256"))
    return canonical(value)
