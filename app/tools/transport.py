from __future__ import annotations

from app.schemas import TransportOption, TravelRequest


def plan_transport(request: TravelRequest) -> list[TransportOption]:
    destination_station = f"{request.destination}站/北站"
    origin_station = f"{request.origin}站/北站" if request.origin != "当前位置" else "就近高铁站/客运站"
    low_budget = request.budget_mode == "student" or request.budget_total / max(request.people, 1) < 1200

    options = [
        TransportOption(
            name="高铁/动车优先方案",
            total_time="约 2-8 小时，取决于城市距离",
            estimated_cost="约 150-650 元/人",
            best_for="时间稳定、适合短途周末游",
            steps=[
                f"{request.origin}市区前往 {origin_station}",
                f"{origin_station} 乘高铁/动车至 {destination_station}",
                f"{destination_station} 转地铁/公交到住宿片区",
            ],
            caution="Demo 不编造具体车次、余票和实时票价；生产版需接入 12306 或票务聚合 API。",
        ),
        TransportOption(
            name="普速火车/大巴省钱方案",
            total_time="约 5-12 小时",
            estimated_cost="约 80-300 元/人",
            best_for="学生穷游、预算优先",
            steps=[
                "优先查询夜间普速火车或城际大巴",
                "到达后先放行李，再安排低体力消耗点位",
                "返程预留 90 分钟以上到站缓冲",
            ],
            caution="低价方案通常牺牲时间和舒适度，晕车用户不建议选长途大巴。",
        ),
        TransportOption(
            name="舒适少折腾方案",
            total_time="约 3-6 小时",
            estimated_cost="约 350-900 元/人",
            best_for="情侣/家庭、少步行、行李较多",
            steps=[
                "选择白天到达的高铁或航班",
                "抵达后打车到酒店，减少换乘",
                "市内以地铁 + 短途打车串联同片区景点",
            ],
            caution="舒适方案费用较高，若超预算会自动压缩餐饮/门票或改公共交通。",
        ),
    ]

    if low_budget:
        return [options[1], options[0], options[2]]
    return options
