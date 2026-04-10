from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth

from .adf import build_adf_document
from .config import JiraSettings
from .exceptions import JiraAuthenticationError, JiraConfigurationError, JiraRequestError
from .models import JiraConnectionInfo, JiraCreateIssueResult, JiraIssueDraft


class JiraClient:
    def __init__(self, settings: JiraSettings, session: requests.Session | None = None) -> None:
        if not settings.is_configured:
            missing = ", ".join(settings.missing_fields)
            raise JiraConfigurationError(f"Configuracao Jira incompleta: {missing}")

        self.settings = settings
        self.session = session or requests.Session()
        self.session.auth = HTTPBasicAuth(settings.email, settings.api_token)
        self.session.headers.update({"Accept": "application/json"})

    def test_connection(self, project_key: str = "") -> JiraConnectionInfo:
        myself = self.get_myself()
        key = str(project_key or self.settings.project_key or "").strip()
        project_name = ""
        issue_types: tuple[str, ...] = ()
        if key:
            project = self.get_project(key)
            project_name = str(project.get("name") or "")
            issue_types = tuple(
                sorted(
                    {
                        str(item.get("name") or "").strip()
                        for item in project.get("issueTypes", [])
                        if str(item.get("name") or "").strip()
                    }
                )
            )

        return JiraConnectionInfo(
            base_url=self.settings.base_url,
            account_id=str(myself.get("accountId") or ""),
            display_name=str(myself.get("displayName") or ""),
            email=str(myself.get("emailAddress") or self.settings.email),
            project_key=key,
            project_name=project_name,
            issue_types=issue_types,
        )

    def get_myself(self) -> dict[str, Any]:
        response = self._request("GET", "/rest/api/3/myself", expected_status=(200,))
        return self._json_or_empty(response)

    def get_project(self, project_key: str) -> dict[str, Any]:
        key = str(project_key or "").strip()
        if not key:
            raise JiraConfigurationError("Project key nao informado para consulta no Jira.")
        response = self._request("GET", f"/rest/api/3/project/{quote(key)}", expected_status=(200,))
        return self._json_or_empty(response)

    def get_issue(self, issue_key: str, fields: tuple[str, ...] = ("status",)) -> dict[str, Any]:
        key = str(issue_key or "").strip()
        if not key:
            raise JiraRequestError("Issue key ausente para consulta no Jira.")
        params = {}
        if fields:
            params["fields"] = ",".join(str(field).strip() for field in fields if str(field).strip())
        response = self._request(
            "GET",
            f"/rest/api/3/issue/{quote(key)}",
            params=params,
            expected_status=(200,),
        )
        return self._json_or_empty(response)

    def create_issue(self, draft: JiraIssueDraft) -> JiraCreateIssueResult:
        fields = {
            "project": {"key": draft.project_key},
            "issuetype": {"name": draft.issue_type},
            "summary": draft.summary,
            "description": build_adf_document(draft.description),
        }
        if draft.labels:
            fields["labels"] = list(draft.labels)
        if draft.extra_fields:
            fields.update(draft.extra_fields)

        response = self._request(
            "POST",
            "/rest/api/3/issue",
            json={"fields": fields},
            expected_status=(201,),
        )
        payload = self._json_or_empty(response)
        issue_key = str(payload.get("key") or "").strip()
        issue_id = str(payload.get("id") or "").strip()
        attachment_names: list[str] = []

        for attachment_path in draft.attachment_paths:
            if self.add_attachment(issue_key, attachment_path):
                attachment_names.append(Path(attachment_path).name)

        return JiraCreateIssueResult(
            issue_id=issue_id,
            issue_key=issue_key,
            issue_url=self.issue_browse_url(issue_key),
            attachment_names=tuple(attachment_names),
        )

    def add_attachment(self, issue_key: str, attachment_path: str | Path) -> bool:
        path = Path(attachment_path)
        if not issue_key:
            raise JiraRequestError("Issue key ausente para upload de anexo.")
        if not path.exists() or not path.is_file():
            raise JiraRequestError(f"Arquivo de anexo nao encontrado: {path}")

        with path.open("rb") as handle:
            response = self._request(
                "POST",
                f"/rest/api/3/issue/{quote(issue_key)}/attachments",
                files={"file": (path.name, handle)},
                headers={"X-Atlassian-Token": "no-check"},
                expected_status=(200, 201),
            )
        return response.ok

    def issue_browse_url(self, issue_key: str) -> str:
        return f"{self.settings.base_url}/browse/{issue_key}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: tuple[int, ...],
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.settings.base_url}{path}"
        timeout = kwargs.pop("timeout", self.settings.timeout_s)
        verify = kwargs.pop("verify", self.settings.verify_ssl)

        try:
            response = self.session.request(method, url, timeout=timeout, verify=verify, **kwargs)
        except requests.RequestException as exc:
            raise JiraRequestError(f"Falha de rede ao acessar Jira: {exc}") from exc

        if response.status_code in {401, 403}:
            detail = self._extract_error_detail(response)
            raise JiraAuthenticationError(f"Jira recusou a autenticacao. {detail}".strip())

        if response.status_code not in expected_status:
            detail = self._extract_error_detail(response)
            raise JiraRequestError(
                f"Jira respondeu com status {response.status_code}. {detail}".strip(),
                status_code=response.status_code,
                details=detail,
            )
        return response

    @staticmethod
    def _json_or_empty(response: requests.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _extract_error_detail(cls, response: requests.Response) -> str:
        payload = cls._json_or_empty(response)
        messages = []
        error_messages = payload.get("errorMessages")
        if isinstance(error_messages, list):
            messages.extend(str(item).strip() for item in error_messages if str(item).strip())

        errors = payload.get("errors")
        if isinstance(errors, dict):
            for field, message in errors.items():
                text = str(message).strip()
                if text:
                    messages.append(f"{field}: {text}")

        if messages:
            return " ".join(messages)

        text = str(response.text or "").strip()
        return text[:400]
