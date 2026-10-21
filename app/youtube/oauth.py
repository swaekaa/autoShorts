"""
YouTube OAuth 2.0 Authorization
================================
One-time setup flow + token refresh for YouTube Data API v3.

Setup flow (run once from CLI):
    python scripts/youtube_auth.py

After authorization, YOUTUBE_REFRESH_TOKEN is stored and used for all uploads.
The service verifies channel identity before enabling public uploads.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from app.logging_config import get_logger

logger = get_logger(__name__)

# Minimum required scope for uploads
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]
# Broader scope needed to verify channel identity
YOUTUBE_READONLY_SCOPE = ["https://www.googleapis.com/auth/youtube.readonly"]
SCOPES = YOUTUBE_UPLOAD_SCOPE + YOUTUBE_READONLY_SCOPE


class YouTubeOAuth:
    """
    Manages YouTube OAuth 2.0 credentials.
    Automatically refreshes expired access tokens using the stored refresh token.
    """

    def __init__(self, settings: Any):
        self._settings = settings
        self._credentials: Credentials | None = None

    def get_credentials(self) -> Credentials:
        """
        Return valid credentials, refreshing if necessary.
        Raises if credentials are missing or cannot be refreshed.
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        if not self._settings.google_client_id or not self._settings.google_client_secret:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured. "
                "See README.md for setup instructions."
            )

        if not self._settings.youtube_refresh_token:
            raise RuntimeError(
                "YOUTUBE_REFRESH_TOKEN not set. "
                "Run scripts/youtube_auth.py to authorize your channel."
            )

        creds = Credentials(
            token=None,  # Will be refreshed
            refresh_token=self._settings.youtube_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret,
            scopes=SCOPES,
        )

        if not creds.valid:
            creds.refresh(Request())
            logger.info("YouTube access token refreshed")

        self._credentials = creds
        return creds

    def revoke_check(self) -> bool:
        """
        Check if the current credentials are still valid.
        Returns False if they have been revoked.
        """
        try:
            creds = self.get_credentials()
            return creds.valid
        except Exception as exc:
            logger.error(
                "Credential validation failed",
                extra={"error": str(exc)},
            )
            return False

    @staticmethod
    def run_one_time_auth(
        client_id: str,
        client_secret: str,
        port: int = 8090,
    ) -> str:
        """
        Run the OAuth flow to obtain a refresh token.
        Opens a browser for user authorization.
        Returns the refresh token string.

        Call from: scripts/youtube_auth.py
        """
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=port)

        if not creds.refresh_token:
            raise RuntimeError(
                "No refresh_token received. Ensure the OAuth consent screen "
                "is configured and the app is NOT in 'Testing' mode that "
                "restricts refresh token issuance. Try re-authorizing."
            )

        logger.info("YouTube OAuth authorization successful")
        return creds.refresh_token
