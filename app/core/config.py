"""Environment-backed application configuration."""

import os
from urllib.parse import urlsplit

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()
    load_dotenv(".env.local", override=True)


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer without leaking the value in errors."""

    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")

    return value


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    """Read a comma-separated environment value."""

    return tuple(
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    )


class Settings:
    """Application settings shared by desktop and production modes."""

    database_path = "livetrigger.db"
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    app_version = os.getenv("APP_VERSION", "1.1.1").strip()
    update_repository = os.getenv(
        "UPDATE_REPOSITORY",
        "shahred94/Tbana",
    ).strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    subscription_api_url = (
        os.getenv("SUBSCRIPTION_API_URL", "").strip().rstrip("/")
    )
    secret_key = os.getenv("SECRET_KEY", "").strip()
    access_token_expire_minutes = _positive_int(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        43200,
    )
    allowed_origins = _csv("ALLOWED_ORIGINS")
    trusted_hosts = _csv(
        "TRUSTED_HOSTS",
        "127.0.0.1,localhost,api.tbanastream.com",
    )
    log_level = os.getenv("LOG_LEVEL", "info").strip().lower()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = _positive_int("SMTP_PORT", 587)
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls = os.getenv(
        "SMTP_USE_TLS",
        "true",
    ).strip().lower() not in {"false", "0", "no", "off"}
    smtp_use_ssl = os.getenv(
        "SMTP_USE_SSL",
        "false",
    ).strip().lower() in {"true", "1", "yes", "on"}
    toyyibpay_base_url = (
        os.getenv("TOYYIBPAY_BASE_URL", "https://dev.toyyibpay.com")
        .strip()
        .rstrip("/")
    )
    toyyibpay_category_code = os.getenv(
        "TOYYIBPAY_CATEGORY_CODE", ""
    ).strip()
    toyyibpay_secret_key = os.getenv(
        "TOYYIBPAY_SECRET_KEY", ""
    ).strip()
    toyyibpay_callback_url = os.getenv(
        "TOYYIBPAY_CALLBACK_URL", ""
    ).strip()
    toyyibpay_return_url = os.getenv(
        "TOYYIBPAY_RETURN_URL", ""
    ).strip()
    pro_price_cents = _positive_int("PRO_PRICE_CENTS", 2990)
    pro_duration_days = _positive_int("PRO_DURATION_DAYS", 30)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://"))

    @property
    def is_remote_desktop(self) -> bool:
        return bool(self.subscription_api_url)

    @property
    def secure_cookie(self) -> bool:
        return (
            not self.is_remote_desktop
            and self.public_base_url.lower().startswith("https://")
        )

    @property
    def email_enabled(self) -> bool:
        return bool(
            self.smtp_host
            and
            self.smtp_from_email
        )

    @property
    def payment_site_url(self) -> str:
        parsed = urlsplit(self.toyyibpay_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise RuntimeError("TOYYIBPAY_BASE_URL must be an absolute URL.")
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def payment_callback_url(self) -> str:
        return (
            self.toyyibpay_callback_url
            or f"{self.public_base_url}/api/payment/callback"
        )

    @property
    def payment_return_url(self) -> str:
        return (
            self.toyyibpay_return_url
            or f"{self.public_base_url}/api/payment/return"
        )

    @staticmethod
    def _require_absolute_url(name: str, value: str) -> None:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"{name} must be an absolute HTTP(S) URL.")

    def require_payment_settings(self) -> None:
        missing = [
            name
            for name, value in (
                ("PUBLIC_BASE_URL", self.public_base_url),
                ("TOYYIBPAY_CATEGORY_CODE", self.toyyibpay_category_code),
                ("TOYYIBPAY_SECRET_KEY", self.toyyibpay_secret_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing payment configuration: " + ", ".join(missing)
            )
        self._require_absolute_url(
            "TOYYIBPAY_CALLBACK_URL",
            self.payment_callback_url,
        )
        self._require_absolute_url(
            "TOYYIBPAY_RETURN_URL",
            self.payment_return_url,
        )

    def require_production_settings(self) -> None:
        """Fail early when required self-host settings are unsafe or absent."""

        if self.app_env != "production":
            raise RuntimeError("APP_ENV must be production.")
        if not self.is_postgres:
            raise RuntimeError(
                "Production API requires a PostgreSQL DATABASE_URL."
            )
        if self.subscription_api_url:
            raise RuntimeError(
                "SUBSCRIPTION_API_URL is desktop-only and must not be set "
                "on the production API server."
            )
        if len(self.secret_key) < 32:
            raise RuntimeError(
                "SECRET_KEY must contain at least 32 characters."
            )
        if not self.public_base_url:
            raise RuntimeError("PUBLIC_BASE_URL is required.")
        self._require_absolute_url("PUBLIC_BASE_URL", self.public_base_url)
        if not self.trusted_hosts:
            raise RuntimeError("TRUSTED_HOSTS must contain at least one host.")


settings = Settings()
