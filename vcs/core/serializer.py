from __future__ import annotations

import json
from typing import Any, Dict, Union

from pydantic import BaseModel


class Serializer:
    @staticmethod
    def to_canonical_dict(model_or_dict: Union[BaseModel, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(model_or_dict, BaseModel):
            return model_or_dict.model_dump(mode="json")
        elif isinstance(model_or_dict, dict):
            return model_or_dict
        else:
            raise TypeError(f"Expected BaseModel or dict, got {type(model_or_dict)}")

    @staticmethod
    def serialize_canonical_json(model_or_dict: Union[BaseModel, Dict[str, Any]]) -> str:
        data = Serializer.to_canonical_dict(model_or_dict)
        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False
        )
