# adblock_processor/utils/exceptions.py

class AdblockProcessorError(Exception):
    """Base class for exceptions in this application."""
    pass

class ConfigError(AdblockProcessorError):
    """Exception raised for errors in the configuration."""
    pass

class DownloadError(AdblockProcessorError):
    """Exception raised for errors during list downloading."""
    pass

class ParsingError(AdblockProcessorError):
    """Exception raised for errors during rule parsing."""
    pass

class ValidationError(AdblockProcessorError):
    """Exception raised for errors during rule validation."""
    pass

class TranslationError(AdblockProcessorError):
    """Exception raised for errors during rule translation."""
    pass

class GenerationError(AdblockProcessorError):
    """Exception raised for errors during list generation."""
    pass

class SyntaxDBError(AdblockProcessorError):
    """Exception raised for errors related to the syntax pattern database."""
    pass
