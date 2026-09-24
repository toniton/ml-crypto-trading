import io
import csv
import logging


class AuditCsvFormatter(logging.Formatter):
    def __init__(self, header: list[str]):
        super().__init__()
        self.header = header

    def format(self, record: logging.LogRecord) -> str:
        sio = io.StringIO()
        writer = csv.writer(sio)

        row = []
        for field in self.header:
            if field == "timestamp":
                try:
                    val = record.__dict__["timestamp"]
                except KeyError:
                    val = int(record.created * 1000)
            else:
                try:
                    val = record.__dict__[field]
                except (KeyError, AttributeError):
                    val = ""
            row.append(val)

        writer.writerow(row)
        return sio.getvalue()
