"""TikTok Live Activity Log Manager."""

from datetime import datetime


MAX_LOGS = 500


logs = []


def add_log(
    message,
    log_type="SYSTEM",
):

    """Add new activity log."""

    timestamp = datetime.now().strftime(
        "%H:%M:%S"
    )


    logs.insert(
        0,
        {
            "time": timestamp,
            "type": log_type,
            "message": message,
        }
    )


    if len(logs) > MAX_LOGS:

        logs.pop()


def get_logs():

    """Get all activity logs."""

    return logs


def clear_logs():

    """Clear all activity logs."""

    logs.clear()