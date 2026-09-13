"""Load a user-authored flow file (YAML or JSON) into a validated Flow."""
import json
import os

import yaml

from .models import Flow


def load_flow(path: str) -> Flow:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        data = yaml.safe_load(raw)
    elif ext == ".json":
        data = json.loads(raw)
    else:
        # Best-effort: try YAML first (a superset of JSON), fall back to JSON.
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            data = json.loads(raw)

    return Flow.model_validate(data)
