import csv
import logging
import logging.handlers
import os
import threading
import uuid
from datetime import datetime
from typing import Optional

from src.configuration.environment_config import EnvironmentConfig
from src.core.logging.domain import LogDomain
from src.core.logging.formatters import AuditCsvFormatter


class LoggingManager:
    _instance: Optional['LoggingManager'] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[EnvironmentConfig] = None):
        self.instance_id = uuid.uuid4().hex[:8]
        self._config = config or EnvironmentConfig()
        self.log_dir = self._config.log_dir
        self.log_level = self._config.log_level or 'INFO'
        self.current_month = datetime.now().strftime('%Y-%m')
        self.standard_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        self._setup_complete = False
        self._setup_lock = threading.Lock()
        self.active_loggers: set[str] = set()

        os.makedirs(self.log_dir, exist_ok=True)

    @classmethod
    def get_instance(cls, config: Optional[EnvironmentConfig] = None) -> 'LoggingManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)

        instance = cls._instance
        if config is not None:
            with instance.get_setup_lock():
                if instance.get_config() != config:
                    instance.set_config(config)

        return instance

    def get_setup_lock(self) -> threading.Lock:
        return self._setup_lock

    def get_config(self) -> EnvironmentConfig:
        return self._config

    def set_config(self, config: EnvironmentConfig) -> None:
        self._config = config
        self.log_dir = config.log_dir
        self.log_level = config.log_level or 'INFO'
        self._setup_complete = False
        os.makedirs(self.log_dir, exist_ok=True)

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            if cls._instance:
                instance = cls._instance
                with instance.get_setup_lock():
                    for logger_name in list(instance.active_loggers):
                        logger = logging.getLogger(logger_name)
                        for handler in logger.handlers[:]:
                            handler.close()
                            logger.removeHandler(handler)
                        logger.setLevel(logging.NOTSET)
                    instance.active_loggers.clear()
                    cls._instance = None

            root = logging.getLogger()
            for handler in root.handlers[:]:
                handler.close()
                root.removeHandler(handler)
            root.setLevel(logging.WARNING)
            logging.disable(logging.NOTSET)

    def setup_logging(self) -> None:
        with self._setup_lock:
            if self._setup_complete:
                return

            self._setup_domain_logger(LogDomain.APPLICATION, self.log_level)
            self._setup_domain_logger(LogDomain.TRADING, self.log_level)
            self._setup_audit_logger()

            self._setup_complete = True

    def get_log_file_path(self, domain: str, asset: Optional[str] = None) -> str:
        if asset:
            # Sanitize asset name for filesystem
            safe_asset = asset.replace('/', '_').replace('\\', '_')
            return os.path.join(self.log_dir, f'{domain}-{safe_asset}-{self.current_month}.log')
        return os.path.join(self.log_dir, f'{domain}-{self.current_month}.log')

    def _setup_domain_logger(self, domain: LogDomain, level: str) -> None:
        logger_name = f"{domain.value}.{self.instance_id}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper()))
        logger.propagate = False

        # Add file handler
        file_path = self.get_log_file_path(domain.value)
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(self.standard_format))
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(self.standard_format))
        logger.addHandler(console_handler)

        self.active_loggers.add(logger_name)

    def _setup_audit_logger(self, asset: Optional[str] = None) -> logging.Logger:
        domain = LogDomain.AUDIT.value
        logger_name = f"{domain}.{self.instance_id}"
        if asset:
            logger_name = f"{logger_name}.{asset}"

        logger = logging.getLogger(logger_name)

        # If already setup, return it
        if logger_name in self.active_loggers:
            return logger

        logger.setLevel(logging.INFO)
        logger.propagate = False

        file_path = self.get_log_file_path(domain, asset)

        # Ensure header exists if file is new
        header = [
            'timestamp', 'asset', 'event_type', 'action',
            'close_price', 'high_price', 'low_price', 'volume', 'context'
        ]

        file_exists = os.path.exists(file_path)
        if not file_exists or os.path.getsize(file_path) == 0:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, lineterminator='\n')
                writer.writerow(header)

        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setFormatter(AuditCsvFormatter(header))
        logger.addHandler(file_handler)

        self.active_loggers.add(logger_name)
        return logger

    def get_logger(self, domain: LogDomain, name: Optional[str] = None, asset: Optional[str] = None) -> logging.Logger:
        self.setup_logging()

        if domain == LogDomain.AUDIT:
            return self._setup_audit_logger(asset)

        logger_name = f"{domain.value}.{self.instance_id}"
        if name:
            logger_name = f'{logger_name}.{name}'

        return logging.getLogger(logger_name)
