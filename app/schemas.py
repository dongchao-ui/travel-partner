from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator


BudgetMode = Literal["student", "value", "comfort"]
TravelGroup = Literal["solo", "couple", "friends", "family"]
Pace = Literal["relaxed", "balanced", "intense"]


class BudgetBreakdown(BaseModel):
    lodging: int = 0
    food: int = 0
    local_transport: int = 0
    intercity_transport: int = 0
    tickets: int = 0
    buffer: int = 0

    @computed_field
    @property
    def total(self) -> int:
        return self.lodging + self.food + self.local_transport + self.intercity_transport + self.tickets + self.buffer


class TravelRequest(BaseModel):
    origin: str = Field(default="当前位置", min_length=1, max_length=30)
    destination: str = Field(..., min_length=1, max_length=30)
    start_date: date | None = None
    end_date: date | None = None
    days: int = Field(default=3, ge=1, le=10)
    group: TravelGroup = "friends"
    people: int = Field(default=2, ge=1, le=12)
    budget_total: int = Field(default=1800, ge=300, le=100000)
    budget_mode: BudgetMode = "value"
    interests: list[str] = Field(default_factory=lambda: ["城市逛吃", "小众打卡"])
    constraints: list[str] = Field(default_factory=list)
    must_have: str = ""
    private_notes: str = ""
    use_private_knowledge: bool = True
    pace: Pace = "balanced"

    @field_validator("interests", "constraints", mode="before")
    @classmethod
    def coerce_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(value)


class WeatherDay(BaseModel):
    date: str
    text: str
    temp_min: int
    temp_max: int
    precipitation_mm: float
    advice: str


class WeatherReport(BaseModel):
    source: str
    location_name: str
    days: list[WeatherDay]
    warnings: list[str] = Field(default_factory=list)


class Attraction(BaseModel):
    name: str
    category: str
    area: str
    price: str
    open_time: str
    duration: str
    reason: str
    tips: list[str]
    indoor: bool = False
    cost_level: Literal["low", "mid", "high"] = "mid"
    evidence: list[str] = Field(default_factory=list)


class GuideInsight(BaseModel):
    title: str
    content: str
    source: str
    confidence: Literal["low", "medium", "high"] = "medium"


class TransportOption(BaseModel):
    name: str
    total_time: str
    estimated_cost: str
    best_for: str
    steps: list[str]
    caution: str


class TimeSlot(BaseModel):
    time: str
    title: str
    detail: str
    cost: str
    weather_hint: str


class DayPlan(BaseModel):
    day: int
    date: str
    theme: str
    area: str
    slots: list[TimeSlot]
    food: list[str]
    transport: str
    daily_budget: int
    risk_control: list[str]


class PlanResponse(BaseModel):
    plan_id: str
    summary: str
    request: TravelRequest
    weather: WeatherReport
    attractions: list[Attraction]
    guide_insights: list[GuideInsight]
    transport_options: list[TransportOption]
    itinerary: list[DayPlan]
    budget: BudgetBreakdown
    packing_list: list[str]
    warnings: list[str]
    adjustment_log: list[str]
    markdown: str
    export_url: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class UploadResponse(BaseModel):
    filename: str
    characters: int
    chunks: int
    message: str
