import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from family_ai_api.agent import registry
from family_ai_api.agent.registry import ToolSpec
from family_ai_api.config import Settings
from family_ai_api.services import ollama_client

logger = logging.getLogger(__name__)

PLANNER_INSTRUCTIONS = """你是一个工具规划器。根据用户问题，判断是否需要调用一个工具。

规则：
1. 最多选择一个工具。
2. 写操作只生成计划，不会直接执行，用户需要确认。
3. 如果问题不需要工具，返回 {"tool": null, "arguments": {}}。
4. 对于 create_task，只有用户在消息中明确给出日期/时间时才填写 due_at，
   并且必须使用用户给出的日期；不要猜测、换算或编造日期。无法确定时省略 due_at。
5. 只输出一个 JSON 对象，不要输出 Markdown、解释或多余文本。

可用工具：
"""

ANSWER_SYSTEM = (
    "你是家庭助手。根据工具结果回答用户问题；"
    "不要编造工具结果中没有的信息；回答使用中文，简洁。"
)


@dataclass(frozen=True)
class Plan:
    tool: ToolSpec
    arguments: dict


def _tools_prompt() -> str:
    lines: list[str] = []
    for spec in registry.TOOLS.values():
        kind = "写" if spec.write else "读"
        schema = json.dumps(spec.parameters, ensure_ascii=False)
        lines.append(f"- {spec.name}（{kind}）：{spec.description} 参数：{schema}")
    return "\n".join(lines)


def build_planner_prompt() -> str:
    return (
        PLANNER_INSTRUCTIONS
        + _tools_prompt()
        + '\n\n输出格式：{"tool": "工具名" 或 null, "arguments": {...}}'
    )


def extract_date_expression(message: str) -> str | None:
    full = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", message)
    if full:
        try:
            return date(
                int(full.group(1)), int(full.group(2)), int(full.group(3))
            ).isoformat()
        except ValueError:
            return None

    short = re.search(r"(\d{1,2})月(\d{1,2})日", message)
    if short:
        try:
            return date(
                date.today().year, int(short.group(1)), int(short.group(2))
            ).isoformat()
        except ValueError:
            return None

    today = date.today()
    if "后天" in message:
        return (today + timedelta(days=2)).isoformat()
    if "明天" in message:
        return (today + timedelta(days=1)).isoformat()
    if "今天" in message:
        return today.isoformat()
    return None


def resolve_due_at(message: str, model_due_at: object) -> str | None:
    explicit = extract_date_expression(message)
    if explicit is None:
        return None
    if (
        isinstance(model_due_at, str)
        and model_due_at.startswith(explicit)
        and "T" in model_due_at
    ):
        return model_due_at
    return explicit


async def plan(message: str, settings: Settings) -> Plan | None:
    messages = [
        {"role": "system", "content": build_planner_prompt()},
        {"role": "user", "content": f"用户问题：\n{message}"},
    ]
    result = await ollama_client.chat(messages, settings)
    text = result.content.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    name = data.get("tool")
    if not isinstance(name, str):
        return None
    name = name.strip()
    arguments = data.get("arguments") or {}
    if not isinstance(arguments, dict):
        return None

    try:
        normalized = registry.validate_arguments(name, arguments, settings)
    except registry.ToolError as exc:
        logger.warning("tool plan rejected: %s", type(exc).__name__)
        return None

    if name == "create_task":
        normalized["due_at"] = resolve_due_at(message, normalized.get("due_at"))

    return Plan(tool=registry.TOOLS[name], arguments=normalized)


async def answer_without_tool(message: str, settings: Settings) -> str:
    result = await ollama_client.chat(
        [{"role": "user", "content": message}], settings
    )
    return result.content


async def answer_with_tool(
    message: str,
    tool_result: str,
    settings: Settings,
) -> str:
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM},
        {
            "role": "user",
            "content": f"用户问题：\n{message}\n\n工具结果（JSON）：\n{tool_result}",
        },
    ]
    result = await ollama_client.chat(messages, settings)
    return result.content


def confirmation_text(plan: Plan) -> str:
    return f"已准备执行工具 {plan.tool.name}。确认后才会执行。"
