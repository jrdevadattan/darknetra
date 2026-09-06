"""Reject removed API operations or schema fields unless the API major changes."""

import argparse
import json
from pathlib import Path


def breaking_changes(before: dict, after: dict) -> list[str]:
    if (
        before.get("info", {}).get("version", "0").split(".")[0]
        != after.get("info", {}).get("version", "0").split(".")[0]
    ):
        old_prefix = {
            path.split("/")[2]
            for path in before.get("paths", {})
            if path.startswith("/api/")
        }
        new_prefix = {
            path.split("/")[2]
            for path in after.get("paths", {})
            if path.startswith("/api/")
        }
        if old_prefix.isdisjoint(new_prefix):
            return []
    changes = []
    for path, operations in before.get("paths", {}).items():
        for method in operations:
            if method.lower() in {
                "get",
                "head",
                "post",
                "patch",
                "put",
                "delete",
                "options",
            } and method not in after.get("paths", {}).get(path, {}):
                changes.append(f"Removed {method.upper()} {path}")
    previous = before.get("components", {}).get("schemas", {})
    current = after.get("components", {}).get("schemas", {})
    for name, schema in previous.items():
        if name not in current:
            changes.append(f"Removed schema {name}")
            continue
        for field, definition in schema.get("properties", {}).items():
            if field not in current[name].get("properties", {}):
                changes.append(f"Removed {name}.{field}")
                continue
            replacement = current[name]["properties"][field]
            if "type" in definition and replacement.get("type") != definition["type"]:
                changes.append(f"Changed type of {name}.{field}")
            if not set(definition.get("enum", [])).issubset(
                replacement.get("enum", [])
            ):
                changes.append(f"Removed enum member from {name}.{field}")
        if not set(schema.get("enum", [])).issubset(current[name].get("enum", [])):
            changes.append(f"Removed enum member from {name}")
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    problems = breaking_changes(
        json.loads(args.before.read_text()), json.loads(args.after.read_text())
    )
    if problems:
        raise SystemExit("\n".join(problems))
    print("No removed operations, fields, enum members or changed primitive types.")
