import importlib
import logging
import pkgutil


class ApplicationHelper:
    @staticmethod
    def import_modules(package):
        for (_, name, _) in pkgutil.iter_modules(package.__path__):
            try:
                importlib.import_module(f".{name}", package.__name__)
            except ImportError as exc:
                logging.warning(f"Skipping {name}: {exc}")
