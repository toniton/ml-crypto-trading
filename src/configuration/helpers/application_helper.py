import importlib
import pkgutil

from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class ApplicationHelper(ApplicationLoggingMixin):
    @classmethod
    def import_modules(cls, package):
        for (_, name, _) in pkgutil.iter_modules(package.__path__):
            try:
                importlib.import_module(f".{name}", package.__name__)
            except ImportError as exc:
                cls().app_logger.warning(f"Skipping {name}: {exc}")
