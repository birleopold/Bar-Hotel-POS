from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import IntegrationLink

EFRIS_PROVIDER_KEY = "ura_efris"


@dataclass
class EfrisSubmitResult:
    success: bool
    provider_reference: str = ""
    error_message: str = ""


class BaseEfrisAdapter:
    def submit_receipt(self, *, tenant_id, payload: dict) -> EfrisSubmitResult:
        raise NotImplementedError

    def health_check_settings(self, *, settings: dict) -> EfrisSubmitResult:
        raise NotImplementedError


@dataclass
class UraEfrisCredentials:
    submit_endpoint: str
    auth_endpoint: str = ""
    tin: str = ""
    branch_id: str = ""
    device_no: str = ""
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    api_key: str = ""
    api_secret: str = ""
    signing_key: str = ""
    encryption_key: str = ""
    signing_mode: str = "hmac_sha256"
    encryption_mode: str = "none"
    request_timeout_seconds: int = 30
    extra_headers: dict[str, str] | None = None


class UraEfrisHttpAdapter(BaseEfrisAdapter):
    """
    HTTP adapter for URA EFRIS submissions.
    Keeps signing/encryption in explicit hooks so cryptography can be swapped
    without changing queue orchestration.
    """

    def submit_receipt(self, *, tenant_id, payload: dict) -> EfrisSubmitResult:
        link = (
            IntegrationLink.objects.filter(
                tenant_id=tenant_id,
                provider_key=EFRIS_PROVIDER_KEY,
                is_enabled=True,
            )
            .only("settings")
            .first()
        )
        if link is None:
            return EfrisSubmitResult(
                success=False,
                error_message="EFRIS integration link is not enabled for this tenant.",
            )
        credentials, error = self._credentials_from_settings(link.settings or {})
        if error:
            return EfrisSubmitResult(success=False, error_message=error)
        token, token_error = self._resolve_access_token(credentials)
        if token_error:
            return EfrisSubmitResult(success=False, error_message=token_error)
        try:
            wire_payload = self._build_wire_payload(payload=payload, credentials=credentials)
        except ValueError as exc:
            return EfrisSubmitResult(success=False, error_message=str(exc))

        headers = self._build_headers(credentials=credentials, access_token=token)
        code, body = self._post_json(
            url=credentials.submit_endpoint,
            payload=wire_payload,
            headers=headers,
            timeout_seconds=credentials.request_timeout_seconds,
        )
        return self._normalize_submit_response(status_code=code, body=body)

    def health_check_settings(self, *, settings: dict) -> EfrisSubmitResult:
        credentials, error = self._credentials_from_settings(settings)
        if error:
            return EfrisSubmitResult(success=False, error_message=error)
        token, token_error = self._resolve_access_token(credentials)
        if token_error:
            return EfrisSubmitResult(success=False, error_message=token_error)
        probe_ok, probe_error = self._probe_submit_endpoint(credentials=credentials, access_token=token)
        if not probe_ok:
            return EfrisSubmitResult(success=False, error_message=probe_error or "EFRIS endpoint probe failed.")
        return EfrisSubmitResult(success=True, provider_reference="health-check-ok")

    def _credentials_from_settings(
        self, settings: dict[str, Any]
    ) -> tuple[UraEfrisCredentials | None, str | None]:
        submit_endpoint = str(settings.get("submit_endpoint") or "").strip()
        auth_endpoint = str(settings.get("auth_endpoint") or "").strip()
        if not submit_endpoint:
            return None, "EFRIS config missing submit_endpoint."

        credentials = UraEfrisCredentials(
            submit_endpoint=submit_endpoint,
            auth_endpoint=auth_endpoint,
            tin=str(settings.get("tin") or "").strip(),
            branch_id=str(settings.get("branch_id") or "").strip(),
            device_no=str(settings.get("device_no") or "").strip(),
            access_token=str(settings.get("access_token") or "").strip(),
            client_id=str(settings.get("client_id") or "").strip(),
            client_secret=str(settings.get("client_secret") or "").strip(),
            api_key=str(settings.get("api_key") or "").strip(),
            api_secret=str(settings.get("api_secret") or "").strip(),
            signing_key=str(settings.get("signing_key") or "").strip(),
            encryption_key=str(settings.get("encryption_key") or "").strip(),
            signing_mode=str(settings.get("signing_mode") or "hmac_sha256").strip().lower(),
            encryption_mode=str(settings.get("encryption_mode") or "none").strip().lower(),
            request_timeout_seconds=int(settings.get("request_timeout_seconds") or 30),
            extra_headers={
                str(k): str(v)
                for k, v in (settings.get("extra_headers") or {}).items()
                if isinstance(k, str)
            }
            if isinstance(settings.get("extra_headers"), dict)
            else None,
        )
        if not credentials.tin:
            return None, "EFRIS config missing tin."
        if credentials.request_timeout_seconds <= 0:
            credentials.request_timeout_seconds = 30
        return credentials, None

    def _resolve_access_token(self, credentials: UraEfrisCredentials) -> tuple[str, str | None]:
        if credentials.access_token:
            return credentials.access_token, None
        if not credentials.auth_endpoint:
            return "", None
        if not credentials.client_id or not credentials.client_secret:
            return "", "EFRIS auth requires client_id and client_secret."
        code, body = self._post_json(
            url=credentials.auth_endpoint,
            payload={"client_id": credentials.client_id, "client_secret": credentials.client_secret},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout_seconds=credentials.request_timeout_seconds,
        )
        if code < 200 or code >= 300:
            return "", self._extract_error_message(body) or f"EFRIS auth failed with HTTP {code}."
        token = self._extract_reference(body, keys=("access_token", "token", "accessToken"))
        if not token:
            return "", "EFRIS auth response missing access token."
        return token, None

    def _build_wire_payload(self, *, payload: dict, credentials: UraEfrisCredentials) -> dict:
        payload_text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        encrypted_payload = self.encrypt_payload(payload_text=payload_text, credentials=credentials)
        signature = self.sign_payload(payload_text=encrypted_payload, credentials=credentials)
        wire_payload = {
            "tin": credentials.tin,
            "branch_id": credentials.branch_id,
            "device_no": credentials.device_no,
            "data": encrypted_payload,
        }
        if signature:
            wire_payload["signature"] = signature
        return wire_payload

    def _build_headers(self, *, credentials: UraEfrisCredentials, access_token: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-EFRIS-TIN": credentials.tin,
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if credentials.api_key:
            headers["X-API-Key"] = credentials.api_key
        if credentials.extra_headers:
            headers.update(credentials.extra_headers)
        return headers

    def _post_json(
        self, *, url: str, payload: dict, headers: dict[str, str], timeout_seconds: int
    ) -> tuple[int, dict[str, Any]]:
        request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8") if response else ""
                body = json.loads(raw) if raw else {}
                return int(response.getcode() or 200), body if isinstance(body, dict) else {"raw": body}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"message": raw or str(exc)}
            return int(exc.code), body if isinstance(body, dict) else {"raw": body}
        except URLError as exc:
            return 599, {"message": f"EFRIS network error: {exc.reason}"}
        except Exception as exc:  # defensive
            return 599, {"message": f"EFRIS adapter unexpected error: {exc}"}

    def _probe_submit_endpoint(
        self, *, credentials: UraEfrisCredentials, access_token: str
    ) -> tuple[bool, str]:
        headers = {"Accept": "application/json", "X-EFRIS-TIN": credentials.tin}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if credentials.api_key:
            headers["X-API-Key"] = credentials.api_key
        if credentials.extra_headers:
            headers.update(credentials.extra_headers)
        request = Request(url=credentials.submit_endpoint, headers=headers, method="OPTIONS")
        try:
            with urlopen(request, timeout=credentials.request_timeout_seconds) as response:
                code = int(response.getcode() or 200)
                if 200 <= code < 500:
                    return True, ""
                return False, f"EFRIS endpoint probe failed with HTTP {code}."
        except HTTPError as exc:
            if 200 <= int(exc.code) < 500:
                return True, ""
            return False, f"EFRIS endpoint probe failed with HTTP {exc.code}."
        except URLError as exc:
            return False, f"EFRIS endpoint network error: {exc.reason}"
        except Exception as exc:
            return False, f"EFRIS endpoint probe unexpected error: {exc}"

    def encrypt_payload(self, *, payload_text: str, credentials: UraEfrisCredentials) -> str:
        mode = credentials.encryption_mode
        if mode in {"", "none", "passthrough"}:
            return payload_text
        if mode == "base64":
            return base64.b64encode(payload_text.encode("utf-8")).decode("utf-8")
        raise ValueError(f"Unsupported EFRIS encryption_mode: {mode}")

    def sign_payload(self, *, payload_text: str, credentials: UraEfrisCredentials) -> str:
        mode = credentials.signing_mode
        if mode in {"", "none"}:
            return ""
        if mode == "sha256":
            return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        if mode == "hmac_sha256":
            key = credentials.api_secret or credentials.signing_key
            if not key:
                raise ValueError(
                    "EFRIS signing_mode hmac_sha256 requires api_secret or signing_key."
                )
            return hmac.new(
                key.encode("utf-8"),
                payload_text.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        raise ValueError(f"Unsupported EFRIS signing_mode: {mode}")

    def _normalize_submit_response(self, *, status_code: int, body: dict[str, Any]) -> EfrisSubmitResult:
        if status_code < 200 or status_code >= 300:
            return EfrisSubmitResult(
                success=False,
                error_message=self._extract_error_message(body) or f"EFRIS HTTP {status_code}.",
            )
        status_token = str(self._extract_reference(body, keys=("status", "result", "state")) or "").lower()
        if status_token in {"error", "failed", "fail", "rejected"}:
            return EfrisSubmitResult(
                success=False,
                error_message=self._extract_error_message(body) or "EFRIS rejected the submission.",
            )
        success_flag = self._extract_reference(body, keys=("success", "ok", "accepted"))
        if isinstance(success_flag, bool) and not success_flag:
            return EfrisSubmitResult(
                success=False,
                error_message=self._extract_error_message(body) or "EFRIS returned success=false.",
            )
        reference = self._extract_reference(
            body,
            keys=(
                "invoiceNo",
                "invoice_no",
                "receiptNo",
                "receipt_no",
                "reference",
                "referenceNo",
                "providerReference",
            ),
        )
        explicit_success = status_token in {"success", "succeeded", "accepted", "ok"} or success_flag is True
        if not reference and not explicit_success:
            return EfrisSubmitResult(
                success=False,
                error_message="EFRIS response did not confirm acceptance or provide a fiscal reference.",
            )
        return EfrisSubmitResult(success=True, provider_reference=str(reference or "")[:128])

    def _extract_error_message(self, body: dict[str, Any]) -> str:
        message = self._extract_reference(
            body,
            keys=("message", "error", "error_message", "errorMessage", "details", "detail", "msg"),
        )
        return str(message)[:2000] if message else ""

    def _extract_reference(self, body: Any, *, keys: tuple[str, ...]) -> Any:
        if isinstance(body, dict):
            for key in keys:
                if key in body and body[key] not in (None, ""):
                    return body[key]
            for value in body.values():
                found = self._extract_reference(value, keys=keys)
                if found not in (None, ""):
                    return found
        elif isinstance(body, list):
            for value in body:
                found = self._extract_reference(value, keys=keys)
                if found not in (None, ""):
                    return found
        return None


def get_efris_adapter() -> BaseEfrisAdapter:
    return UraEfrisHttpAdapter()
