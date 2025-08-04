from datetime import datetime, timedelta
from enum import Enum
from typing import List


class Weekday(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


def get_weekend_dates(target_date: str) -> List[str]:
    """
    Get the list of dates to process based on weekend logic.

    Args:
        target_date: Date in DD/MM/YYYY format

    Returns:
        List of dates to process (current date + weekend dates if applicable)
    """
    # Parse the target date
    date_obj = datetime.strptime(target_date, "%d/%m/%Y")
    weekday = date_obj.weekday()

    dates_to_process = [target_date]

    # If it's Friday, add Saturday, Sunday, and Monday
    if weekday == Weekday.FRIDAY.value:
        for i in range(1, 4):  # Saturday, Sunday, Monday
            next_date = date_obj + timedelta(days=i)
            dates_to_process.append(next_date.strftime("%d/%m/%Y"))

    # If it's Saturday, add Sunday and Monday
    elif weekday == Weekday.SATURDAY.value:
        for i in range(1, 3):  # Sunday, Monday
            next_date = date_obj + timedelta(days=i)
            dates_to_process.append(next_date.strftime("%d/%m/%Y"))

    # If it's Sunday, add Monday
    elif weekday == Weekday.SUNDAY.value:
        next_date = date_obj + timedelta(days=1)  # Monday
        dates_to_process.append(next_date.strftime("%d/%m/%Y"))

    return dates_to_process
