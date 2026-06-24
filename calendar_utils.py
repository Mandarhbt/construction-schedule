from datetime import timedelta


def is_working_day(date, working_days, holidays):

    day_name = date.strftime("%A")

    if day_name not in working_days:
        return False

    if date.strftime("%Y-%m-%d") in holidays:
        return False

    return True


def add_working_days(
    start_date,
    duration,
    working_days,
    holidays
):

    current_date = start_date

    days_counted = 1

    while days_counted < duration:

        current_date += timedelta(days=1)

        if is_working_day(
            current_date,
            working_days,
            holidays
        ):
            days_counted += 1

    return current_date


def next_working_day(
    date,
    working_days,
    holidays
):

    next_date = date + timedelta(days=1)

    while not is_working_day(
        next_date,
        working_days,
        holidays
    ):
        next_date += timedelta(days=1)

    return next_date