from typing import Any

from darknetra.tools.contracts import ToolSpec


def to_ollama_tools(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.input_model.model_json_schema(),
            },
        }
        for s in specs
    ]
