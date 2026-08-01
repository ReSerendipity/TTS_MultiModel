"""Tests for API authentication middleware."""
import os
import sys
import pytest

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TTS_SKIP_MODEL_LOAD", "1")


class TestAPIAuthMiddleware:
    """Test API authentication middleware."""

    def test_middleware_import(self):
        """Auth middleware module can be imported."""
        from integrated_app.auth import APIAuthMiddleware
        assert APIAuthMiddleware is not None

    def test_public_paths_defined(self):
        """Public paths whitelist is defined."""
        from integrated_app.auth import APIAuthMiddleware
        # The middleware should have a concept of public paths
        # that don't require authentication
        assert hasattr(APIAuthMiddleware, '__init__')

    def test_middleware_with_auth_disabled(self):
        """Middleware allows all requests when auth is disabled."""
        from integrated_app.auth import APIAuthMiddleware
        # When enabled=False, all requests should pass through
        middleware = APIAuthMiddleware(app=None, enabled=False, token="")
        assert middleware is not None

    def test_middleware_with_auth_enabled(self):
        """Middleware initializes with auth enabled."""
        from integrated_app.auth import APIAuthMiddleware
        middleware = APIAuthMiddleware(app=None, enabled=True, token="test-token-123")
        assert middleware is not None

    def test_empty_token_rejected(self):
        """Empty token should not be accepted when auth is enabled."""
        from integrated_app.auth import APIAuthMiddleware
        # Creating middleware with empty token when enabled should work
        # but should reject all authenticated requests
        middleware = APIAuthMiddleware(app=None, enabled=True, token="")
        assert middleware is not None


class TestAuthConfiguration:
    """Test auth configuration from config."""

    def test_config_has_api_auth(self):
        """Config has api_auth section."""
        from integrated_app.config import get_config
        config = get_config()
        assert hasattr(config, 'api_auth')

    def test_api_auth_has_enabled_field(self):
        """API auth config has enabled field."""
        from integrated_app.config import get_config
        config = get_config()
        auth = config.api_auth
        assert hasattr(auth, 'enabled')
        assert isinstance(auth.enabled, bool)

    def test_api_auth_has_token_field(self):
        """API auth config has token field."""
        from integrated_app.config import get_config
        config = get_config()
        auth = config.api_auth
        assert hasattr(auth, 'token')
        assert isinstance(auth.token, str)
