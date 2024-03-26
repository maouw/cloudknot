"""Custom validators for pydantic models."""

import typing
from typing import Any

__all__ = ["box_iterable"]


def box_iterable(
    x: Any, t: Any, box: typing.Optional[type] = None, make_unique=False
) -> Any:
    """Validate that a value is of a certain type."""
    origin = typing.get_origin(t)
    args = typing.get_args(t)
    print(f"{origin=}, {args=}")
    if box and isinstance(x, args):
        x = box((x,))

    if origin and not isinstance(x, origin):
        raise TypeError(f"{x} is not a {origin}")

    if args:
        for el in x:
            if not isinstance(el, args):
                raise TypeError(f"Type of element {el} is not in {args}")
    if box and make_unique:
        x = box(dict.fromkeys(x))
    return x
