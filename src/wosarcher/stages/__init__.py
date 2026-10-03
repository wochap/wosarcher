"""Pure pipeline stages: values and ports in, a model out."""


def noop(_item: object) -> None:
    """The default item callback: does nothing."""
