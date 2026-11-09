"""Abstract base class for installation steps."""

from abc import ABC, abstractmethod
from installer.context import InstallerContext


class BaseStep(ABC):
    """Encapsulates a single distinct phase of the installation process."""

    @property
    @abstractmethod
    def name(self) -> str:
        """User-facing step title."""
        pass

    @abstractmethod
    def run(self, context: InstallerContext) -> bool:
        """Executes the step. Returns True on success, False on failure."""
        pass
