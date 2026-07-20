from __future__ import annotations

from app.schemas import BudgetBreakdown, TravelRequest


def calculate_budget(request: TravelRequest) -> tuple[BudgetBreakdown, list[str]]:
    total = request.budget_total
    mode = request.budget_mode
    if mode == "student":
        ratios = {"lodging": 0.24, "food": 0.24, "local_transport": 0.08, "intercity_transport": 0.28, "tickets": 0.10, "buffer": 0.06}
    elif mode == "comfort":
        ratios = {"lodging": 0.32, "food": 0.24, "local_transport": 0.12, "intercity_transport": 0.22, "tickets": 0.06, "buffer": 0.04}
    else:
        ratios = {"lodging": 0.28, "food": 0.24, "local_transport": 0.10, "intercity_transport": 0.25, "tickets": 0.08, "buffer": 0.05}
    budget = BudgetBreakdown(**{key: round(total * value) for key, value in ratios.items()})
    log = []
    per_person_day = total / max(request.people * request.days, 1)
    if per_person_day < 260:
        log.append("预算偏紧：已优先选择免费景点、公共交通和低价餐饮，把付费体验控制在 1-2 个。")
    if budget.total > total:
        log.append("预算四舍五入后略超，实际执行时从机动金中扣减。")
    return budget, log


def build_packing_list(request: TravelRequest, rainy: bool, hot: bool) -> list[str]:
    items = ["身份证/学生证", "充电器和充电宝", "舒适步行鞋", "常用药", "少量现金", "可折叠背包"]
    if rainy:
        items.extend(["折叠伞", "防水鞋套或备用袜子"])
    if hot:
        items.extend(["防晒霜", "遮阳帽", "补水杯"])
    if request.group == "family":
        items.extend(["长辈常用药", "轻便外套"])
    if any("晕车" in item for item in request.constraints):
        items.append("晕车药/晕车贴")
    if any("宠物" in item for item in request.constraints):
        items.extend(["宠物证件", "牵引绳", "宠物便携水碗"])
    return list(dict.fromkeys(items))
