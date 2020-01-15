class SnarlError(Exception):
    pass


class RecursiveIncludeError(SnarlError):
    pass


class BlockArgumentError(SnarlError):
    pass
