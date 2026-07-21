from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

from app.schemas import WeatherDay, WeatherReport


WEATHER_TEXT = {
    0: "晴",
    1: "多云",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "有雾",
    51: "小雨",
    53: "小雨",
    55: "小雨",
    61: "有雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷阵雨",
}


async def get_weather(destination: str, days: int, start_date: date | None = None) -> WeatherReport:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            location = await geocode(client, destination)
            forecast_start = start_date or date.today()
            forecast_end = forecast_start + timedelta(days=max(1, min(days, 10)) - 1)
            params = {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "start_date": forecast_start.isoformat(),
                "end_date": forecast_end.isoformat(),
                "timezone": "Asia/Shanghai",
            }
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            data = response.json()["daily"]
            weather_days = []
            for index, current_date in enumerate(data["time"][:days]):
                code = int(data["weather_code"][index])
                temp_max = round(data["temperature_2m_max"][index])
                temp_min = round(data["temperature_2m_min"][index])
                precipitation = float(data["precipitation_sum"][index] or 0)
                text = WEATHER_TEXT.get(code, "天气变化")
                weather_days.append(
                    WeatherDay(
                        date=current_date,
                        text=text,
                        temp_min=temp_min,
                        temp_max=temp_max,
                        precipitation_mm=precipitation,
                        advice=build_weather_advice(text, temp_max, precipitation),
                    )
                )
            return WeatherReport(source="Open-Meteo 实时天气", location_name=location["name"], days=weather_days, warnings=build_warnings(weather_days))
    except Exception as error:
        await asyncio.sleep(0)
        return fallback_weather(destination, days, str(error), start_date)


async def geocode(client: httpx.AsyncClient, destination: str) -> dict:
    response = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": destination, "count": 1, "language": "zh", "format": "json"},
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ValueError(f"未找到目的地坐标：{destination}")
    first = results[0]
    return {"name": first.get("name", destination), "latitude": first["latitude"], "longitude": first["longitude"]}


def build_weather_advice(text: str, temp_max: int, precipitation: float) -> str:
    if precipitation >= 5 or "雨" in text:
        return "雨天优先安排博物馆、商圈、咖啡馆等室内点位，带伞和防水鞋。"
    if temp_max >= 33:
        return "高温日减少午后暴晒路段，增加室内休息和补水。"
    if temp_max <= 8:
        return "气温偏低，注意保暖，晚间活动缩短室外停留。"
    return "天气适合常规户外游玩，注意根据体力调整节奏。"


def build_warnings(days: list[WeatherDay]) -> list[str]:
    warnings = []
    if any(day.precipitation_mm >= 5 for day in days):
        warnings.append("出行周期内存在明显降水，已在行程中加入室内替代方案。")
    if any(day.temp_max >= 33 for day in days):
        warnings.append("部分日期温度较高，建议避开 12:00-15:00 长时间户外排队。")
    return warnings


def fallback_weather(destination: str, days: int, reason: str, start_date: date | None = None) -> WeatherReport:
    today = start_date or date.today()
    fallback_days = [
        WeatherDay(
            date=(today + timedelta(days=index)).isoformat(),
            text=["多云", "有雨", "晴", "阴"][index % 4],
            temp_min=20 + index % 3,
            temp_max=28 + index % 4,
            precipitation_mm=3.5 if index % 4 == 1 else 0,
            advice="天气接口不可用，使用演示天气；出发前请再次核对实时预报。",
        )
        for index in range(days)
    ]
    return WeatherReport(source="演示天气兜底", location_name=destination, days=fallback_days, warnings=[f"天气接口暂不可用：{reason}"])
