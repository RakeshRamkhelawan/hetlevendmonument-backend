"""
SC-12.2: Internationalization (i18n) Setup
Provides multi-language support for the application.
"""

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Current language context
current_language: ContextVar[str] = ContextVar("current_language", default="en")


class I18n:
    """
    SC-12.2: Internationalization support.

    Features:
    - JSON-based translation files
    - Fallback to default language
    - Pluralization support
    - Variable interpolation
    """

    DEFAULT_LANGUAGE = "en"
    SUPPORTED_LANGUAGES = ["en", "nl", "hi", "sa"]  # English, Dutch, Hindi, Sanskrit

    def __init__(self, translations_dir: str | None = None) -> None:
        self.translations_dir = Path(
            translations_dir or Path(__file__).parent.parent / "translations"
        )
        self.translations: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._load_translations()

    def _load_translations(self) -> None:
        """Load all translation files."""
        self.translations_dir.mkdir(parents=True, exist_ok=True)

        for lang in self.SUPPORTED_LANGUAGES:
            file_path = self.translations_dir / f"{lang}.json"
            if file_path.exists():
                try:
                    with open(file_path, encoding="utf-8") as f:
                        self.translations[lang] = json.load(f)
                    logger.info(f"Loaded translations for: {lang}")
                except Exception as e:
                    logger.error(f"Failed to load translations for {lang}: {e}")
                    self.translations[lang] = {}
            else:
                # Create default file
                self.translations[lang] = {}
                self._save_translation(lang)

    def _save_translation(self, lang: str) -> None:
        """Save translations to file."""
        file_path = self.translations_dir / f"{lang}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.translations.get(lang, {}), f, indent=2, ensure_ascii=False)

    def t(
        self,
        key: str,
        lang: str | None = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Translate a key.

        Args:
            key: Translation key (dot-notation supported)
            lang: Language code (uses context if not provided)
            count: For pluralization
            **kwargs: Variables for interpolation

        Returns:
            Translated string
        """
        lang = lang or current_language.get() or self.DEFAULT_LANGUAGE

        # Get translation
        value = self._get_nested(self.translations.get(lang, {}), key)

        # Fallback to default language
        if value is None and lang != self.DEFAULT_LANGUAGE:
            value = self._get_nested(self.translations.get(self.DEFAULT_LANGUAGE, {}), key)

        # Return key if not found
        if value is None:
            logger.warning(f"Missing translation: {key} ({lang})")
            return key

        # Handle pluralization
        if isinstance(value, dict) and count is not None:
            if count == 0 and "zero" in value:
                value = value["zero"]
            elif count == 1 and "one" in value:
                value = value["one"]
            elif "many" in value:
                value = value["many"]
            else:
                value = value.get("other", str(value))

        # Interpolate variables
        if isinstance(value, str) and kwargs:
            try:
                value = value.format(**kwargs, count=count)
            except KeyError as e:
                logger.warning(f"Missing interpolation variable: {e}")

        return str(value) if not isinstance(value, str) else value

    def _get_nested(self, data: dict[str, Any], key: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get nested value using dot notation."""
        keys = key.split(".")
        value = data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None

        return value

    def add_translation(self, lang: str, key: str, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add or update a translation."""
        if lang not in self.translations:
            self.translations[lang] = {}

        keys = key.split(".")
        current = self.translations[lang]

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        self._save_translation(lang)

    def get_available_languages(self) -> list[str]:
        """Get list of available languages."""
        return list(self.translations.keys())


# Create default translation files
DEFAULT_TRANSLATIONS = {
    "en": {
        "common": {
            "welcome": "Welcome",
            "login": "Login",
            "logout": "Logout",
            "save": "Save",
            "cancel": "Cancel",
            "delete": "Delete",
            "confirm": "Confirm",
            "loading": "Loading...",
            "error": "An error occurred",
            "success": "Success",
        },
        "auth": {
            "login_title": "Sign In",
            "login_button": "Sign In",
            "register_title": "Create Account",
            "forgot_password": "Forgot Password?",
            "invalid_credentials": "Invalid email or password",
        },
        "errors": {
            "not_found": "Page not found",
            "unauthorized": "You are not authorized to view this page",
            "server_error": "Something went wrong. Please try again.",
        },
        "items": {"zero": "No items", "one": "{count} item", "many": "{count} items"},
    },
    "nl": {
        "common": {
            "welcome": "Welkom",
            "login": "Inloggen",
            "logout": "Uitloggen",
            "save": "Opslaan",
            "cancel": "Annuleren",
            "delete": "Verwijderen",
            "confirm": "Bevestigen",
            "loading": "Laden...",
            "error": "Er is een fout opgetreden",
            "success": "Gelukt",
        },
        "auth": {
            "login_title": "Inloggen",
            "login_button": "Inloggen",
            "register_title": "Account Aanmaken",
            "forgot_password": "Wachtwoord vergeten?",
            "invalid_credentials": "Ongeldige e-mail of wachtwoord",
        },
    },
    "hi": {
        "common": {
            "welcome": "[U+0938][U+094D][U+0935][U+093E][U+0917][U+0924]",
            "login": "[U+0932][U+0949][U+0917][U+093F][U+0928]",
            "logout": "[U+0932][U+0949][U+0917][U+0906][U+0909][U+091F]",
            "save": "[U+0938][U+0939][U+0947][U+091C][U+0947][U+0902]",
            "cancel": "[U+0930][U+0926][U+094D][U+0926] [U+0915][U+0930][U+0947][U+0902]",
        }
    },
}


def create_default_translations(i18n: I18n) -> None:
    """Populate default translations."""
    for lang, translations in DEFAULT_TRANSLATIONS.items():
        for key, value in _flatten_dict(translations).items():
            i18n.add_translation(lang, key, value)


def _flatten_dict(d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Flatten nested dict to dot-notation keys."""
    items: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict) and not any(k in v for k in ["zero", "one", "many", "other"]):
            items.update(_flatten_dict(v, new_key))
        else:
            items[new_key] = v
    return items


# Singleton instance
i18n = I18n()


# Convenience function
def t(key: str, **kwargs: Any) -> str:
    """Translate a key."""
    return i18n.t(key, **kwargs)


def set_language(lang: str) -> None:
    """Set the current language."""
    current_language.set(lang)
