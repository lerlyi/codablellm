from codablellm.core import SourceFunction

def transform(f: SourceFunction) -> SourceFunction:
    return f.with_definition(f.definition.replace('Main app', 'My app'))