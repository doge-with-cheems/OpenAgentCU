"""Rule-based instruction planner: natural language -> token-level plan."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

from .errors import NoMatch
from .keys import KeyParseError, SINGLE_KEYS, canonical_keys, parse_keys
from .models import Token

SPLIT_WORDS = ("然后", "接着", "并且", "并")
SPLIT_CHARS = "，；;。"
QUOTES = "「」『』“”\"'‘’"
OPEN_QUOTES = {"「": "」", "『": "』", "“": "”", "‘": "’"}

# 打开/启动 时识别为网址的目标
SITE_URLS = {
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "bilibili": "https://www.bilibili.com",
    "baidu": "https://www.baidu.com",
}

VERBS: tuple[tuple[str, str], ...] = (
    ("双击", "double_click"),
    ("右键", "right_click"),
    ("单击", "click"),
    ("点击", "click"),
    ("点一下", "click"),
    ("输入文字", "type"),
    ("输入文本", "type"),
    ("输入内容", "type"),
    ("打字", "type"),
    ("输入", "set_value"),
    ("填写", "set_value"),
    ("键入", "set_value"),
    ("滚动", "scroll"),
    ("按键", "key"),
    ("按下", "key"),
    ("敲", "key"),
    ("按", "key"),
    ("启动", "launch"),
    ("运行", "launch"),
    ("打开", "open"),
    ("搜索", "search"),
    ("等待", "wait"),
    ("激活", "activate"),
    ("切换到", "activate"),
    ("切到", "activate"),
    ("选择", "click"),
    ("点", "click"),
)

GENERIC_WORDS = (
    "窗口", "对话框", "按钮", "图标", "控件", "区域", "搜索框", "输入框",
    "一下", "这个", "那个", "浏览器", "应用", "程序", "软件", "的",
)

EDIT_TYPES = {"edit", "document", "textbox", "richtext", "text"}

@dataclass
class PlanStep:
    raw: str
    op: str
    token_id: str = ""
    token_name: str = ""
    score: float = 0.0
    value: str = ""
    keys: str = ""
    direction: str = ""
    times: int = 1
    ms: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"raw": self.raw, "op": self.op}
        if self.token_id:
            data["token_id"] = self.token_id
            data["token_name"] = self.token_name
            data["score"] = round(self.score, 3)
        if self.value:
            data["value"] = self.value
        if self.keys:
            data["keys"] = self.keys
        if self.direction:
            data["direction"] = self.direction
        if self.times != 1:
            data["times"] = self.times
        if self.ms:
            data["ms"] = self.ms
        return data


@dataclass
class Plan:
    instruction: str
    steps: list[PlanStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "steps": [step.to_dict() for step in self.steps],
        }


def split_clauses(text: str) -> list[str]:
    """Split on 然后/接着/并/，/； but never inside quotes."""
    parts: list[str] = []
    buffer: list[str] = []
    closing: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if closing is None and char in OPEN_QUOTES:
            closing = OPEN_QUOTES[char]
            buffer.append(char)
            index += 1
            continue
        if closing is not None and char == closing:
            closing = None
            buffer.append(char)
            index += 1
            continue
        if char == '"' or char == "'":
            closing = None if closing == char else char
            buffer.append(char)
            index += 1
            continue
        if closing is None:
            matched = False
            for word in SPLIT_WORDS:
                if text.startswith(word, index):
                    parts.append("".join(buffer))
                    buffer = []
                    index += len(word)
                    matched = True
                    break
            if matched:
                continue
            if char in SPLIT_CHARS:
                parts.append("".join(buffer))
                buffer = []
                index += 1
                continue
        buffer.append(char)
        index += 1
    parts.append("".join(buffer))
    cleaned = []
    for part in parts:
        value = part.strip(" \t\r\n，,。.；;：:")
        if value:
            cleaned.append(value)
    return cleaned


def detect_verb(clause: str) -> tuple[str, str]:
    for word, op in VERBS:
        if word in clause:
            return word, op
    return "", ""


def _strip_quotes(value: str) -> str:
    return value.strip().strip(QUOTES).strip()


def _clean_target(text: str) -> str:
    value = text.strip(" \t，,。.：:、；;")
    value = value.strip(QUOTES).strip()
    for prefix in ("这个", "那个", "向", "往", "把", "对", "给", "从"):
        if value.startswith(prefix) and len(value) > len(prefix):
            value = value[len(prefix):]
    for word in GENERIC_WORDS:
        if value.endswith(word) and len(value) > len(word):
            value = value[: -len(word)]
            break
    return value.strip(" 的了").strip(QUOTES)


def match_token(target: str, tokens: list[Token]) -> tuple[Token | None, float, list[dict[str, Any]]]:
    needle = _clean_target(target).lower()
    if not needle:
        return None, 0.0, []
    scored: list[tuple[float, int, Token]] = []
    for token in tokens:
        name = (token.name or "").strip()
        if not name:
            continue
        hay = name.lower()
        score = 0.0
        if hay == needle:
            score = 1.0
        elif needle in hay:
            score = 0.92 - min(len(hay) - len(needle), 40) * 0.004
        elif hay in needle:
            score = 0.86 - min(len(needle) - len(hay), 40) * 0.004
        else:
            ratio = difflib.SequenceMatcher(None, hay, needle).ratio()
            if ratio >= 0.6:
                score = ratio * 0.8
        if score > 0:
            scored.append((score, token.order, token))
    if not scored:
        fallback: list[tuple[float, int, Token]] = []
        for token in tokens:
            name = (token.name or "").strip()
            if not name:
                continue
            ratio = difflib.SequenceMatcher(None, name.lower(), needle).ratio()
            fallback.append((ratio, token.order, token))
        fallback.sort(key=lambda item: (-item[0], item[1]))
        candidates = [
            {"token_id": token.id, "name": token.name, "ctype": token.ctype, "score": round(ratio, 3)}
            for ratio, _order, token in fallback[:5]
        ]
        return None, 0.0, candidates
    scored.sort(key=lambda item: (-item[0], item[1]))
    candidates = [
        {"token_id": token.id, "name": token.name, "ctype": token.ctype, "score": round(score, 3)}
        for score, _order, token in scored[:5]
    ]
    best_score, _order, best = scored[0]
    return best, best_score, candidates


def _find_edit_token(tokens: list[Token]) -> Token | None:
    edits = [t for t in tokens if t.ctype.lower() in EDIT_TYPES]
    return edits[0] if len(edits) == 1 else None


def _parse_key(clause: str) -> str:
    body = clause
    for marker in ("按下", "按键", "敲", "按"):
        if marker in body:
            body = body.split(marker, 1)[1]
            break
    body = _strip_quotes(body).strip(" \t：:，,。")
    parts = body.split()
    if len(parts) > 1 and re.fullmatch(r"[A-Za-z0-9+^%{}\-_,]+", parts[0]):
        body = parts[0]

    key = canonical_keys(body)
    if not key:
        return ""
    if key in SINGLE_KEYS:
        return "{" + key.upper() + "}"
    try:
        parse_keys(key)
    except KeyParseError:
        return ""
    return key


def _parse_scroll(clause: str) -> tuple[str, int]:
    direction = ""
    for word, value in (("向下", "down"), ("向上", "up"), ("向左", "left"), ("向右", "right"),
                        ("下滚", "down"), ("上滚", "up")):
        if word in clause:
            direction = value
            break
    match = re.search(r"(\d+)\s*(?:次|格|行|页)?", clause)
    times = int(match.group(1)) if match else 1
    return direction or "down", max(1, times)


def _parse_wait(clause: str) -> int:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(毫秒|ms|秒|s)?", clause)
    if not match:
        return 1000
    value = float(match.group(1))
    unit = (match.group(2) or "秒").lower()
    if unit in ("毫秒", "ms"):
        return int(value)
    return int(value * 1000)


def _parse_input(clause: str, verb: str) -> tuple[str, str]:
    if verb in ("输入文字", "输入文本", "输入内容", "打字"):
        value = clause.split(verb, 1)[1] if verb in clause else ""
        return "", _strip_quotes(value)

    marker = next((word for word in ("输入", "填写", "键入") if word in clause), "")
    if not marker:
        return "", ""
    before, _, after = clause.partition(marker)
    before = _clean_target(before)
    if before.startswith("在") and len(before) > 1:
        before = _strip_quotes(before[1:])
    after = after.strip(" \t：:")

    suffix = re.match(r"(.+?)(?:到|在|进)(.+)$", after)
    if suffix and not before:
        return _clean_target(suffix.group(2)), _strip_quotes(suffix.group(1))

    if before in ("文字", "文本", "内容", "一下"):
        before = ""
    return before, _strip_quotes(after)


def _looks_like_url(target: str) -> bool:
    value = target.strip().lower()
    if re.match(r"^https?://", value):
        return True
    if re.match(r"^[\w.-]+\.(com|cn|org|net|io|tv|dev)(/|$)", value):
        return True
    return value in SITE_URLS


def _url_for(target: str) -> str:
    value = target.strip()
    lower = value.lower()
    if lower in SITE_URLS:
        return SITE_URLS[lower]
    if re.match(r"^https?://", lower):
        return value
    return "https://" + value


def _match_or_raise(target: str, tokens: list[Token], clause: str) -> tuple[Token, float]:
    token, score, candidates = match_token(target, tokens)
    if token is None:
        detail = ""
        if candidates:
            detail = "候选: " + "; ".join(
                f"{item['name']}({item['token_id']})" for item in candidates[:5]
            )
        raise NoMatch(f"没有找到匹配「{target or clause}」的元素", detail=detail)
    return token, score


def _add_input_steps(steps: list[PlanStep], clause: str, target: str, value: str,
                     tokens: list[Token]) -> None:
    if not value:
        raise NoMatch(f"没有识别到要输入的内容: {clause}")
    if not target:
        edit = _find_edit_token(tokens)
        if edit is not None:
            steps.append(PlanStep(raw=clause, op="set_value", token_id=edit.id,
                                  token_name=edit.name, score=0.5, value=value))
        else:
            steps.append(PlanStep(raw=clause, op="type", value=value))
        return
    token, score = _match_or_raise(target, tokens, clause)
    if token.ctype.lower() in EDIT_TYPES:
        steps.append(PlanStep(raw=clause, op="set_value", token_id=token.id,
                              token_name=token.name, score=score, value=value))
        return
    steps.append(PlanStep(raw=clause, op="click", token_id=token.id,
                          token_name=token.name, score=score))
    steps.append(PlanStep(raw=clause, op="wait", ms=250))
    steps.append(PlanStep(raw=clause, op="type", value=value))


def make_plan(instruction: str, tokens: list[Token]) -> Plan:
    clauses = split_clauses(instruction)
    if not clauses:
        raise NoMatch("指令为空")

    steps: list[PlanStep] = []
    for clause in clauses:
        # A clause that is exactly an element name (even if the name contains
        # words like 输入/键入) is a click, not an action.
        raw_clause = _strip_quotes(clause).strip()
        exact_token = next((t for t in tokens if t.name.strip() == raw_clause), None)
        if exact_token is not None:
            steps.append(PlanStep(raw=clause, op="click", token_id=exact_token.id,
                                  token_name=exact_token.name, score=1.0))
            continue
        exact_token, exact_score, _exact_candidates = match_token(clause, tokens)
        if exact_token is not None and exact_score >= 0.98:
            steps.append(PlanStep(raw=clause, op="click", token_id=exact_token.id,
                                  token_name=exact_token.name, score=exact_score))
            continue

        verb, op = detect_verb(clause)

        if not op:
            if "回车" in clause:
                steps.append(PlanStep(raw=clause, op="key", keys="{ENTER}"))
                continue
            token, score, _candidates = match_token(clause, tokens)
            if token is not None and score >= 0.9:
                steps.append(PlanStep(raw=clause, op="click", token_id=token.id,
                                      token_name=token.name, score=score))
                continue
            raise NoMatch(f"无法识别动作: {clause}", detail="支持: 启动/打开/点击/输入/搜索/按键/滚动/等待")

        if op == "key":
            keys = _parse_key(clause)
            if not keys:
                raise NoMatch(f"无法识别按键: {clause}", detail="示例: 按键回车 / 按键 win / 按下CTRL+S")
            steps.append(PlanStep(raw=clause, op="key", keys=keys))
            if keys == "{WIN}":
                steps.append(PlanStep(raw=clause, op="wait", ms=350))
            continue

        if op == "wait":
            steps.append(PlanStep(raw=clause, op="wait", ms=_parse_wait(clause)))
            continue

        if op == "type":
            value = _strip_quotes(clause.split(verb, 1)[1]) if verb in clause else ""
            if not value:
                raise NoMatch(f"没有识别到要输入的内容: {clause}")
            steps.append(PlanStep(raw=clause, op="type", value=value))
            continue

        if op == "search":
            query = _clean_target(clause.split(verb, 1)[1]) if verb in clause else ""
            if not query:
                raise NoMatch(f"没有识别到搜索内容: {clause}")
            if "youtube" in clause.lower():
                url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
            else:
                url = "https://www.google.com/search?q=" + quote_plus(query)
            steps.append(PlanStep(raw=clause, op="open_url", value=url))
            steps.append(PlanStep(raw=clause, op="wait", ms=800))
            continue

        if op == "launch":
            target = _clean_target(clause.split(verb, 1)[1]) if verb in clause else ""
            if not target:
                raise NoMatch(f"没有识别到要启动的程序: {clause}")
            if _looks_like_url(target):
                steps.append(PlanStep(raw=clause, op="open_url", value=_url_for(target)))
            else:
                steps.append(PlanStep(raw=clause, op="launch", value=target))
            steps.append(PlanStep(raw=clause, op="wait", ms=1200))
            continue

        if op == "open":
            target = _clean_target(clause.split(verb, 1)[1]) if verb in clause else ""
            if not target:
                raise NoMatch(f"没有识别到要打开的目标: {clause}")
            # 「打开 chrome 搜索 xxx」：启动应用并直接搜索
            if "搜索" in target:
                app, _, query = target.partition("搜索")
                app = app.strip()
                query = query.strip()
                if app and query:
                    if app.lower() in ("youtube", "youtube music"):
                        steps.append(PlanStep(raw=clause, op="open_url",
                                              value="https://www.youtube.com/results?search_query="
                                                    + quote_plus(query)))
                        steps.append(PlanStep(raw=clause, op="wait", ms=1000))
                        continue
                    steps.append(PlanStep(raw=clause, op="launch", value=app))
                    steps.append(PlanStep(raw=clause, op="wait", ms=1200))
                    steps.append(PlanStep(raw=clause, op="open_url",
                                          value="https://www.google.com/search?q=" + quote_plus(query)))
                    steps.append(PlanStep(raw=clause, op="wait", ms=800))
                    continue
            if _looks_like_url(target):
                steps.append(PlanStep(raw=clause, op="open_url", value=_url_for(target)))
                steps.append(PlanStep(raw=clause, op="wait", ms=800))
                continue
            token, score, _candidates = match_token(target, tokens)
            if token is not None and token.ctype.lower() == "window" and score >= 0.85:
                steps.append(PlanStep(raw=clause, op="activate", token_id=token.id,
                                      token_name=token.name, score=score))
                continue
            steps.append(PlanStep(raw=clause, op="launch", value=target))
            steps.append(PlanStep(raw=clause, op="wait", ms=1200))
            continue

        if op == "set_value":
            target, value = _parse_input(clause, verb)
            _add_input_steps(steps, clause, target, value, tokens)
            continue

        if op == "scroll":
            body = clause.split(verb, 1)[0] if verb else clause
            body = re.sub(r"(向下|向上|向左|向右|下滚|上滚)", " ", body)
            body = re.sub(r"\d+\s*(?:次|格|行|页)?", " ", body)
            target_text = _clean_target(body)
            if target_text.startswith("在") and len(target_text) > 1:
                target_text = target_text[1:]
            token, score = _match_or_raise(target_text, tokens, clause)
            direction, times = _parse_scroll(clause)
            steps.append(PlanStep(raw=clause, op="scroll", token_id=token.id,
                                  token_name=token.name, score=score,
                                  direction=direction, times=times))
            continue

        # click / double_click / right_click / activate
        body = clause.split(verb, 1)[1] if verb in clause else ""
        target_text = _clean_target(body)
        token, score = _match_or_raise(target_text, tokens, clause)
        steps.append(PlanStep(raw=clause, op=op, token_id=token.id,
                              token_name=token.name, score=score))

    if not steps:
        raise NoMatch("没有可执行的步骤")
    return Plan(instruction=instruction, steps=steps)
