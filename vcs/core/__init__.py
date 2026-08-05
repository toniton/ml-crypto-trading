from vcs.core.hashing import Hashing
from vcs.core.serializer import Serializer

serialize_canonical_json = Serializer.serialize_canonical_json
to_canonical_dict = Serializer.to_canonical_dict
compute_blob_hash = Hashing.compute_blob_hash
compute_commit_hash = Hashing.compute_commit_hash

__all__ = [
    "Serializer",
    "Hashing",
    "serialize_canonical_json",
    "to_canonical_dict",
    "compute_blob_hash",
    "compute_commit_hash",
]
