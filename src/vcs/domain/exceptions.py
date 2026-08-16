class VcsError(Exception):
    """Base exception for all VCS domain errors."""


class BlobNotFoundError(VcsError):
    """Raised when a blob hash is not found in the object store."""

    def __init__(self, blob_hash: str):
        super().__init__(f"Blob with hash '{blob_hash}' not found.")
        self.blob_hash = blob_hash


class CommitNotFoundError(VcsError):
    """Raised when a commit hash is not found in the object store."""

    def __init__(self, commit_hash: str):
        super().__init__(f"Commit with hash '{commit_hash}' not found.")
        self.commit_hash = commit_hash


class ReferenceNotFoundError(VcsError):
    """Raised when a reference name is not found in the object store."""

    def __init__(self, name: str):
        super().__init__(f"Reference '{name}' not found.")
        self.name = name


class InvalidReferenceError(VcsError):
    """Raised when a target commit hash or ref is invalid."""
