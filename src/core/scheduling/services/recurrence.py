"""RFC 5545 recurrence expansion utilities.

Uses python-dateutil to expand RRULE strings into concrete datetime
occurrences. This avoids re-implementing the complex RFC 5545 logic
in-house; dateutil is the de-facto Python standard for this.
"""

from datetime import datetime

from dateutil.rrule import rrulestr


def expand_recurrence(
    rrule: str,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Expand an RRULE string into datetime occurrences within [start, end].

    Args:
        rrule:  RFC 5545 RRULE value, e.g. ``"FREQ=WEEKLY;BYDAY=MO"``.
                The ``"RRULE:"`` property prefix is optional.
        start:  Window start (inclusive).
        end:    Window end (inclusive).

    Returns:
        Sorted list of datetimes in [start, end].  Returns [] if end < start.
    """
    if end < start:
        return []

    # dateutil.rrulestr handles both bare RRULE strings and the
    # full "RRULE:..." property format.
    rule = rrulestr(rrule, dtstart=start, ignoretz=False)
    return list(rule.between(start, end, inc=True))
