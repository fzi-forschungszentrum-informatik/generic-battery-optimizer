import pandas as pd


def get_period_length(period: pd.Timestamp, index: pd.DatetimeIndex):
    """Gets duration of models period

    Arguments:
    ----------
        period: pd.Timestamp
            The period to get the duration of
        index: pd.DatetimeIndex
            The index of the model
    Returns:
    --------
        period_length: pd.Timedelta
            The duration of the period
        period_conversion_factor: float
            The conversion factor of the period to hours
    """
    if period == index.last():
        period_length = 0
        period_conversion_factor = 1
    else:
        period_length = index.next(period) - period
        period_conversion_factor = period_length.total_seconds() / 3600
    return period_length, period_conversion_factor

