"""Alerts: tell people when data quality drops.

Two channels are supported, both optional and set in the .env file:

* Telegram  (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
* Webhook   (ALERT_WEBHOOK_URL, for Slack, Teams or similar; receives {"text": "..."})

Only the Python standard library is used, so there is nothing extra to install.
Secrets are never printed or returned in error messages.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from core import config


def configured_channels() -> list[str]:
    channels = []
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        channels.append("Telegram")
    if config.ALERT_WEBHOOK_URL:
        channels.append("Webhook")
    return channels


def _post(url: str, payload: bytes, content_type: str) -> None:
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def send_alert(message: str) -> dict:
    """Send a message to every configured channel. Returns {channel: result text}."""
    results: dict[str, str] = {}

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode(
            {"chat_id": config.TELEGRAM_CHAT_ID, "text": message}).encode()
        try:
            _post(url, body, "application/x-www-form-urlencoded")
            results["Telegram"] = "sent"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            results["Telegram"] = f"failed ({type(exc).__name__})"

    if config.ALERT_WEBHOOK_URL:
        try:
            _post(config.ALERT_WEBHOOK_URL, json.dumps({"text": message}).encode(), "application/json")
            results["Webhook"] = "sent"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            results["Webhook"] = f"failed ({type(exc).__name__})"

    if not results:
        results["None"] = "no alert channel is configured (see .env.example)"
    return results


def build_message(pipeline: str, score: float, label: str, threshold: float,
                  exceptions: int, risk_text: str) -> str:
    return (
        f"DataGuard alert: {pipeline}\n"
        f"Health score {score:.1f} ({label}) is below the limit of {threshold:.0f}.\n"
        f"{exceptions} exceptions, {risk_text} at risk.\n"
        f"Open the DataGuard app to review the tickets."
    )


def alert_if_needed(pipeline: str, score: float, label: str, threshold: float,
                    exceptions: int, risk_text: str) -> dict | None:
    """Send an alert only when the score is below the threshold."""
    if score >= threshold:
        return None
    return send_alert(build_message(pipeline, score, label, threshold, exceptions, risk_text))
