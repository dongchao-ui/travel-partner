from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import httpx

from app.schemas import DayPlan, PlanQualityIssue, PlanResponse, TimeSlot, ToolCallPlan, TravelRequest
from app.storage import update_memory, write_export
from app.tools.attractions import find_attractions
from app.tools.budget import build_packing_list, calculate_budget
from app.tools.content import collect_guide_insights
from app.tools.transport import plan_transport
from app.tools.weather import get_weather


GROUP_LABEL = {"solo": "单人", "couple": "情侣", "friends": "朋友/同学", "family": "家庭"}
MODE_LABEL = {"student": "学生穷游", "value": "性价比", "comfort": "轻奢舒适"}
PLACEHOLDER_SLOT_TITLES = {"自由探索", "轻量自由探索", "附近餐饮/休息", "夜间餐饮机动"}


async def build_travel_plan(request: TravelRequest) -> PlanResponse:
    normalized_request = normalize_request(request)
    tool_plan = decide_tool_usage(normalized_request)
    weather = await get_weather(normalized_request.destination, normalized_request.days, normalized_request.start_date)
    attractions = await find_attractions(normalized_request)
    guide_insights = collect_guide_insights(normalized_request)
    transport_options = plan_transport(normalized_request) if tool_plan.transport else []
    budget, budget_log = calculate_budget(normalized_request)
    travel_decision = build_travel_decision(weather)

    rainy = any(day.precipitation_mm >= 3 or "雨" in day.text for day in weather.days)
    hot = any(day.temp_max >= 32 for day in weather.days)
    packing_list = build_packing_list(normalized_request, rainy, hot)
    if travel_decision["should_postpone"]:
        itinerary: list[DayPlan] = []
        itinerary_log = [travel_decision["detail"]]
    else:
        itinerary, itinerary_log = build_itinerary(normalized_request, weather, attractions, budget)
    quality_issues = validate_plan(normalized_request, weather, attractions, itinerary, budget, travel_decision)
    quality_log = [f"方案自检：{item.title} - {item.detail}" for item in quality_issues]

    warnings = [
        *weather.warnings,
        *([travel_decision["detail"]] if travel_decision["should_postpone"] else []),
        "票价、余票、酒店库存和平台评分需要生产级 API 二次确认，当前 Demo 不编造实时库存。",
    ]
    if normalized_request.use_private_knowledge:
        warnings.append("本地 RAG 使用轻量关键词召回，生产版可替换为 Chroma + sentence-transformers。")

    summary = build_summary(normalized_request, budget.total)
    markdown = render_markdown(
        normalized_request,
        summary,
        weather,
        attractions,
        guide_insights,
        transport_options,
        itinerary,
        budget,
        packing_list,
        warnings,
        [*budget_log, *itinerary_log, *quality_log],
        travel_decision,
        tool_plan,
        quality_issues,
    )
    markdown = await maybe_polish_with_deepseek(markdown)
    plan_id = uuid.uuid4().hex[:12]
    export_url = write_export(plan_id, markdown)

    update_memory(
        {
            "origin": normalized_request.origin if normalized_request.origin != "当前位置" else "",
            "interests": normalized_request.interests,
            "constraints": normalized_request.constraints,
            "recent_destinations": normalized_request.destination,
            "budget_mode": MODE_LABEL[normalized_request.budget_mode],
        }
    )

    return PlanResponse(
        plan_id=plan_id,
        summary=summary,
        request=normalized_request,
        tool_plan=tool_plan,
        weather=weather,
        attractions=attractions,
        guide_insights=guide_insights,
        transport_options=transport_options,
        itinerary=itinerary,
        budget=budget,
        packing_list=packing_list,
        quality_issues=quality_issues,
        warnings=warnings,
        adjustment_log=[*budget_log, *itinerary_log, *quality_log],
        markdown=markdown,
        export_url=export_url,
    )


def normalize_request(request: TravelRequest) -> TravelRequest:
    if request.start_date and request.end_date:
        delta = (request.end_date - request.start_date).days + 1
        if delta > 0:
            request.days = min(delta, 10)
    if not request.interests:
        request.interests = ["城市逛吃", "小众打卡"]
    return request


def apply_adjustment(request: TravelRequest, instruction: str) -> TravelRequest:
    adjusted = request.model_copy(deep=True)
    text = instruction.strip()
    if any(token in text for token in ["降低预算", "省钱", "穷游", "便宜"]):
        adjusted.budget_mode = "student"
        adjusted.budget_total = max(300, round(adjusted.budget_total * 0.85))
    if any(token in text for token in ["少走路", "缩短步行", "轻松"]):
        if "少走路" not in adjusted.constraints:
            adjusted.constraints.append("少走路")
        adjusted.pace = "relaxed"
    if any(token in text for token in ["增加美食", "多加美食", "夜市", "逛吃"]):
        for interest in ["城市逛吃", "夜市美食"]:
            if interest not in adjusted.interests:
                adjusted.interests.append(interest)
    if any(token in text for token in ["室内", "下雨", "雨天"]):
        if "雨天优先室内" not in adjusted.constraints:
            adjusted.constraints.append("雨天优先室内")
        for interest in ["博物馆", "城市逛吃"]:
            if interest not in adjusted.interests:
                adjusted.interests.append(interest)
    adjusted.private_notes = f"{adjusted.private_notes}\n二次微调：{text}".strip()
    return adjusted


def decide_tool_usage(request: TravelRequest) -> ToolCallPlan:
    reasons = ["天气、景点和预算是完整旅行规划的基础工具。"]
    same_city = request.origin and request.origin == request.destination
    transport = not same_city
    if same_city:
        reasons.append("出发地与目的地一致，弱化城际交通工具，重点使用市内交通建议。")
    else:
        reasons.append("存在跨城出行，需要生成城际交通候选方案。")
    rag = bool(request.use_private_knowledge)
    if rag:
        reasons.append("用户开启私有攻略，将检索本地 RAG 资料辅助生成。")
    else:
        reasons.append("用户未开启私有攻略，仅使用公开规则和内置候选库。")
    return ToolCallPlan(
        weather=True,
        attractions=True,
        guide_search=True,
        transport=transport,
        budget=True,
        rag=rag,
        reasons=reasons,
    )


def build_travel_decision(weather) -> dict:
    rainy_days = [day for day in weather.days if day.precipitation_mm >= 3 or "雨" in day.text]
    heavy_rain = any(day.precipitation_mm >= 10 or "大雨" in day.text or "暴雨" in day.text for day in weather.days)
    mostly_rainy = len(rainy_days) >= max(1, (len(weather.days) + 1) // 2)
    if heavy_rain or mostly_rainy:
        return {
            "level": "warn",
            "should_postpone": True,
            "title": "这段时间降雨偏多，建议改期再出发",
            "detail": "与其硬排雨天行程，不如先把这段时间作为改期候选，等天气稳定后再生成更完整的分天方案。",
        }
    if rainy_days:
        return {
            "level": "notice",
            "should_postpone": False,
            "title": "可以出行，但要准备雨天备选",
            "detail": "行程里有部分降雨风险，建议优先选择博物馆、商圈和室内餐饮等点位。",
        }
    return {
        "level": "ok",
        "should_postpone": False,
        "title": "天气适合按计划出行",
        "detail": "当前周期没有明显降雨压力，可以正常编排行程，并保留少量机动时间即可。",
    }


def validate_plan(request: TravelRequest, weather, attractions, itinerary, budget, travel_decision) -> list[PlanQualityIssue]:
    issues: list[PlanQualityIssue] = []
    attraction_by_name = {item.name: item for item in attractions}

    if travel_decision["should_postpone"]:
        return [
            PlanQualityIssue(
                severity="notice",
                title="已触发改期判断",
                detail="天气风险较高，本次不强行生成每日行程，避免给出不可落地方案。",
            )
        ]

    if not itinerary:
        return [
            PlanQualityIssue(
                severity="warning",
                title="缺少每日行程",
                detail="系统没有生成分天安排，需要检查景点候选或天气分支。",
            )
        ]

    for day in itinerary:
        titles = [slot.title for slot in day.slots if slot.title and slot.title not in PLACEHOLDER_SLOT_TITLES]
        if len(titles) != len(set(titles)):
            issues.append(
                PlanQualityIssue(
                    severity="warning",
                    title=f"Day {day.day} 存在重复景点",
                    detail="同一天上午、下午、晚上出现重复点位，建议重新选择时段景点。",
                )
            )
        weather_day = weather.days[(day.day - 1) % len(weather.days)]
        rainy = weather_day.precipitation_mm >= 3 or "雨" in weather_day.text
        if rainy:
            outdoor_slots = [title for title in titles if title in attraction_by_name and not attraction_by_name[title].indoor]
            if outdoor_slots:
                issues.append(
                    PlanQualityIssue(
                        severity="notice",
                        title=f"Day {day.day} 雨天含室外点位",
                        detail=f"{'、'.join(outdoor_slots[:3])} 可能受降雨影响，建议保留室内备选。",
                    )
                )
        if len(day.slots) < 3:
            issues.append(
                PlanQualityIssue(
                    severity="notice",
                    title=f"Day {day.day} 行程密度偏低",
                    detail="当天少于 3 个时段安排，可根据体力补充轻量餐饮或休息点。",
                )
            )

    trip_counts: dict[str, int] = {}
    for day in itinerary:
        for slot in day.slots:
            if slot.title and slot.title not in PLACEHOLDER_SLOT_TITLES:
                trip_counts[slot.title] = trip_counts.get(slot.title, 0) + 1
    repeated_trip_places = [name for name, count in trip_counts.items() if count > 1]
    if repeated_trip_places:
        issues.append(
            PlanQualityIssue(
                severity="notice",
                title="全程存在重复景点",
                detail=f"{'、'.join(repeated_trip_places[:3])} 在多天行程中重复出现，建议优先替换为未安排点位。",
            )
        )

    vague_places = [
        item.name
        for item in attractions
        if "待核实" in item.area or "市内" in item.area or "待确认" in item.area
    ]
    if vague_places:
        issues.append(
            PlanQualityIssue(
                severity="notice",
                title="部分景点位置仍需核实",
                detail=f"{'、'.join(vague_places[:3])} 的位置来自兜底检索，出发前需要用地图确认入口。",
            )
        )

    if budget.total > request.budget_total:
        issues.append(
            PlanQualityIssue(
                severity="warning",
                title="预算超过用户输入",
                detail=f"当前合计 {budget.total} 元，高于用户预算 {request.budget_total} 元，需要降级食宿或门票。",
            )
        )

    if not issues:
        issues.append(
            PlanQualityIssue(
                severity="pass",
                title="方案自检通过",
                detail="未发现重复景点、空行程、明显预算超限等基础问题。",
            )
        )
    return issues


def build_itinerary(request: TravelRequest, weather, attractions, budget) -> tuple[list[DayPlan], list[str]]:
    logs = []
    plans: list[DayPlan] = []
    daily_budget = max(round(request.budget_total / max(request.days, 1)), 1)
    start = request.start_date or date.today()
    indoor_pool = [item for item in attractions if item.indoor]
    outdoor_pool = [item for item in attractions if not item.indoor]
    all_pool = attractions[:]
    usage_counts: dict[str, int] = {}

    for index in range(request.days):
        weather_day = weather.days[index % len(weather.days)]
        current_date = (start + timedelta(days=index)).isoformat()
        rainy = weather_day.precipitation_mm >= 3 or "雨" in weather_day.text
        primary_pool = indoor_pool if rainy and indoor_pool else outdoor_pool or all_pool
        used_names: set[str] = set()
        morning = choose_distinct_place(primary_pool, index, used_names, usage_counts)
        afternoon = choose_distinct_place(all_pool, index + 2, used_names, usage_counts)
        evening = choose_evening(attractions, index, used_names, usage_counts)

        slots = [
            make_slot("上午", morning, "抵达或从住宿地出发，先安排体力消耗适中的核心点位。", weather_day.advice),
            make_slot("下午", afternoon, "同片区串联第二个点位，预留咖啡/休息时间，避免把路线排满。", weather_day.advice),
            make_slot("晚上", evening, "以夜景、夜市或商圈收尾，方便吃饭后回住处。", weather_day.advice),
        ]
        if rainy and indoor_pool:
            logs.append(f"第 {index + 1} 天存在降水风险，已优先替换为室内/半室内点位。")
        plans.append(
            DayPlan(
                day=index + 1,
                date=current_date,
                theme=build_day_theme(index, request, rainy),
                area=morning.area if morning else f"{request.destination}核心区",
                slots=slots,
                food=build_food_list(request, index),
                transport=build_local_transport(request),
                daily_budget=daily_budget,
                risk_control=build_risk_control(request, weather_day),
            )
        )
    return plans, logs


def make_slot(time_label: str, attraction, fallback: str, weather_hint: str) -> TimeSlot:
    if not attraction:
        fallback_titles = {
            "上午": "轻量自由探索",
            "下午": "附近餐饮/休息",
            "晚上": "夜间餐饮机动",
        }
        return TimeSlot(time=time_label, title=fallback_titles.get(time_label, "自由探索"), detail=fallback, cost="按实际消费", weather_hint=weather_hint)
    return TimeSlot(
        time=time_label,
        title=attraction.name,
        detail=f"{attraction.category}，建议游玩 {attraction.duration}。{attraction.reason}",
        cost=attraction.price,
        weather_hint=weather_hint,
    )


def choose_distinct_place(places, index: int, used_names: set[str], usage_counts: dict[str, int]):
    if not places:
        return None
    candidates = [place for place in places if place.name not in used_names and usage_counts.get(place.name, 0) == 0]
    if not candidates:
        return None
    for offset in range(len(places)):
        place = places[(index + offset) % len(places)]
        if place in candidates:
            used_names.add(place.name)
            usage_counts[place.name] = usage_counts.get(place.name, 0) + 1
            return place
    place = candidates[0]
    used_names.add(place.name)
    usage_counts[place.name] = usage_counts.get(place.name, 0) + 1
    return place


def choose_evening(attractions, index: int, used_names: set[str], usage_counts: dict[str, int]):
    evening_candidates = [item for item in attractions if any(token in item.category for token in ["夜", "小吃", "逛吃", "街区"])]
    place = choose_distinct_place(evening_candidates, index, used_names, usage_counts)
    if place:
        return place
    return choose_distinct_place(attractions, index + 3, used_names, usage_counts)


def build_day_theme(index: int, request: TravelRequest, rainy: bool) -> str:
    if rainy:
        return "雨天友好：室内场馆 + 城市逛吃"
    themes = ["抵达适应 + 核心地标", "小众片区 + 本地美食", "轻松收尾 + 返程缓冲"]
    return themes[index] if index < len(themes) else f"{request.destination}深度探索"


def build_food_list(request: TravelRequest, index: int) -> list[str]:
    base = ["本地小吃集合店/夜市", "高评分社区小馆", "便利店/轻食作为机动备选"]
    if any("不吃辣" in item for item in request.constraints):
        base.insert(0, "清淡本地菜或可备注不辣的餐厅")
    if request.budget_mode == "student":
        base.append("人均 30-60 元的粉面/小吃优先")
    elif request.budget_mode == "comfort":
        base.append("可安排一餐当地特色正餐，人均 100-180 元")
    return base[index % len(base) :] + base[: index % len(base)]


def build_local_transport(request: TravelRequest) -> str:
    if any("少走路" in item or "怕走路" in item for item in request.constraints):
        return "地铁/公交为主，跨片区短途打车，单日步行尽量控制在 1.2 万步以内。"
    if request.budget_mode == "student":
        return "地铁/公交优先，打车只用于夜间返程或换乘成本过高时。"
    return "地铁串联核心片区，必要时用短途打车减少折返。"


def build_risk_control(request: TravelRequest, weather_day) -> list[str]:
    risks = ["热门景点提前预约，避免临时无票。", "每天保留 1 小时机动时间，应对排队和交通延误。"]
    if weather_day.precipitation_mm >= 3 or "雨" in weather_day.text:
        risks.append("带伞，优先执行室内替代路线。")
    if any("拒绝人挤人" in item or "不排队" in item for item in request.constraints):
        risks.append("避开 19:00-21:00 的网红夜景峰值时段，选择错峰或外围观景点。")
    return risks


def build_summary(request: TravelRequest, total_budget: int) -> str:
    return (
        f"为 {GROUP_LABEL[request.group]} {request.people} 人规划 {request.destination} {request.days} 天游，"
        f"预算模式为{MODE_LABEL[request.budget_mode]}，总预算约 {total_budget} 元。"
        "行程优先按片区串联，兼顾天气、预算和硬性限制。"
    )


def render_markdown(request, summary, weather, attractions, insights, transport, itinerary, budget, packing, warnings, adjustment_log, travel_decision, tool_plan, quality_issues) -> str:
    lines = [
        f"# 旅行伙计攻略：{request.origin} -> {request.destination}",
        "",
        f"## 总览",
        summary,
        "",
        "## 预算",
        f"- 住宿：{budget.lodging} 元",
        f"- 餐饮：{budget.food} 元",
        f"- 市内交通：{budget.local_transport} 元",
        f"- 往返大交通：{budget.intercity_transport} 元",
        f"- 门票体验：{budget.tickets} 元",
        f"- 机动金：{budget.buffer} 元",
        "",
        "## 天气提醒",
    ]
    for day in weather.days:
        lines.append(f"- {day.date}：{day.text}，{day.temp_min}-{day.temp_max}℃，降水 {day.precipitation_mm}mm。{day.advice}")
    lines.extend(["", "## 交通方案"])
    for option in transport:
        lines.append(f"- {option.name}：{option.total_time}，{option.estimated_cost}。适合：{option.best_for}。注意：{option.caution}")
    if not transport:
        lines.append("- 本次判断为同城或近距离规划，未生成城际交通方案，优先使用市内公共交通/短途打车。")
    lines.extend(["", "## Agent 工具调用计划"])
    for reason in tool_plan.reasons:
        lines.append(f"- {reason}")
    lines.extend(["", "## 分天行程"])
    if itinerary:
        for day in itinerary:
            lines.extend([f"### Day {day.day}｜{day.date}｜{day.theme}", f"- 片区：{day.area}", f"- 预算：约 {day.daily_budget} 元"])
            for slot in day.slots:
                lines.append(f"- {slot.time}：{slot.title}。{slot.detail} 费用：{slot.cost}。")
            lines.append(f"- 美食：{'；'.join(day.food[:3])}")
            lines.append(f"- 交通：{day.transport}")
            lines.append(f"- 风险控制：{'；'.join(day.risk_control)}")
    else:
        lines.append(f"- {travel_decision['detail']}")
    lines.extend(["", "## 候选景点"])
    for item in attractions:
        lines.append(f"- {item.name}｜{item.category}｜{item.area}｜{item.price}｜{item.open_time}｜地图：{item.map_url}")
    lines.extend(["", "## 方案自检"])
    for issue in quality_issues:
        lines.append(f"- {issue.severity}｜{issue.title}：{issue.detail}")
    lines.extend(["", "## 攻略清洗结论"])
    for insight in insights:
        lines.append(f"- {insight.title}：{insight.content}（{insight.source}，可信度 {insight.confidence}）")
    lines.extend(["", "## 行李清单", "- " + "\n- ".join(packing)])
    lines.extend(["", "## 调整记录"])
    lines.extend([f"- {item}" for item in adjustment_log] or ["- 当前方案未触发预算或天气替换。"])
    lines.extend(["", "## 风险边界"])
    lines.extend([f"- {item}" for item in warnings])
    return "\n".join(lines).strip() + "\n"


async def maybe_polish_with_deepseek(markdown: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return markdown
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = "请在不新增事实、不编造票价车次库存的前提下，润色下面旅行攻略，使其更适合直接发给用户。保留 Markdown 结构：\n\n" + markdown[:12000]
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return content.strip() + "\n"
    except Exception:
        return markdown
