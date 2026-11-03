from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminRuntimeSetting


PROMPT_TOOL_ROUTES_SETTING_KEY = "prompt_tool_provider_routes"

_MANAGED_TOOLS = ("image_analysis", "video_prompt")
_PROVIDER_MODELS = {"neironych": "qwen3.8-max", "nexus": "gpt-6-sol"}
_ROUTE_CHOICES = (("neironych", "nexus"), ("nexus", "neironych"), ("neironych",), ("nexus",))


def prompt_tool_route_options() -> dict[str, list[list[dict[str, str]]]]:
    return {
        tool: [
            [{"provider": provider, "model": _PROVIDER_MODELS[provider]} for provider in choice]
            for choice in _ROUTE_CHOICES
        ]
        for tool in _MANAGED_TOOLS
    }


def validate_prompt_tool_routes(routes: object) -> dict[str, list[dict[str, str]]]:
    if not isinstance(routes, dict) or set(routes) != set(_MANAGED_TOOLS):
        raise ValueError("Specify routes only for image_analysis and video_prompt")
    validated: dict[str, list[dict[str, str]]] = {}
    for tool in _MANAGED_TOOLS:
        route = routes[tool]
        if not isinstance(route, list) or not 1 <= len(route) <= len(_PROVIDER_MODELS):
            raise ValueError(f"Specify one or two supported providers for {tool}")
        targets: list[dict[str, str]] = []
        seen: set[str] = set()
        for target in route:
            if not isinstance(target, dict) or set(target) != {"provider", "model"}:
                raise ValueError(f"Each provider route for {tool} requires only provider and model")
            provider, model = target["provider"], target["model"]
            if (
                not isinstance(provider, str)
                or not isinstance(model, str)
                or provider not in _PROVIDER_MODELS
                or model != _PROVIDER_MODELS[provider]
            ):
                raise ValueError(f"Unsupported provider/model route for {tool}")
            if provider in seen:
                raise ValueError(f"Duplicate provider route for {tool}")
            seen.add(provider)
            targets.append({"provider": provider, "model": model})
        validated[tool] = targets
    return validated


async def configured_prompt_tool_routes(session: AsyncSession) -> dict[str, Any]:
    row = await session.get(AdminRuntimeSetting, PROMPT_TOOL_ROUTES_SETTING_KEY, populate_existing=True)
    if row is None:
        options = prompt_tool_route_options()
        return {"revision": 1, "routes": {tool: options[tool][0] for tool in _MANAGED_TOOLS}}
    value = row.value
    if not isinstance(value, dict):
        raise ValueError("Invalid stored prompt tool route policy")
    revision = value.get("revision")
    if type(revision) is not int or revision < 1:
        raise ValueError("Invalid stored prompt tool route revision")
    return {"revision": revision, "routes": validate_prompt_tool_routes(value.get("routes"))}
