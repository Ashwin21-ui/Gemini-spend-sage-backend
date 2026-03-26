"""Custom exceptions for consistent error handling across the application."""


class SpendSageException(Exception):
    """Base exception for all application errors."""
    
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class PDFExtractionError(SpendSageException):
    """Raised when PDF extraction or parsing fails."""
    pass


class EmbeddingError(SpendSageException):
    """Raised when embedding generation fails."""
    pass


class DatabaseError(SpendSageException):
    """Raised when database operations fail."""
    pass


class ValidationError(SpendSageException):
    """Raised when data validation fails."""
    pass


class InvalidUUIDError(ValidationError):
    """Raised when UUID format is invalid."""
    pass


class ResourceNotFoundError(SpendSageException):
    """Raised when a requested resource doesn't exist."""
    pass


class GeminiAPIError(SpendSageException):
    """Raised when Gemini API calls fail."""
    pass
