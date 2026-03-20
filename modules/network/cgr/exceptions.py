class CGRError(Exception):
    """Base exception for CGR-related errors."""


class ContactPlanError(CGRError):
    """Base exception for contact-plan loading/validation errors."""


class ContactPlanFormatError(ContactPlanError):
    """Raised when the contact-plan payload shape is invalid."""


class ContactPlanValidationError(ContactPlanError):
    """Raised when contact-plan fields fail business validation."""
