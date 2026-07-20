# 旅行伙计 TravelMate Agent

一个面向学生和年轻短途出行人群的 AI 旅行规划智能体 Demo。

## 能力

- 天气查询与行程调整
- 城市景点候选检索
- 公开攻略清洗与摘要提取
- 交通方案推荐
- 预算拆分与自动兜底
- 本地攻略上传与轻量 RAG 召回
- Markdown 攻略导出

## 运行

```powershell
cd D:\codex-chat\travelmate-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

打开：

http://127.0.0.1:8000

## 可选环境变量

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
PORT=8000
```

配置 DeepSeek 后，系统会在输出 Markdown 前做一次润色；没配置也能完整运行。

## 技术栈

Python、FastAPI、Pydantic、httpx、Open-Meteo、OpenStreetMap/维基百科公开接口、Markdown 导出、Docker

## 简历描述

独立开发一站式旅行规划 Agent，整合天气、景点、攻略清洗、交通和预算模块，用户输入出发地、目的地、预算、天数和偏好后，自动生成可落地的分天旅行方案，并支持本地攻略上传、偏好记忆和 Markdown 导出。

