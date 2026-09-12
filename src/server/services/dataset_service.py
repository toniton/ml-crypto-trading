from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, List, Optional


@dataclass(frozen=True)
class DatasetMetadata:
    id: str
    filename: str
    row_count: int
    start_time: str
    end_time: str
    file_size_bytes: int
    sha256: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DatasetValidationError(ValueError):
    pass


class DatasetService:
    def __init__(self, storage_dir: str = "data/datasets") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def list_datasets(self) -> List[DatasetMetadata]:
        results: List[DatasetMetadata] = []
        for meta_file in sorted(self._storage_dir.glob("*.meta.json"), reverse=True):
            try:
                import json
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append(DatasetMetadata(**data))
            except Exception:
                continue
        return results

    def get_dataset(self, dataset_id: str) -> Optional[DatasetMetadata]:
        meta_file = self._storage_dir / f"{dataset_id}.meta.json"
        if not meta_file.exists():
            return None
        import json
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return DatasetMetadata(**data)

    def get_dataset_csv_path(self, dataset_id: str) -> Optional[str]:
        csv_file = self._storage_dir / f"{dataset_id}.csv"
        if csv_file.exists():
            return str(csv_file)
        return None

    def validate_and_save_csv(self, filename: str, content: bytes) -> DatasetMetadata:
        if not content:
            raise DatasetValidationError("Dataset file is empty.")

        text_content = content.decode("utf-8-sig")
        lines = [line.strip() for line in text_content.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            raise DatasetValidationError("CSV must contain a header row and at least one data row.")

        # Detect delimiter (comma vs semicolon vs tab)
        header_line = lines[0]
        delimiter = ";" if ";" in header_line and header_line.count(";") >= header_line.count(",") else ","

        reader = csv.DictReader(lines, delimiter=delimiter)
        required_headers = {"timestamp", "open", "high", "low", "close", "volume"}
        fieldnames = {f.strip().lower() for f in (reader.fieldnames or []) if f}
        missing_headers = required_headers - fieldnames
        if missing_headers:
            raise DatasetValidationError(f"Missing required CSV columns: {sorted(missing_headers)}")

        parsed_rows: list[dict[str, Any]] = []
        seen_timestamps: set[int] = set()

        for row_index, row in enumerate(reader, start=2):
            norm_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v is not None}
            ts_str = norm_row.get("timestamp")
            if not ts_str:
                raise DatasetValidationError(f"Row {row_index}: Missing timestamp.")

            try:
                if ts_str.isdigit():
                    ts_val = int(ts_str)
                    ts_dt = datetime.fromtimestamp(ts_val / 1000 if ts_val > 10**11 else ts_val, tz=timezone.utc)
                else:
                    ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                    else:
                        ts_dt = ts_dt.astimezone(timezone.utc)
            except Exception as exc:
                raise DatasetValidationError(f"Row {row_index}: Invalid timestamp format '{ts_str}'.") from exc

            ts_epoch = int(ts_dt.timestamp())
            if ts_epoch in seen_timestamps:
                raise DatasetValidationError(
                    f"Row {row_index}: Duplicate timestamp detected ({ts_dt.isoformat()})."
                )
            seen_timestamps.add(ts_epoch)

            try:
                open_p = Decimal(norm_row["open"])
                high_p = Decimal(norm_row["high"])
                low_p = Decimal(norm_row["low"])
                close_p = Decimal(norm_row["close"])
                volume_v = Decimal(norm_row["volume"])
            except (InvalidOperation, KeyError) as exc:
                raise DatasetValidationError(f"Row {row_index}: Invalid numeric OHLCV values.") from exc

            if volume_v < 0:
                raise DatasetValidationError(f"Row {row_index}: Volume cannot be negative.")
            if high_p < low_p:
                raise DatasetValidationError(f"Row {row_index}: High price ({high_p}) cannot be lower than Low ({low_p}).")
            if open_p < low_p or open_p > high_p:
                raise DatasetValidationError(f"Row {row_index}: Open price ({open_p}) is outside [Low, High] range.")
            if close_p < low_p or close_p > high_p:
                raise DatasetValidationError(f"Row {row_index}: Close price ({close_p}) is outside [Low, High] range.")

            parsed_rows.append({
                "timestamp_dt": ts_dt,
                "timestamp": ts_dt.isoformat(),
                "open": str(open_p),
                "high": str(high_p),
                "low": str(low_p),
                "close": str(close_p),
                "volume": str(volume_v),
            })

        if not parsed_rows:
            raise DatasetValidationError("Dataset contains no valid data rows.")

        # Sort chronologically by timestamp
        parsed_rows.sort(key=lambda x: x["timestamp_dt"])

        # Write normalized standard comma-separated CSV with exact required columns
        dataset_id = uuid.uuid4().hex[:12]
        csv_path = self._storage_dir / f"{dataset_id}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for r in parsed_rows:
                writer.writerow([r["timestamp"], r["open"], r["high"], r["low"], r["close"], r["volume"]])

        # Calculate normalized file SHA-256 and size
        with open(csv_path, "rb") as f:
            norm_content = f.read()
        sha256_hash = hashlib.sha256(norm_content).hexdigest()

        metadata = DatasetMetadata(
            id=dataset_id,
            filename=filename,
            row_count=len(parsed_rows),
            start_time=parsed_rows[0]["timestamp"],
            end_time=parsed_rows[-1]["timestamp"],
            file_size_bytes=len(norm_content),
            sha256=sha256_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        meta_path = self._storage_dir / f"{dataset_id}.meta.json"
        import json
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        return metadata
