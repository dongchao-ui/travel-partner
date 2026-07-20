from __future__ import annotations

import httpx

from app.schemas import Attraction, TravelRequest


CITY_FALLBACKS: dict[str, list[dict]] = {
    "重庆": [
        {"name": "洪崖洞民俗风貌区", "category": "夜景地标", "area": "渝中区嘉陵江滨江路88号，近小什字/解放碑", "price": "免费", "open_time": "全天外观", "duration": "1.5 小时", "indoor": False},
        {"name": "山城步道仁爱堂段", "category": "城市漫游", "area": "渝中区中兴路234号附近，近较场口", "price": "免费", "open_time": "全天", "duration": "2 小时", "indoor": False},
        {"name": "重庆中国三峡博物馆", "category": "博物馆", "area": "渝中区人民路236号，人民大礼堂对面", "price": "免费预约", "open_time": "通常 09:00-17:00，周一闭馆", "duration": "2 小时", "indoor": True},
        {"name": "鹅岭二厂文创公园", "category": "文创街区", "area": "渝中区鹅岭正街1号，近鹅岭地铁站", "price": "免费，店铺另计", "open_time": "10:00-22:00", "duration": "2 小时", "indoor": False},
        {"name": "李子坝单轨穿楼观景平台", "category": "轻轨打卡", "area": "渝中区李子坝正街62号旁，李子坝站外", "price": "免费", "open_time": "全天", "duration": "40 分钟", "indoor": False},
        {"name": "磁器口古镇正街", "category": "古镇小吃", "area": "沙坪坝区磁器口正街，磁器口地铁站旁", "price": "免费", "open_time": "全天，店铺白天为主", "duration": "2.5 小时", "indoor": False},
        {"name": "观音桥好吃街", "category": "夜市美食", "area": "江北区观音桥步行街星天广场B区", "price": "人均 40-90", "open_time": "午后至夜间", "duration": "1.5 小时", "indoor": False},
    ],
    "武汉": [
        {"name": "江汉路步行街", "category": "城市逛吃", "area": "江汉区江汉路，江汉路地铁站C口附近", "price": "免费，餐饮另计", "open_time": "全天，夜间更热闹", "duration": "2 小时", "indoor": False},
        {"name": "黎黄陂路街头博物馆", "category": "小众打卡", "area": "江岸区黎黄陂路，近中山大道/汉口江滩", "price": "免费", "open_time": "全天外观", "duration": "1.5 小时", "indoor": False},
        {"name": "湖北省博物馆", "category": "博物馆", "area": "武昌区东湖路160号，近省博湖北日报地铁站", "price": "免费预约", "open_time": "通常 09:00-17:00，周一闭馆", "duration": "3 小时", "indoor": True},
        {"name": "东湖听涛景区", "category": "自然风光", "area": "武昌区沿湖大道2号，近省博/梨园广场", "price": "免费，景区项目另计", "open_time": "全天", "duration": "2.5 小时", "indoor": False},
        {"name": "黄鹤楼公园", "category": "历史古迹", "area": "武昌区蛇山西山坡特1号，近司门口黄鹤楼地铁站", "price": "约 70 元", "open_time": "白天开放", "duration": "2 小时", "indoor": False},
        {"name": "昙华林历史文化街区", "category": "文艺街区", "area": "武昌区昙华林，近螃蟹岬地铁站", "price": "免费，店铺另计", "open_time": "全天，店铺午后为主", "duration": "1.5 小时", "indoor": False},
        {"name": "户部巷", "category": "小吃街", "area": "武昌区自由路，近司门口黄鹤楼地铁站", "price": "人均 30-80", "open_time": "午后至夜间", "duration": "1 小时", "indoor": False},
        {"name": "武汉美术馆汉口馆", "category": "美术馆", "area": "江岸区保华街2号，近中山大道/江汉路", "price": "免费预约", "open_time": "通常 09:00-17:00，周一闭馆", "duration": "1.5 小时", "indoor": True},
    ],
    "成都": [
        {"name": "成都博物馆", "category": "博物馆", "area": "青羊区小河街1号，天府广场西侧", "price": "免费预约", "open_time": "通常 09:00-17:00，周一闭馆", "duration": "2 小时", "indoor": True},
        {"name": "宽窄巷子窄巷子段", "category": "城市街区", "area": "青羊区长顺上街127号，宽窄巷子地铁站旁", "price": "免费", "open_time": "全天", "duration": "1.5 小时", "indoor": False},
        {"name": "人民公园鹤鸣茶社", "category": "慢生活", "area": "青羊区少城路12号人民公园内", "price": "免费入园，茶饮另计", "open_time": "白天", "duration": "1.5 小时", "indoor": False},
        {"name": "武侯祠博物馆", "category": "历史古迹", "area": "武侯区武侯祠大街231号", "price": "约 50 元", "open_time": "白天开放", "duration": "2 小时", "indoor": False},
        {"name": "锦里古街", "category": "夜游小吃", "area": "武侯区武侯祠大街231号旁", "price": "免费，餐饮另计", "open_time": "全天，夜间更热闹", "duration": "1.5 小时", "indoor": False},
    ],
    "西安": [
        {"name": "陕西历史博物馆", "category": "博物馆", "area": "雁塔区小寨东路91号，近小寨/大雁塔", "price": "免费预约", "open_time": "通常 09:00-17:30，周一闭馆", "duration": "3 小时", "indoor": True},
        {"name": "西安城墙永宁门段", "category": "历史古迹", "area": "碑林区南大街2号，永宁门地铁站旁", "price": "约 54 元", "open_time": "白天至晚间", "duration": "2 小时", "indoor": False},
        {"name": "大唐不夜城步行街", "category": "夜景演艺", "area": "雁塔区慈恩路46号附近，大雁塔南广场南侧", "price": "免费", "open_time": "夜间更适合", "duration": "2 小时", "indoor": False},
        {"name": "北院门回民街", "category": "小吃街区", "area": "莲湖区北院门，近钟楼地铁站", "price": "人均 40-90", "open_time": "午后至夜间", "duration": "1.5 小时", "indoor": False},
        {"name": "西安碑林博物馆", "category": "历史博物馆", "area": "碑林区三学街15号，近书院门", "price": "约 65 元", "open_time": "白天开放", "duration": "2 小时", "indoor": True},
    ],
    "杭州": [
        {"name": "西湖断桥残雪", "category": "自然风光", "area": "西湖区北山街，近凤起路/龙翔桥地铁站", "price": "免费", "open_time": "全天", "duration": "3 小时", "indoor": False},
        {"name": "浙江省博物馆之江馆区", "category": "博物馆", "area": "西湖区枫桦路馆区，需按实际开放馆区预约", "price": "免费预约", "open_time": "通常 09:00-17:00，周一闭馆", "duration": "2 小时", "indoor": True},
        {"name": "河坊街步行街", "category": "城市逛吃", "area": "上城区河坊街，近定安路地铁站", "price": "免费，餐饮另计", "open_time": "全天，夜间更热闹", "duration": "1.5 小时", "indoor": False},
        {"name": "九溪烟树", "category": "小众自然", "area": "西湖区龙井村南侧九溪路，近九溪公交站", "price": "免费", "open_time": "白天", "duration": "2.5 小时", "indoor": False},
    ],
}


async def find_attractions(request: TravelRequest) -> list[Attraction]:
    raw_places = CITY_FALLBACKS.get(request.destination, [])
    web_places, web_evidence = await search_wikipedia_places(request.destination)
    if not raw_places:
        raw_places = web_places or build_unverified_specific_place(request.destination)

    ranked = sorted(raw_places, key=lambda item: score_place(item, request), reverse=True)
    return [normalize_place(item, request, web_evidence) for item in ranked[:8] if is_specific_place(item)]


async def search_wikipedia_places(destination: str) -> tuple[list[dict], list[str]]:
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.get(
                "https://zh.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": f"{destination} 景点 地标 博物馆 公园", "srlimit": 8, "format": "json", "origin": "*"},
                headers={"User-Agent": "TravelMateAgent/0.1"},
            )
            response.raise_for_status()
            results = response.json().get("query", {}).get("search", [])
            places = []
            evidence = []
            for item in results:
                title = clean_title(item.get("title", ""))
                if not title or not looks_like_specific_title(destination, title):
                    continue
                places.append(
                    {
                        "name": title,
                        "category": infer_category(title),
                        "area": f"{destination}市内，建议出发前用地图搜索“{title}”核对入口",
                        "price": "待核实",
                        "open_time": "待核实",
                        "duration": "1.5-2 小时",
                        "indoor": any(token in title for token in ["馆", "博物馆", "美术馆", "纪念馆"]),
                    }
                )
                evidence.append(f"维基百科摘要：{title}")
            return places, evidence or ["公开百科未召回足够具体景点，建议接入地图 POI 源补强。"]
    except Exception:
        return [], ["公开百科/攻略检索暂不可用，已使用内置城市候选库。"]


def build_unverified_specific_place(destination: str) -> list[dict]:
    return [
        {"name": f"{destination}博物馆", "category": "博物馆", "area": f"{destination}市内，需用地图核对具体馆址和入口", "price": "待核实", "open_time": "待核实", "duration": "2 小时", "indoor": True},
    ]


def clean_title(title: str) -> str:
    return title.replace("(消歧义)", "").strip()


def looks_like_specific_title(destination: str, title: str) -> bool:
    vague_words = ["旅游", "列表", "行政区划", "历史", "文化", "经济", "交通", "街区", "城市", "城区"]
    if len(title) < 2 or any(word == title or title.endswith(word) for word in vague_words):
        return False
    return destination in title or any(token in title for token in ["楼", "馆", "园", "湖", "山", "寺", "桥", "巷", "街", "塔", "宫", "城", "洞", "滩"])


def infer_category(title: str) -> str:
    if any(token in title for token in ["博物馆", "美术馆", "纪念馆"]):
        return "室内场馆"
    if any(token in title for token in ["湖", "山", "公园", "滩"]):
        return "自然风光"
    if any(token in title for token in ["街", "巷", "路"]):
        return "城市逛吃"
    return "景点"


def is_specific_place(place: dict) -> bool:
    name = place.get("name", "")
    vague_names = ["老街区", "城市公园", "夜市/美食街", "核心商圈", "市中心", "老城区"]
    return bool(name) and not any(word in name for word in vague_names)


def score_place(place: dict, request: TravelRequest) -> int:
    score = 70
    joined = f"{place.get('name', '')}{place.get('category', '')}{place.get('area', '')}"
    for interest in request.interests:
        if any(token in joined for token in interest.split()):
            score += 8
        if interest in joined:
            score += 12
    if request.budget_mode == "student" and "免费" in place.get("price", ""):
        score += 10
    if any("雨" in item for item in request.constraints) and place.get("indoor"):
        score += 8
    if any("少走路" in item or "怕走路" in item for item in request.constraints) and "步道" in place.get("name", ""):
        score -= 12
    if any("拒绝人挤人" in item or "不排队" in item for item in request.constraints) and place.get("category", "").startswith("夜景"):
        score -= 4
    return score


def normalize_place(place: dict, request: TravelRequest, evidence: list[str]) -> Attraction:
    category = place.get("category", "景点")
    cost_level = "low" if "免费" in place.get("price", "") else "mid"
    tips = [
        "出发前确认预约、开放时间和临时闭馆信息。",
        "同片区串联游玩，减少跨区往返。",
    ]
    if place.get("indoor"):
        tips.append("适合作为雨天或高温时段替代点。")
    if request.budget_mode == "student":
        tips.append("优先选择免费开放时段，把预算留给餐饮和交通。")
    return Attraction(
        name=place.get("name", "候选景点"),
        category=category,
        area=place.get("area", "待确认片区"),
        price=place.get("price", "待核实"),
        open_time=place.get("open_time", "待核实"),
        duration=place.get("duration", "1-2 小时"),
        reason=f"匹配你的偏好：{', '.join(request.interests) or '轻松旅行'}；适合放入 {request.days} 天游玩节奏。",
        tips=tips,
        indoor=bool(place.get("indoor")),
        cost_level=cost_level,
        evidence=evidence[:2],
    )
