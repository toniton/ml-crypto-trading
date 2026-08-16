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
            if field == 'timestamp':
                val = getattr(record, 'timestamp', int(record.created * 1000))
            else:
                val = getattr(record, field, '')
            row.append(val)

        writer.writerow(row)
        return sio.getvalue()
