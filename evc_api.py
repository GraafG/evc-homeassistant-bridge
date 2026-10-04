"""HTTP client for the EVC Network mobile API."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class EVCClient:
    """Small, retrying client for the EVC Network guest API."""

    def __init__(self, config: dict[str, Any]) -> None:
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("EVC_API_KEY is not configured")

        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config["headers"])
        self.session.headers["x-api-key"] = api_key

        retries = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _common_payload(self, device_id: str) -> dict[str, Any]:
        return {
            "deviceId": device_id,
            "locale": self.config["locale"],
            "platform": self.config["platform"],
            "serviceName": self.config["service_name"],
            "serviceVersion": self.config["service_version"],
            "appVersion": self.config["app_version"],
            "appIdentifier": self.config["app_identifier"],
        }

    def get_guest_token(self, device_id: str) -> str | None:
        """Request a guest token. EVC guest tokens may be single-use."""
        payload = {
            **self._common_payload(device_id),
            "webUrl": "directpayment.evc-net.com",
        }
        response = self.session.post(
            f"{self.config['base_url']}/user/guestLogin",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("data", {}).get("token")

    def get_station_status(self, qr_code: str, device_id: str) -> dict[str, Any]:
        """Fetch raw status data for one station."""
        try:
            token = self.get_guest_token(device_id)
            if not token:
                return {"error": "EVC API did not return an authentication token"}

            payload = {
                **self._common_payload(device_id),
                "locationId": "",
                "channelId": "",
                "qrCode": qr_code,
                "evseId": "",
                "token": token,
                "referenceGeoBounds": {},
            }
            response = self.session.post(
                f"{self.config['base_url']}/location/getLocationDetails",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("data", {})
        except (requests.RequestException, ValueError) as exc:
            return {"error": str(exc)}
