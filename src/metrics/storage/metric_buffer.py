from __future__ import annotations

from src.metrics.models.metric_sample import MetricSample


class MetricBuffer:
    def __init__(self) -> None:
        self._samples: list[MetricSample] = []

    def append(self, sample: MetricSample) -> None:
        self._samples.append(sample)

    def drain(self) -> list[MetricSample]:
        samples = self._samples
        self._samples = []
        return samples

    def __len__(self) -> int:
        return len(self._samples)
