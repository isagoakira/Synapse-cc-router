"""
Experiment data query tool.
"""

import asyncio
from pathlib import Path
from typing import Optional


async def query_experiment_data(experiment: str, metric: Optional[str] = None) -> dict:
    """
    Query experiment results from shared data directory.
    """
    await asyncio.sleep(0.05)

    possible_paths = [
        Path(f"~/experiments/{experiment}").expanduser(),
        Path(f"~/data/experiments/{experiment}").expanduser(),
        Path(f"/tmp/experiments/{experiment}").expanduser(),
    ]

    for exp_path in possible_paths:
        if exp_path.exists():
            return {
                "status": "ok",
                "experiment": experiment,
                "path": str(exp_path),
                "metric": metric,
                "data": {"message": "Experiment data found"},
                "found": True,
            }

    return {
        "status": "ok",
        "experiment": experiment,
        "metric": metric,
        "data": None,
        "found": False,
        "message": "Experiment data not found",
    }
