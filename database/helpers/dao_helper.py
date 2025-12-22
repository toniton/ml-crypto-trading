import importlib
import pkgutil

from database.database_manager import DatabaseManager


class DaoHelper:
    DATABASE_DAO_DIR = "database/dao"

    @staticmethod
    def load_classes():
        for _, name, _ in pkgutil.iter_modules([DaoHelper.DATABASE_DAO_DIR]):
            importlib.import_module(
                "." + name, DaoHelper.DATABASE_DAO_DIR.replace("/", ".")
            )

        for cls in DatabaseManager.BaseTableModel.__subclasses__():
            cls()
