from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from vcs.core.serializer import Serializer


class Hashing:
    @staticmethod
    def compute_blob_hash(model_or_dict_or_str: Union[BaseModel, Dict[str, Any], str]) -> str:
        if isinstance(model_or_dict_or_str, str):
            content_str = model_or_dict_or_str
        else:
            content_str = Serializer.serialize_canonical_json(model_or_dict_or_str)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_commit_hash(
            blob_hash: str,
            parent_hash: Optional[str],
            author: str,
            message: str,
            metadata: Dict[str, Any],
            timestamp: datetime,
    ) -> str:
        ts_str = timestamp.isoformat()
        meta_str = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        raw_body = f"parent={parent_hash or ''}\nblob={blob_hash}\nauthor={author}\nmessage={message}\nmetadata={meta_str}\ntimestamp={ts_str}"
        header = f"commit {len(raw_body.encode('utf-8'))}\0"
        payload = (header + raw_body).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
