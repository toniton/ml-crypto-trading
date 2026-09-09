import importlib
import pkgutil

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class DaoHelper:
    DATABASE_DAO_DIR = "database/dao"

    @staticmethod
    def load_classes():
        for _, name, _ in pkgutil.iter_modules([DaoHelper.DATABASE_DAO_DIR]):
            importlib.import_module(
                "." + name, DaoHelper.DATABASE_DAO_DIR.replace("/", ".")
            )

        for cls in SqlAlchemyDatabaseManager.BaseTableModel.__subclasses__():
            cls()
