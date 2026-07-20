from __future__ import annotations

import re

from app.schemas import TravelRequest


KNOWN_CITIES = ["北京", "上海", "广州", "深圳", "西安", "重庆", "成都", "杭州", "厦门", "南京", "武汉", "长沙", "青岛", "苏州"]


def parse_chat_message(message: str) -> TravelRequest:
    origin = extract_origin(message)
    destination = extract_destination(message)
    days = extract_days(message)
    budget = extract_budget(message)
    interests = extract_interests(message)
    constraints = extract_constraints(message)
    people = extract_people(message)
    mode = "student" if any(token in message for token in ["穷游", "学生", "省钱"]) else "comfort" if any(token in message for token in ["轻奢", "舒服", "少折腾"]) else "value"
    group = "couple" if "情侣" in message else "family" if any(token in message for token in ["家庭", "父母", "亲子"]) else "solo" if any(token in message for token in ["一个人", "独自", "单人"]) else "friends"
    pace = "relaxed" if any(token in message for token in ["少走路", "不早起", "轻松"]) else "intense" if any(token in message for token in ["特种兵", "多打卡"]) else "balanced"
    return TravelRequest(
        origin=origin,
        destination=destination,
        days=days,
        budget_total=budget,
        budget_mode=mode,
        group=group,
        people=people,
        interests=interests,
        constraints=constraints,
        pace=pace,
        must_have=message,
    )


def extract_destination(text: str) -> str:
    explicit = re.search(r"(?:去|到|目的地是)\s*([\u4e00-\u9fa5]{2,6})", text)
    if explicit:
        return explicit.group(1).strip("玩旅游出差")
    for city in KNOWN_CITIES:
        if city in text and f"从{city}" not in text:
            return city
    return "重庆"


def extract_origin(text: str) -> str:
    explicit = re.search(r"从\s*([\u4e00-\u9fa5]{2,6})\s*(?:出发|去|到)", text)
    return explicit.group(1) if explicit else "当前位置"


def extract_days(text: str) -> int:
    digit = re.search(r"(\d+)\s*天", text)
    if digit:
        return min(max(int(digit.group(1)), 1), 10)
    mapping = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
    chinese = re.search(r"([一两二三四五六七])天", text)
    return mapping.get(chinese.group(1), 3) if chinese else 3


def extract_budget(text: str) -> int:
    match = re.search(r"(?:预算|花费|控制在)?\s*(\d{3,5})\s*(?:元|块|预算)?", text)
    return min(max(int(match.group(1)), 300), 100000) if match else 1800


def extract_people(text: str) -> int:
    match = re.search(r"(\d+)\s*人", text)
    return min(max(int(match.group(1)), 1), 12) if match else 2


def extract_interests(text: str) -> list[str]:
    mapping = ["自然风光", "历史古迹", "城市逛吃", "户外徒步", "博物馆", "小众打卡", "夜市美食", "美食", "夜景", "拍照"]
    found = [item for item in mapping if item in text]
    return found or ["城市逛吃", "小众打卡"]


def extract_constraints(text: str) -> list[str]:
    mapping = ["少走路", "不爱早起", "晕车", "不吃辣", "宠物同行", "拒绝人挤人", "不排队"]
    return [item for item in mapping if item in text]
