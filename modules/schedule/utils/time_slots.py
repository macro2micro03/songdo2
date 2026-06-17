"""Time slot utilities."""


def slots_overlap(a_from, a_to, b_from, b_to):
    return a_from < b_to and b_from < a_to
