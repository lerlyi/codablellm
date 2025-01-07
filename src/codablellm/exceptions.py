class CodableLLMError(Exception):
    pass


class ExtractorNotFound(CodableLLMError):
    pass

class TSParsingError(CodableLLMError):
    pass

class ExtraNotInstalled(CodableLLMError):
    pass
