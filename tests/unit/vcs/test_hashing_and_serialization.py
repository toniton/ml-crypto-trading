from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.vcs.core.hashing import Hashing
from src.vcs.core.serializer import Serializer


class SampleSubConfig(BaseModel):
    temperature: float = 0.5
    model_name: str = "llama"


class SampleConfig(BaseModel):
    b_field: str = "world"
    a_field: str = "hello"
    sub: SampleSubConfig = Field(default_factory=SampleSubConfig)


def test_canonical_json_key_sorting():
    config1 = SampleConfig(a_field="hello", b_field="world")
    config2_dict = {"b_field": "world", "a_field": "hello", "sub": {"model_name": "llama", "temperature": 0.5}}

    canonical1 = Serializer.serialize_canonical_json(config1)
    canonical2 = Serializer.serialize_canonical_json(config2_dict)

    # Keys must be ordered alphabetically
    assert canonical1 == canonical2
    assert canonical1 == '{"a_field":"hello","b_field":"world","sub":{"model_name":"llama","temperature":0.5}}'


def test_blob_hash_determinism():
    config1 = SampleConfig()
    config2_dict = {"a_field": "hello", "b_field": "world", "sub": {"temperature": 0.5, "model_name": "llama"}}

    hash1 = Hashing.compute_blob_hash(config1)
    hash2 = Hashing.compute_blob_hash(config2_dict)

    assert hash1 == hash2
    assert len(hash1) == 64  # Hex-encoded SHA-256


def test_commit_hash_determinism():
    blob_h = "a" * 64
    ts = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)

    commit_hash_1 = Hashing.compute_commit_hash(
        blob_hash=blob_h,
        parent_hash=None,
        author="toni",
        message="Initial commit",
        metadata={"env": "production"},
        timestamp=ts,
    )

    commit_hash_2 = Hashing.compute_commit_hash(
        blob_hash=blob_h,
        parent_hash=None,
        author="toni",
        message="Initial commit",
        metadata={"env": "production"},
        timestamp=ts,
    )

    assert commit_hash_1 == commit_hash_2
    assert len(commit_hash_1) == 64
