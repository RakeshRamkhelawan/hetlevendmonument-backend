
"""
Domain Exceptions
"""


class DomainException(Exception):
    """Base exception for all domain errors"""

    pass


class ValidationException(DomainException):
    """Raised when domain validation fails"""

    pass


class EntityNotFoundException(DomainException):
    """Raised when entity is not found"""

    pass


class BusinessRuleViolationException(DomainException):
    """Raised when business rule is violated"""

    pass
