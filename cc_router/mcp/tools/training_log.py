"""
Training log reading tool.
"""

from pathlib import Path


async def read_training_log(workspace: str, pattern: str = "*.log") -> dict:
    """
    Read ML training log files.
    """
    workspace_path = Path(workspace)

    if not workspace_path.exists():
        return {"status": "error", "message": f"Workspace not found: {workspace}", "logs": []}

    log_files = list(workspace_path.glob(pattern))
    logs = []
    for log_file in log_files:
        try:
            content = log_file.read_text()
            logs.append({"file": str(log_file), "size": len(content), "preview": content[:500]})
        except Exception as e:
            logs.append({"file": str(log_file), "error": str(e)})

    return {
        "status": "ok",
        "workspace": workspace,
        "pattern": pattern,
        "logs": logs,
        "count": len(logs),
    }
