"""Safe metadata-export failures that do not imply uncertain container cleanup."""


class HistoryError(ValueError):
    """History capture was refused before export; execution outcome is separate.

    The stable code contains no database contents or credential values. This
    failure cannot authorize replay or relabel an uncertain tool outcome.
    """

    def __init__(self, code):
        self.code = code
        super().__init__(code)
