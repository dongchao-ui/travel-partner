from __future__ import annotations

from app.schemas import GuideInsight, TravelRequest
from app.storage import search_private_knowledge


def collect_guide_insights(request: TravelRequest) -> list[GuideInsight]:
    insights = [
        GuideInsight(
            title="广告过滤策略",
            content="对单一平台反复出现的店铺、夸张种草词和引流话术降低权重，优先采用跨平台重复出现的避坑与路线建议。",
            source="Agent 清洗规则",
            confidence="high",
        ),
        GuideInsight(
            title="短途旅行节奏",
            content="学生和年轻上班族短途出行应优先保证核心片区深度游，避免每天跨 3 个以上片区导致交通时间吞噬体验。",
            source="通用旅行经验库",
            confidence="high",
        ),
        GuideInsight(
            title="预算控制",
            content="把不可压缩的大交通预算先锁定，再动态调整住宿、餐饮和门票；超预算时优先替换高价门票和打车路段。",
            source="预算规则库",
            confidence="high",
        ),
    ]

    if any("不吃辣" in item for item in request.constraints):
        insights.append(
            GuideInsight(
                title="饮食限制",
                content="美食推荐需增加清淡备选，点单时明确少辣/不辣，避免把地方特色默认等同于重口味。",
                source="用户硬约束",
                confidence="high",
            )
        )

    if request.use_private_knowledge:
        query = f"{request.destination} {' '.join(request.interests)} {request.private_notes}"
        for item in search_private_knowledge(query):
            insights.append(GuideInsight(title="私有攻略命中", content=item, source="本地 RAG 知识库", confidence="medium"))

    return insights[:8]
