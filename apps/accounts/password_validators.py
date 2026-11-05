from django.core.exceptions import ValidationError


class PasswordCompositionValidator:
    """Require the password components shown in the account interfaces."""

    def validate(self, password, user=None):
        failures = []
        if not any(character.isupper() for character in password):
            failures.append("Include at least one uppercase letter.")
        if not any(character.islower() for character in password):
            failures.append("Include at least one lowercase letter.")
        if not any(character.isdigit() for character in password):
            failures.append("Include at least one number.")
        if not any(not character.isalnum() for character in password):
            failures.append("Include at least one special symbol.")
        if failures:
            raise ValidationError(failures, code="password_composition")

    def get_help_text(self):
        return "Use uppercase and lowercase letters, a number, and a special symbol."
