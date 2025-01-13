'''
Exceptions related to codablellm.
'''

class CodableLLMError(Exception):
    '''
    Base exception class for all CodableLLM errors.
    '''


class ExtractorNotFound(CodableLLMError):
    '''
    A source code extractor could not be imported.
    '''

class DecompilerNotFound(CodableLLMError):
    '''
    A decompiler could not be imported.
    '''

class TSParsingError(CodableLLMError):
    '''
    A tree-sitter parsing error occurred.
    '''


class ExtraNotInstalled(CodableLLMError):
    '''
    An extra is not installed to perform an optional feature.
    '''
