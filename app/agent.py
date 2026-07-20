from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import httpx

from app.schemas import DayPlan, PlanResponse, TimeSlot, TravelRequest
from app.storage import update_memory, write_export
from app.tools.attractions import find_attractions
from app.tools.budget import build_packing_list, calculate_budget
from app.tools.content import collect_guide_insights
from app.tools.transport import plan_transport
from app.tools.weather import get_weather


GROUP_LABEL = {"solo": "单人", "couple": "情侣", "friends": "朋友/同学", "family": "家庭"}
MODE_LABEL = {"student": "学生穷游", "value": "性价比", "comfort": "轻奢舒适"}


async def build_travel_plan(request: TravelRequest) -> PlanResponse:
    normalized_request = normalize_request(request)
    weather = await get_weather(normalized_request.destination, normalized_request.days)
    attractions = await find_attractions(normalized_request)
    guide_insights = collect_guide_insights(normalized_request)
    transport_options = plan_transport(normalized_request)
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
        [*budget_log, *itinerary_log],
        travel_decision,
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
        weather=weather,
        attractions=attractions,
        guide_insights=guide_insights,
        transport_options=transport_options,
        itinerary=itinerary,
        budget=budget,
        packing_list=packing_list,
        warnings=warnings,
        adjustment_log=[*budget_log, *itinerary_log],
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


def build_itinerary(request: TravelRequest, weather, attractions, budget) -> tuple[list[DayPlan], list[str]]:
    logs = []
    plans: list[DayPlan] = []
    daily_budget = max(round(request.budget_total / max(request.days, 1)), 1)
    start = request.start_date or date.today()
    indoor_pool = [item for item in attractions if item.indoor]
    outdoor_pool = [item for item in attractions if not item.indoor]
    all_pool = attractions[:]

    for index in range(request.days):
        weather_day = weather.days[index % len(weather.days)]
        current_date = (start + timedelta(days=index)).isoformat()
        rainy = weather_day.precipitation_mm >= 3 or "雨" in weather_day.text
        primary_pool = indoor_pool if rainy and indoor_pool else outdoor_pool or all_pool
        used_names: set[str] = set()
        morning = choose_distinct_place(primary_pool, index, used_names)
        afternoon = choose_distinct_place(all_pool, index + 2, used_names)
        evening = choose_evening(attractions, index, used_names)

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
        return TimeSlot(time=time_label, title="自由探索", detail=fallback, cost="按实际消费", weather_hint=weather_hint)
    return TimeSlot(
        time=time_label,
        title=attraction.name,
        detail=f"{attraction.category}，建议游玩 {attraction.duration}。{attraction.reason}",
        cost=attraction.price,
        weather_hint=weather_hint,
    )


def choose_distinct_place(places, index: int, used_names: set[str]):
    if not places:
        return None
    for offset in range(len(places)):
        place = places[(index + offset) % len(places)]
        if place.name not in used_names:
            used_names.add(place.name)
            return place
    return None


def choose_evening(attractions, index: int, used_names: set[str]):
    evening_candidates = [item for item in attractions if any(token in item.category for token in ["夜", "小吃", "逛吃", "街区"])]
    place = choose_distinct_place(evening_candidates, index, used_names)
    if place:
        return place
    return choose_distinct_place(attractions, index + 3, used_names)


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


def render_markdown(request, summary, weather, attractions, insights, transport, itinerary, budget, packing, warnings, adjustment_log, travel_decision) -> str:
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
        lines.append(f"- {item.name}｜{item.category}｜{item.area}｜{item.price}｜{item.open_time}")
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
