import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TimeseriesChunker:
    """
    Chunks sequential timeseries data into sliding windows.
    """

    def __init__(self, window_size: int = 60, stride: int = 30) -> None:
        self.window_size = window_size
        self.stride = stride

    def chunk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes timeseries dictionary into overlapping sliding window chunks.
        """
        timestamps = data.get("timestamps", [])
        values = data.get("values", [])
        machine_id = data.get("machine_id", "unknown")
        metric_name = data.get("metric_name", "unknown")

        if len(timestamps) != len(values):
            raise ValueError("timestamps and values arrays must have the same length")

        chunks = []
        n = len(timestamps)
        
        if n == 0:
            return {"chunks": []}

        if n < self.window_size:
            chunk_text = (
                f"Timeseries chunk for {metric_name} on machine {machine_id} "
                f"from {timestamps[0]} to {timestamps[-1]}. Values: {values}"
            )
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    "machine_id": machine_id,
                    "metric_name": metric_name,
                    "start_time": timestamps[0],
                    "end_time": timestamps[-1],
                    "chunk_index": 0,
                    "window_size": n
                }
            })
            logger.info("Produced 1 timeseries chunk.")
            return {"chunks": chunks}

        chunk_index = 0
        step = max(1, self.stride)
        
        for i in range(0, max(1, n - self.window_size + 1), step):
            window_ts = timestamps[i:i + self.window_size]
            window_vals = values[i:i + self.window_size]
            
            chunk_text = (
                f"Timeseries chunk for {metric_name} on machine {machine_id} "
                f"from {window_ts[0]} to {window_ts[-1]}. Values: {window_vals}"
            )
            
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    "machine_id": machine_id,
                    "metric_name": metric_name,
                    "start_time": window_ts[0],
                    "end_time": window_ts[-1],
                    "chunk_index": chunk_index,
                    "window_size": len(window_vals)
                }
            })
            chunk_index += 1

        logger.info("Produced %d timeseries chunks.", len(chunks))
        return {"chunks": chunks}
