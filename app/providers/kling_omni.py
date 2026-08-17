from __future__ import annotations

from typing import Any

import httpx

from app.providers.kie import KieTask


class KlingOmniProviderError(RuntimeError):
    pass


class KlingOmniClient:
    """Direct Kling VIDEO 3.0 Omni adapter.

    Kie currently exposes Kling 3.0 but not the separate 3.0 Omni API in its
    public Market index. The direct endpoint is therefore explicit deployment
    configuration instead of silently routing Omni requests to a different Kie
    model. This keeps product semantics correct while allowing the official
    Kling endpoint assigned to the account to be plugged in without code edits.
    """

    def __init__(
        self,
        *,
        api_key: str,
        create_url: str,
        status_url_template: str,
        model_name: str = "kling-v3-omni",
    ) -> None:
        if not api_key:
            raise KlingOmniProviderError("KLING_OMNI_API_KEY is not configured")
        if not create_url or not create_url.startswith("https://"):
            raise KlingOmniProviderError("KLING_OMNI_CREATE_URL must be an HTTPS endpoint")
        if not status_url_template or "{task_id}" not in status_url_template:
            raise KlingOmniProviderError(
                "KLING_OMNI_STATUS_URL_TEMPLATE must contain {task_id}"
            )
        if not status_url_template.startswith("https://"):
            raise KlingOmniProviderError("KLING_OMNI_STATUS_URL_TEMPLATE must use HTTPS")
        self._create_url = create_url
        self._status_url_template = status_url_template
        self._model_name = model_name
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_task(self, *, input_data: dict[str, Any]) -> str:
        body = {"model_name": self._model_name, **input_data}
        response = await self._client.post(self._create_url, json=body)
        response.raise_for_status()
        payload = response.json()
        task_id = self._task_id(payload)
        if not task_id:
            raise KlingOmniProviderError(
                f"Kling Omni generation returned no task id: {payload!r}"
            )
        return task_id

    async def get_task(self, task_id: str) -> KieTask:
        url = self._status_url_template.format(task_id=task_id)
        response = await self._client.get(url)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status = str(
            data.get("task_status")
            or data.get("status")
            or data.get("state")
            or "processing"
        ).lower()
        if status in {"succeed", "succeeded", "success", "completed"}:
            state = "success"
        elif status in {"failed", "fail", "error"}:
            state = "fail"
        else:
            state = "generating"
        return KieTask(
            task_id=self._task_id(payload) or task_id,
            state=state,
            result_urls=self._result_urls(data),
            fail_code=str(data.get("error_code") or data.get("fail_code") or ""),
            fail_message=str(
                data.get("error_message")
                or data.get("fail_message")
                or data.get("message")
                or ""
            ),
            raw=payload,
        )

    @staticmethod
    def _task_id(payload: dict[str, Any]) -> str:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        value = data.get("task_id") or data.get("taskId") or data.get("id")
        return str(value or "")

    @classmethod
    def _result_urls(cls, payload: dict[str, Any]) -> list[str]:
        candidates: list[str] = []

        def add(value: Any) -> None:
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                if value not in candidates:
                    candidates.append(value)
            elif isinstance(value, list):
                for item in value:
                    add(item)
            elif isinstance(value, dict):
                for key in ("url", "video_url", "resource", "videos", "works", "task_result"):
                    if key in value:
                        add(value[key])

        for key in ("video_url", "result_url", "result_urls", "task_result", "videos", "works"):
            if key in payload:
                add(payload[key])
        return candidates
