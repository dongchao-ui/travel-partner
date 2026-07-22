const form = document.querySelector("#planForm");
const resultEl = document.querySelector("#result");
const submitBtn = document.querySelector("#submitBtn");
const sampleBtn = document.querySelector("#sampleBtn");
const uploadBtn = document.querySelector("#uploadBtn");
const guideFile = document.querySelector("#guideFile");
const uploadStatus = document.querySelector("#uploadStatus");
const healthBadge = document.querySelector("#healthBadge");
let currentPlan = null;

window.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) window.lucide.createIcons();
  setToday();
  await checkHealth();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = readForm();
  await generatePlan("/api/plan", payload);
});

sampleBtn.addEventListener("click", async () => {
  applySampleScenario();
  await generatePlan("/api/plan", readForm());
});

uploadBtn.addEventListener("click", async () => {
  const file = guideFile.files?.[0];
  if (!file) {
    uploadStatus.textContent = "请先选择一个 PDF/TXT/MD 文件。";
    return;
  }
  uploadBtn.disabled = true;
  uploadStatus.textContent = "正在上传并切分攻略...";
  try {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/upload", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "上传失败");
    uploadStatus.textContent = `${data.filename} 已入库，${data.characters} 字，${data.chunks} 个片段。`;
  } catch (error) {
    uploadStatus.textContent = error.message;
  } finally {
    uploadBtn.disabled = false;
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    healthBadge.textContent = data.deepseek_enabled ? "DeepSeek 已启用" : "本地规则引擎";
    healthBadge.classList.toggle("ok", true);
  } catch {
    healthBadge.textContent = "服务未连接";
  }
}

async function generatePlan(url, payload) {
  submitBtn.disabled = true;
  resultEl.className = "result";
  resultEl.innerHTML = `<div class="loading"><i data-lucide="loader-circle"></i><strong>Agent 正在调用工具链...</strong><span>天气、景点、攻略清洗、交通和预算会并行整理。</span></div>`;
  if (window.lucide) window.lucide.createIcons();
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "生成失败");
    renderPlan(data);
  } catch (error) {
    resultEl.innerHTML = `<div class="error"><strong>生成失败</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    submitBtn.disabled = false;
    if (window.lucide) window.lucide.createIcons();
  }
}

function readForm() {
  const data = new FormData(form);
  return {
    origin: data.get("origin") || "当前位置",
    destination: data.get("destination"),
    start_date: data.get("start_date") || null,
    days: Number(data.get("days") || 3),
    people: Number(data.get("people") || 2),
    group: data.get("group"),
    budget_total: Number(data.get("budget_total") || 1800),
    budget_mode: data.get("budget_mode"),
    interests: checkedValues("interests"),
    constraints: checkedValues("constraints"),
    private_notes: data.get("private_notes") || "",
    use_private_knowledge: true,
  };
}

function applySampleScenario() {
  form.elements.origin.value = "西安";
  form.elements.destination.value = "重庆";
  form.elements.days.value = "3";
  form.elements.people.value = "2";
  form.elements.budget_total.value = "1800";
  form.elements.group.value = "friends";
  form.elements.budget_mode.value = "student";
  form.elements.start_date.value = new Date().toISOString().slice(0, 10);
  form.elements.private_notes.value = "想轻松一点，尽量住地铁旁边，偏夜景和夜市，不想排队。";
  setChecked("interests", ["城市逛吃", "小众打卡", "夜市美食"]);
  setChecked("constraints", ["少走路", "拒绝人挤人"]);
}

function setChecked(name, values) {
  document.querySelectorAll(`[data-name="${name}"] input`).forEach((item) => {
    item.checked = values.includes(item.value);
  });
}

function groupLabel(value) {
  return (
    {
      solo: "单人",
      couple: "情侣",
      friends: "朋友/同学",
      family: "家庭",
    }[value] || value
  );
}

function modeLabel(value) {
  return (
    {
      student: "学生穷游",
      value: "性价比",
      comfort: "轻奢舒适",
    }[value] || value
  );
}

function checkedValues(name) {
  return [...document.querySelectorAll(`[data-name="${name}"] input:checked`)].map((item) => item.value);
}

function renderPlan(plan) {
  currentPlan = plan;
  resultEl.className = "result";
  resultEl.innerHTML = `
    <section class="summary-band">
      <div>
        <p class="eyebrow">方案 ${escapeHtml(plan.plan_id)}</p>
        <h2>${escapeHtml(plan.request.destination)} ${plan.request.days} 天游</h2>
        <p>${escapeHtml(plan.summary)}</p>
        <div class="summary-meta">
          <span><i data-lucide="users"></i>${escapeHtml(groupLabel(plan.request.group))}</span>
          <span><i data-lucide="wallet"></i>${escapeHtml(modeLabel(plan.request.budget_mode))}</span>
          <span><i data-lucide="cloud-sun"></i>${escapeHtml(plan.weather.source)}</span>
          <span><i data-lucide="file-down"></i>已导出 Markdown</span>
        </div>
      </div>
      <a class="download" href="${plan.export_url}" target="_blank"><i data-lucide="download"></i>导出 Markdown</a>
    </section>

    <section class="metric-grid">
      ${metric("cloud-sun", "天气来源", plan.weather.source)}
      ${metric("landmark", "候选景点", `${plan.attractions.length} 个`)}
      ${metric("train", "交通方案", `${plan.transport_options.length} 套`)}
      ${metric("wallet", "预算合计", `${plan.budget.total} 元`)}
    </section>

    ${renderTravelDecision(plan)}
    ${renderQuickAdjust()}

    <section class="module-board">
      <div class="module-tabs" role="tablist" aria-label="方案模块">
        <button class="module-tab active" type="button" data-module="weather"><i data-lucide="cloud-sun"></i>天气建议</button>
        <button class="module-tab" type="button" data-module="transport"><i data-lucide="train"></i>交通方案</button>
        <button class="module-tab" type="button" data-module="notes"><i data-lucide="shield-check"></i>注意事项</button>
        <button class="module-tab" type="button" data-module="cleanup"><i data-lucide="filter"></i>攻略清洗</button>
        <button class="module-tab" type="button" data-module="attractions"><i data-lucide="landmark"></i>景点规划</button>
        <button class="module-tab" type="button" data-module="itinerary"><i data-lucide="calendar-days"></i>每日行程</button>
      </div>
      <div class="module-content">
        <section class="module-panel active" data-panel="weather">${renderWeatherModule(plan)}</section>
        <section class="module-panel" data-panel="transport">${renderTransportModule(plan.transport_options)}</section>
        <section class="module-panel" data-panel="notes">${renderNotesModule(plan)}</section>
        <section class="module-panel" data-panel="cleanup">${renderCleanupModule(plan.guide_insights)}</section>
        <section class="module-panel" data-panel="attractions">${renderAttractionModule(plan.attractions)}</section>
        <section class="module-panel" data-panel="itinerary">${renderItineraryModule(plan)}</section>
      </div>
    </section>
  `;
  bindModuleTabs();
  bindQuickAdjustButtons();
  if (window.lucide) window.lucide.createIcons();
}

function renderQuickAdjust() {
  return `
    <section class="quick-adjust">
      <div>
        <p class="eyebrow">二次微调</p>
        <strong>基于当前方案快速重排</strong>
      </div>
      <div class="quick-actions">
        <button class="secondary" type="button" data-adjust="降低预算"><i data-lucide="wallet"></i>降低预算</button>
        <button class="secondary" type="button" data-adjust="少走路"><i data-lucide="footprints"></i>少走路</button>
        <button class="secondary" type="button" data-adjust="增加美食"><i data-lucide="utensils"></i>增加美食</button>
        <button class="secondary" type="button" data-adjust="雨天优先室内"><i data-lucide="umbrella"></i>雨天室内</button>
      </div>
    </section>
  `;
}

function bindQuickAdjustButtons() {
  document.querySelectorAll("[data-adjust]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!currentPlan) return;
      await generatePlan("/api/adjust-plan", {
        base_request: currentPlan.request,
        instruction: button.dataset.adjust,
      });
    });
  });
}

function bindModuleTabs() {
  document.querySelectorAll(".module-tab").forEach((button) => {
    button.addEventListener("click", () => {
      const module = button.dataset.module;
      document.querySelectorAll(".module-tab").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".module-panel").forEach((panelEl) => panelEl.classList.toggle("active", panelEl.dataset.panel === module));
      if (window.lucide) window.lucide.createIcons();
    });
  });
}

function renderTravelDecision(plan) {
  const advice = getWeatherDecision(plan.weather);
  return `
    <section class="decision-card ${advice.level}">
      <div class="decision-icon"><i data-lucide="${advice.icon}"></i></div>
      <div>
        <p class="eyebrow">出行判断</p>
        <h3>${escapeHtml(advice.title)}</h3>
        <p>${escapeHtml(advice.detail)}</p>
      </div>
      <div class="decision-facts">
        <span>${advice.rainyDays}/${plan.weather.days.length} 天降雨</span>
        <span>${escapeHtml(plan.weather.location_name)}</span>
      </div>
    </section>
  `;
}

function getWeatherDecision(weather) {
  const rainyDays = weather.days.filter((day) => isRainyDay(day));
  const heavyRain = weather.days.some((day) => day.precipitation_mm >= 10 || /大雨|暴雨|雷/.test(day.text));
  const mostlyRainy = rainyDays.length >= Math.ceil(weather.days.length / 2);
  if (heavyRain || mostlyRainy) {
    return {
      level: "warn",
      icon: "cloud-rain",
      rainyDays: rainyDays.length,
      title: "这段时间不太适合硬出行，建议优先考虑改期",
      detail: "未来出行周期降雨占比较高，室外夜景、步行街和拍照体验会明显打折。下面仍保留雨天备选方案，但更推荐换到天气稳定的日期。",
    };
  }
  if (rainyDays.length) {
    return {
      level: "notice",
      icon: "umbrella",
      rainyDays: rainyDays.length,
      title: "可以出行，但需要准备雨天替代路线",
      detail: "行程里有部分降雨风险，建议把博物馆、商圈和室内餐饮作为优先备选，室外景点尽量放到少雨时段。",
    };
  }
  return {
    level: "ok",
    icon: "sun",
    rainyDays: 0,
    title: "天气适合按计划出行",
    detail: "当前周期没有明显降雨压力，可以正常执行行程，保留少量机动时间即可。",
  };
}

function isRainyDay(day) {
  return day.precipitation_mm >= 3 || /雨|雪|雷/.test(day.text);
}

function renderWeatherModule(plan) {
  const advice = getWeatherDecision(plan.weather);
  return `
    <div class="module-head">
      <div>
        <p class="eyebrow">天气建议</p>
        <h3>${escapeHtml(advice.title)}</h3>
      </div>
      <span class="module-badge">${escapeHtml(plan.weather.source)}</span>
    </div>
    <div class="weather-grid">
      ${plan.weather.days
        .map(
          (day) => `
          <article class="weather-day ${isRainyDay(day) ? "rainy" : ""}">
            <strong>${escapeHtml(day.date)}</strong>
            <b>${escapeHtml(day.text)} ${day.temp_min}-${day.temp_max}℃</b>
            <p>降水 ${day.precipitation_mm}mm</p>
            <small>${escapeHtml(day.advice)}</small>
          </article>`,
        )
        .join("")}
    </div>
  `;
}

function renderTransportModule(options) {
  return `
    <div class="module-head">
      <div>
        <p class="eyebrow">交通方案</p>
        <h3>按预算、时间和舒适度给出候选路线</h3>
      </div>
    </div>
    <div class="option-grid">
      ${options
        .map(
          (item) => `
          <article class="option-card">
            <strong>${escapeHtml(item.name)}</strong>
            <p>${escapeHtml(item.total_time)}｜${escapeHtml(item.estimated_cost)}</p>
            <ul>${item.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>
            <small>${escapeHtml(item.caution)}</small>
          </article>`,
        )
        .join("")}
    </div>
  `;
}

function renderNotesModule(plan) {
  return `
    <div class="module-head">
      <div>
        <p class="eyebrow">注意事项</p>
        <h3>预算、行李和风险边界</h3>
      </div>
    </div>
    <div class="notes-grid">
      ${renderBudget(plan.budget)}
      ${renderToolPlan(plan.tool_plan)}
      ${renderQualityIssues(plan.quality_issues)}
      ${renderList("行李清单", "backpack", plan.packing_list)}
      ${renderList("风险边界", "shield-alert", plan.warnings)}
    </div>
  `;
}

function renderCleanupModule(items) {
  const ruleItems = (items || []).filter((item) => !isPrivateInsight(item));
  const privateItems = (items || []).filter(isPrivateInsight);
  return `
    <div class="module-head">
      <div>
        <p class="eyebrow">攻略清洗</p>
        <h3>系统规则和私有 RAG 命中</h3>
      </div>
    </div>
    <div class="cleanup-grid">
      ${renderCleanupGroup("攻略清洗规则", "filter", ruleItems.length ? `<div class="insight-list rule-list">${ruleItems.map(renderInsightCard).join("")}</div>` : `<div class="empty-state">暂无系统清洗规则结果。</div>`)}
      ${renderCleanupGroup("私有 RAG 命中", "database", privateItems.length ? `<div class="rag-hit-list">${privateItems.map(renderRagHitCard).join("")}</div>` : `<div class="empty-state">本次没有命中私有攻略；上传或补充目的地攻略后会显示在这里。</div>`)}
    </div>
  `;
}

function renderCleanupGroup(title, icon, content) {
  return panel(title, icon, content, "cleanup-panel");
}

function renderToolPlan(toolPlan) {
  if (!toolPlan) return "";
  const tools = [
    ["天气", toolPlan.weather],
    ["景点", toolPlan.attractions],
    ["攻略", toolPlan.guide_search],
    ["交通", toolPlan.transport],
    ["预算", toolPlan.budget],
    ["私有 RAG", toolPlan.rag],
  ];
  return panel(
    "Agent 工具路由",
    "workflow",
    `<div class="tool-status">${tools
      .map(([name, enabled]) => `<span class="${enabled ? "enabled" : "disabled"}">${enabled ? "调用" : "跳过"} ${name}</span>`)
      .join("")}</div><ul>${toolPlan.reasons.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`,
  );
}

function renderQualityIssues(issues = []) {
  return panel(
    "方案自检",
    "badge-check",
    `<div class="quality-list">${issues
      .map(
        (item) => `
        <div class="quality-item ${escapeHtml(item.severity)}">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.detail)}</p>
        </div>`,
      )
      .join("")}</div>`,
  );
}

function renderAttractionModule(attractions) {
  return `
    <div class="module-head">
      <div>
        <p class="eyebrow">景点规划</p>
        <h3>按片区、价格和天气适配度筛选候选点</h3>
      </div>
    </div>
    <div class="attraction-grid">
      ${attractions
        .map(
          (item) => `
          <article class="attraction-card">
            <div class="attraction-top"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.category)}</span></div>
            <p class="attraction-location"><i data-lucide="map-pin"></i><span>${escapeHtml(item.area)}</span></p>
            <p>${escapeHtml(item.price)}｜${escapeHtml(item.open_time)}｜${escapeHtml(item.duration)}</p>
            <small>${escapeHtml(item.tips.slice(0, 2).join("；"))}</small>
            ${item.map_url ? `<a class="map-link" href="${escapeHtml(item.map_url)}" target="_blank" rel="noreferrer"><i data-lucide="navigation"></i>打开地图</a>` : ""}
          </article>`,
        )
        .join("")}
    </div>
  `;
}

function renderItineraryModule(plan) {
  const advice = getWeatherDecision(plan.weather);
  if (advice.level === "warn") {
    return `
      <div class="postpone-card">
        <p class="eyebrow">建议改期</p>
        <h3>${escapeHtml(advice.title)}</h3>
        <p>${escapeHtml(advice.detail)}</p>
        <div class="postpone-hint">
          <span><i data-lucide="cloud-rain"></i>${advice.rainyDays}/${plan.weather.days.length} 天降雨</span>
          <span><i data-lucide="calendar-x"></i>先看天气再排日程</span>
        </div>
      </div>
    `;
  }
  return `
    <div class="main-flow">
      <h3>每日行程</h3>
      ${plan.itinerary.map(renderDay).join("")}
    </div>
  `;
}

function renderDay(day) {
  return `
    <article class="day-block">
      <header>
        <span>Day ${day.day}</span>
        <div><strong>${escapeHtml(day.theme)}</strong><p>${escapeHtml(day.date)}｜${escapeHtml(day.area)}｜约 ${day.daily_budget} 元</p></div>
      </header>
      <div class="slots">
        ${day.slots
          .map(
            (slot) => `
            <div class="slot">
              <b>${escapeHtml(slot.time)}</b>
              <strong>${escapeHtml(slot.title)}</strong>
              <p>${escapeHtml(slot.detail)}</p>
              <small>${escapeHtml(slot.cost)}｜${escapeHtml(slot.weather_hint)}</small>
            </div>`,
          )
          .join("")}
      </div>
      <p class="line"><b>美食</b>${escapeHtml(day.food.slice(0, 3).join(" / "))}</p>
      <p class="line"><b>交通</b>${escapeHtml(day.transport)}</p>
      <p class="line"><b>风控</b>${escapeHtml(day.risk_control.join("；"))}</p>
    </article>
  `;
}

function renderBudget(budget) {
  const items = [
    ["住宿", budget.lodging],
    ["餐饮", budget.food],
    ["市内交通", budget.local_transport],
    ["往返交通", budget.intercity_transport],
    ["门票体验", budget.tickets],
    ["机动金", budget.buffer],
  ];
  return panel("预算拆分", "wallet", items.map(([k, v]) => `<div class="row"><span>${k}</span><strong>${v} 元</strong></div>`).join(""));
}

function renderWeather(weather) {
  return panel(
    "天气",
    "cloud-sun",
    weather.days.map((day) => `<div class="row"><span>${escapeHtml(day.date)} ${escapeHtml(day.text)}</span><strong>${day.temp_min}-${day.temp_max}℃</strong></div>`).join(""),
  );
}

function renderTransport(options) {
  return panel(
    "交通候选",
    "train",
    options
      .map((item) => `<div class="compact"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.total_time)}｜${escapeHtml(item.estimated_cost)}</p><small>${escapeHtml(item.caution)}</small></div>`)
      .join(""),
  );
}

function isPrivateInsight(item) {
  return /RAG|私有|知识库/i.test(`${item?.title || ""} ${item?.source || ""}`);
}

function renderInsightCard(item) {
  const normalized = normalizeInsight(item);
  const confidenceText = { high: "高可信", medium: "中可信", low: "低可信" }[item.confidence] || item.confidence;
  return `
    <article class="insight-card ${normalized.isPrivate ? "private-rag" : ""}">
      <div class="insight-card-head">
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          ${normalized.file ? `<span>${escapeHtml(normalized.file)}</span>` : ""}
        </div>
        <div class="insight-tags">
          <em>${escapeHtml(item.source)}</em>
          <em>${escapeHtml(confidenceText)}</em>
        </div>
      </div>
      <p>${escapeHtml(normalized.summary)}</p>
      ${normalized.chips.length ? `<div class="insight-chips">${normalized.chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>` : ""}
    </article>
  `;
}

function renderRagHitCard(item) {
  const normalized = normalizeInsight(item);
  const confidenceText = { high: "高可信", medium: "中可信", low: "低可信" }[item.confidence] || item.confidence;
  return `
    <article class="rag-hit-card">
      <header>
        <div>
          <span>命中资料</span>
          <strong>${escapeHtml(normalized.file || item.title)}</strong>
        </div>
        <em>${escapeHtml(confidenceText)}</em>
      </header>
      <p>${escapeHtml(normalized.summary)}</p>
      ${normalized.chips.length ? `<div class="insight-chips">${normalized.chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>` : ""}
      <small>${escapeHtml(item.source)}</small>
    </article>
  `;
}

function normalizeInsight(item) {
  const raw = String(item.content || "").replace(/\s+/g, " ").trim();
  const isPrivate = isPrivateInsight(item);
  let file = "";
  let summary = raw;

  if (isPrivate) {
    const match = raw.match(/^([^：:]{2,40}\.(?:txt|md|pdf|markdown))\s*[：:]\s*(.+)$/i);
    if (match) {
      file = match[1];
      summary = match[2];
    }
  }

  const chips = extractInsightChips(summary);
  summary = shortenText(summary, isPrivate ? 180 : 120);
  return { isPrivate, file, summary, chips };
}

function extractInsightChips(text) {
  const chips = [];
  const budgetMatches = text.match(/\d+(?:\.\d+)?\s*(?:-|－|~|—)\s*\d+(?:\.\d+)?\s*元|\d+(?:\.\d+)?\s*元/g) || [];
  budgetMatches.slice(0, 4).forEach((item) => chips.push(item.replace(/\s+/g, "")));

  ["预算", "交通", "住宿", "餐饮", "门票", "高铁", "火车", "室内", "少走路"].forEach((keyword) => {
    if (text.includes(keyword) && !chips.includes(keyword)) chips.push(keyword);
  });

  return chips.slice(0, 6);
}

function shortenText(text, maxLength) {
  if (text.length <= maxLength) return text;
  const cut = text.slice(0, maxLength);
  const lastBreak = Math.max(cut.lastIndexOf("。"), cut.lastIndexOf("；"), cut.lastIndexOf("，"));
  return `${cut.slice(0, lastBreak > 70 ? lastBreak + 1 : maxLength)}...`;
}

function renderList(title, icon, items) {
  return panel(title, icon, `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
}

function panel(title, icon, content, className = "") {
  return `<section class="panel ${className}"><div class="panel-heading"><i data-lucide="${icon}"></i><h3>${title}</h3></div>${content}</section>`;
}

function metric(icon, label, value) {
  return `<div class="metric"><i data-lucide="${icon}"></i><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function setToday() {
  const input = form.querySelector('input[name="start_date"]');
  input.value = new Date().toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
