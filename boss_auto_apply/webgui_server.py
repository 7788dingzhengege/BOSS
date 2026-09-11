# -*- coding: utf-8 -*-
"""BOSS直聘自动投递 - HTML 网页版控制台（Tkinter GUI 的平替版，原 gui.py 等代码一律不动）

运行:
    E:/BOSS/.venv/Scripts/python.exe webgui_server.py
然后浏览器打开: http://127.0.0.1:8642

功能:
    /        控制台(投递设置/开始/终止/实时日志/今日计数/飞轮摘要)
    /label   人工标注页(HTML 渲染, 上千条也不卡)
    /trend   飞轮趋势
    /rules   规则库(rules.json / rule_suggestions.json)只读查看
"""
import sys
import os
import json
import time
import threading
import webbrowser
from collections import deque

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import (KEYWORDS, CITIES, MAX_DAILY_APPLIES, FILTER_CONFIG,
                    APPLIED_FILE, CITY_OPTIONS, SCALE_OPTIONS)
from applier import JobApplier

SETTINGS_FILE = "data/gui_settings.json"
PORT = 8642

DEFAULTS = {
    "keywords": ", ".join(KEYWORDS[:3]),
    "city": CITIES[0] if CITIES else "北京",
    "count": str(MAX_DAILY_APPLIES),
    "speed": "1",
    "exclude": ", ".join(FILTER_CONFIG.get("exclude_keywords", [])),
    "intern": True,
    "login": True,
    "schedule": False,
    "schedule_hour": "09",
    "schedule_minute": "00",
    "scales": ["305", "306"],
    "agent_filter": False,
    "rag_enabled": True,
}

# ===================== 全局状态 / 日志 =====================
LOG = deque(maxlen=3000)
STATE = {"running": False, "applier": None, "last_msg": "就绪", "started_at": None}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    LOG.append(line)
    return line


class TeeOut:
    """把 print 输出同时写入日志缓冲（网页实时显示）"""

    def __init__(self, real):
        self.real = real

    def write(self, s):
        if s:
            for ln in s.replace("\r", "\n").split("\n"):
                if ln.strip():
                    LOG.append(f"[{time.strftime('%H:%M:%S')}] {ln}")
        try:
            self.real.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            self.real.flush()
        except Exception:
            pass


# ===================== 业务函数（复刻 gui.py 逻辑） =====================
def get_today_count():
    if not os.path.exists(APPLIED_FILE):
        return 0
    try:
        with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        today = time.strftime("%Y-%m-%d")
        return sum(1 for j in data.get("jobs", []) if j.get("date") == today)
    except Exception:
        return 0


def reset_today_count():
    if not os.path.exists(APPLIED_FILE):
        return True
    try:
        with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        today = time.strftime("%Y-%m-%d")
        data["jobs"] = [j for j in data.get("jobs", []) if j.get("date") != today]
        with open(APPLIED_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return {**DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(cfg):
    os.makedirs(os.path.dirname(SETTINGS_FILE) or '.', exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def start_apply(cfg):
    """解析网页表单 → 构造 JobApplier → 后台线程跑（镜像 gui.py 的 start_apply/_run_apply）"""
    if STATE["running"]:
        return False, "已在运行中，请先终止"
    try:
        keywords = [k.strip() for k in str(cfg.get("keywords", "")).replace("，", ",").split(",") if k.strip()]
        if not keywords:
            keywords = KEYWORDS.copy()
        max_a = cfg.get("count", MAX_DAILY_APPLIES)
        max_a = int(max_a) if str(max_a).isdigit() else MAX_DAILY_APPLIES
        delay_map = {"1": (1, 2), "2": (3, 6), "3": (5, 10)}
        speed = str(cfg.get("speed", "1"))
        exclude = [e.strip() for e in str(cfg.get("exclude", "")).replace("，", ",").split(",") if e.strip()]
        city_name = cfg.get("city") or CITIES[0]
        scales = [s for s in cfg.get("scales", []) if s in SCALE_OPTIONS.values()]
    except Exception as e:
        return False, f"配置解析失败: {e}"

    try:
        a = JobApplier()
        a.interactive = False          # 网页版：跑完自动关浏览器，不等待回车
        a.keywords = keywords
        a.city_code = CITY_OPTIONS.get(city_name, CITY_OPTIONS[CITIES[0]])
        a.max_daily_applies = max_a
        a.delay_range = delay_map.get(speed, (1, 2))
        a.internship_only = bool(cfg.get("intern", True))
        a.exclude_keywords = exclude
        a.skip_login = bool(cfg.get("login", True))
        a.scale_codes = scales or ["305", "306"]
        a.agent_filter_enabled = bool(cfg.get("agent_filter", False))
        a.rag_enabled = bool(cfg.get("rag_enabled", True))
    except Exception as e:
        return False, f"初始化失败: {e}"

    STATE["applier"] = a
    STATE["running"] = True
    STATE["started_at"] = time.strftime("%H:%M:%S")
    STATE["last_msg"] = "运行中..."
    log("▶ 开始投递: " + ", ".join(keywords[:5]))
    threading.Thread(target=_run_apply, daemon=True).start()
    return True, "已启动"


def _run_apply():
    a = STATE["applier"]
    try:
        a.run()
        STATE["last_msg"] = f"完成！本次投递 {a.today_count} 个，今日累计 {get_today_count()} 个"
    except Exception as e:
        STATE["last_msg"] = f"错误: {e}"
        log(f"!! {e}")
    finally:
        STATE["running"] = False
        log("■ 投递进程结束")


def stop_apply():
    a = STATE["applier"]
    if a is not None:
        a.stop_requested = True
        STATE["last_msg"] = "🛑 终止信号已发送"
        log("🛑 终止信号已发送")
        return True
    return False


def flywheel_summary():
    try:
        from flywheel import metrics
        m = metrics.compute_metrics()
        total = m.get("total_labeled", 0)
        if total == 0:
            return {"total": 0, "text": "标注: 0 条 | 开始标注启动飞轮"}
        g1, g2, g3, g4 = m.get("G1", 0), m.get("G2", 0), m.get("G3", 0), m.get("G4", 0)
        oa = m.get("overall_accuracy")
        oa_pct = f"{oa*100:.0f}%" if oa else "N/A"
        pred = metrics.predict_overall_accuracy()
        pred_str = f" | 预测:{pred*100:.0f}%" if pred is not None else ""
        return {"total": total, "G1": g1, "G2": g2, "G3": g3, "G4": g4,
                "text": f"标注:{total}条 G1:{g1} G2:{g2} G3:{g3} G4:{g4} 综合:{oa_pct}{pred_str}"}
    except Exception as e:
        return {"total": 0, "text": f"加载失败: {e}"}


def pending_lists(group=None):
    from flywheel import labeler
    q = labeler.get_review_queue(group)

    def prep(items):
        out = []
        for j in items:
            out.append({
                "job_id": j.get("job_id", ""),
                "job_name": j.get("job_name", ""),
                "company": j.get("company", ""),
                "salary": j.get("salary", ""),
                "hit_keyword": j.get("hit_keyword", ""),
                "applied_at": (j.get("applied_at") or "")[:16],
            })
        return sorted(out, key=lambda x: x["applied_at"], reverse=True)

    return {"applied": prep(q["applied"]), "excluded": prep(q["excluded"])}


def do_label(job_id, label_type, note=""):
    from flywheel import labeler, metrics
    if label_type == "accepted":
        labeler.label_accepted(job_id, note)
    else:
        labeler.label_rejected(job_id, note)
    try:
        metrics.recompute_all_run_metrics()
    except Exception:
        pass
    return True


def do_batch(group, target_group=None):
    from flywheel import labeler, metrics
    q = labeler.get_review_queue(target_group)
    if group == "applied_ok":
        ids = [j["job_id"] for j in q["applied"]]
        labeler.batch_label_applied_accepted(ids)
    elif group == "excluded_reject":
        ids = [j["job_id"] for j in q["excluded"]]
        labeler.batch_label_excluded_rejected(ids)
    else:
        ids = []
    try:
        metrics.recompute_all_run_metrics()
    except Exception:
        pass
    return len(ids)


def load_rules_data():
    out = {"rules": None, "suggestions": None}
    for key, path in (("rules", "data/rules.json"), ("suggestions", "data/rule_suggestions.json")):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    out[key] = json.load(f)
            except Exception:
                pass
    return out


# ===================== HTTP 服务 =====================
def _json_body(handler):
    length = int(handler.headers.get('Content-Length', 0) or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode('utf-8'))
    except Exception:
        return {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, code=200):
        body = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/' or path == '/index.html':
            return self._send_html(PAGE_INDEX)
        if path == '/label':
            return self._send_html(PAGE_LABEL)
        if path == '/trend':
            return self._send_html(PAGE_TREND)
        if path == '/rules':
            return self._send_html(PAGE_RULES)
        if path == '/api/state':
            from flywheel import store as fw_store
            groups = fw_store.get_all_groups()
            return self._send_json({
                "running": STATE["running"],
                "started_at": STATE["started_at"],
                "last_msg": STATE["last_msg"],
                "today_count": get_today_count(),
                "flywheel": flywheel_summary(),
                "groups": groups,
                "log": list(LOG),
            })
        if path == '/api/config':
            return self._send_json({
                "cfg": load_settings(),
                "defaults": DEFAULTS,
                "city_options": CITY_OPTIONS,
                "scale_options": SCALE_OPTIONS,
                "count_options": ["20", "40", "60", "100", "130"],
                "speed_options": {"1": "快", "2": "正常", "3": "慢"},
            })
        if path == '/api/pending':
            qs = urllib.parse.parse_qs(parsed.query)
            g = (qs.get('group') or [''])[0]
            return self._send_json({"group": g, **pending_lists(g or None)})
        if path == '/api/metrics':
            try:
                from flywheel import metrics
                rounds = metrics.compute_all_runs()
            except Exception:
                rounds = []
            return self._send_json({"summary": flywheel_summary(), "rounds": rounds})
        if path == '/api/rules':
            from flywheel import store as fw_store
            return self._send_json({**load_rules_data(), "group_rules": fw_store.get_group_rules()})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = _json_body(self)

        if path == '/api/config':
            cfg = {**load_settings(), **body}
            try:
                save_settings(cfg)
                log("💾 设置已保存")
                return self._send_json({"ok": True, "msg": "设置已保存"})
            except Exception as e:
                return self._send_json({"ok": False, "msg": f"保存失败: {e}"}, 500)

        if path == '/api/start':
            ok, msg = start_apply(body)
            return self._send_json({"ok": ok, "msg": msg})

        if path == '/api/stop':
            ok = stop_apply()
            return self._send_json({"ok": ok, "msg": "终止信号已发送" if ok else "当前无运行任务"})

        if path == '/api/reset-count':
            ok = reset_today_count()
            return self._send_json({"ok": ok, "msg": "今日计数已重置" if ok else "重置失败"})

        if path == '/api/label':
            try:
                ok = do_label(body.get("job_id", ""), body.get("label_type", ""), body.get("note", ""))
                return self._send_json({"ok": ok})
            except Exception as e:
                return self._send_json({"ok": False, "msg": str(e)}, 500)

        if path == '/api/label-batch':
            try:
                n = do_batch(body.get("group", ""), body.get("target_group") or None)
                return self._send_json({"ok": True, "count": n})
            except Exception as e:
                return self._send_json({"ok": False, "msg": str(e)}, 500)

        self.send_response(404)
        self.end_headers()


# ===================== 页面模板 =====================
_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei',system-ui,sans-serif;background:#f2f4f7;color:#333;padding:20px}
.wrap{max-width:980px;margin:0 auto}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:18px 20px;margin-bottom:16px}
.card h2{font-size:15px;color:#1a73e8;margin-bottom:12px;border-left:4px solid #1a73e8;padding-left:10px}
.row{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start}
.field{flex:1;min-width:200px}
.field label{display:block;font-size:12px;color:#666;margin-bottom:4px;font-weight:600}
input[type=text],select{width:100%;padding:7px 10px;border:1px solid #cfd6dd;border-radius:7px;font-size:13px}
.checks{display:flex;flex-wrap:wrap;gap:8px 18px;padding-top:6px}
.checks label{font-size:13px;color:#333;font-weight:400;display:flex;align-items:center;gap:5px;cursor:pointer}
.btns{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
button{padding:9px 18px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;color:#fff}
.b-primary{background:#1a73e8}.b-primary:hover{background:#1557b0}
.b-success{background:#43a047}.b-danger{background:#e53935}.b-warning{background:#fb8c00}
.b-info{background:#546e7a}.b-light{background:#e0e0e0;color:#333}
button:disabled{opacity:.5;cursor:not-allowed}
.status{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:12px;flex-wrap:wrap}
.dot{width:10px;height:10px;border-radius:50%;background:#9e9e9e;display:inline-block}
.dot.run{background:#43a047;animation:blink 1.2s infinite}
@keyframes blink{50%{opacity:.35}}
.badge{background:#e8f0fe;color:#1a73e8;border-radius:20px;padding:2px 12px;font-size:12px;font-weight:700}
.badge.red{background:#fce8e6;color:#d93025}
pre.log{background:#0f172a;color:#d1e3f8;padding:12px 14px;border-radius:10px;font-size:12px;line-height:1.55;height:320px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.topbar h1{font-size:20px;color:#1a73e8}
.topbar nav a{margin-left:14px;font-size:13px;color:#1a73e8;text-decoration:none}
a{color:#1a73e8}
.lbl-row{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid #f0f2f5;font-size:13px;flex-wrap:wrap}
.lbl-row:nth-child(odd){background:#fafbfc}
.lbl-info{flex:1;min-width:260px}
.lbl-meta{color:#888;font-size:12px}
.lbl-actions{display:flex;gap:6px;align-items:center}
.lbl-actions input{width:130px;padding:4px 8px;border:1px solid #cfd6dd;border-radius:6px;font-size:12px}
.small-btn{padding:4px 12px;font-size:12px;border-radius:6px}
.b-ok{background:#43a047}.b-no{background:#e53935}
.hdr-sec{font-size:14px;font-weight:700;margin:18px 0 8px;padding:8px 12px;border-radius:8px}
.hdr-app{background:#e6f4ea;color:#1e7e34}.hdr-exc{background:#fef3e2;color:#b45309}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid #eef0f3;text-align:left}
th{background:#f8f9fb;color:#555;font-size:12px}
.bar{height:14px;border-radius:4px;background:#e8f0fe;min-width:2px}
.hint{font-size:12px;color:#888;margin-top:6px}
"""

_PAGE_HEAD = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BOSS 直聘自动投递 - 网页版</title><style>{_CSS}</style></head><body>
<div class="wrap"><div class="topbar"><h1>⚡ BOSS 直聘自动投递</h1>
<nav><a href="/">控制台</a><a href="/label">标注</a><a href="/trend">趋势</a><a href="/rules">规则库</a></nav></div>"""

PAGE_INDEX = _PAGE_HEAD + """
<div class="card">
  <div class="status">
    <span class="dot" id="dot"></span>
    <b id="runText">未运行</b>
    <span class="badge" id="todayBadge">今日已投 0</span>
    <span id="startedAt" style="color:#888;font-size:12px"></span>
    <span style="flex:1"></span>
    <span id="lastMsg" style="color:#888;font-size:12px">就绪</span>
  </div>
  <div class="row">
    <div class="field" style="flex:2"><label>搜索关键词（逗号分隔）</label><input id="kw" type="text"></div>
    <div class="field"><label>城市</label><select id="city"></select></div>
  </div>
  <div class="row" style="margin-top:12px">
    <div class="field"><label>投递数量</label><div class="checks" id="counts"></div></div>
    <div class="field"><label>操作速度</label><div class="checks" id="speeds"></div></div>
  </div>
  <div class="row" style="margin-top:12px">
    <div class="field" style="flex:2"><label>公司规模</label><div class="checks" id="scales"></div></div>
  </div>
  <div class="row" style="margin-top:12px">
    <div class="field"><label>排除关键词（逗号分隔）</label><input id="excl" type="text"></div>
  </div>
  <div class="row" style="margin-top:12px">
    <div class="field"><label>选项</label><div class="checks">
      <label><input type="checkbox" id="intern"> 只投实习</label>
      <label><input type="checkbox" id="login"> 已登录</label>
      <label><input type="checkbox" id="rag"> RAG召回</label>
      <label><input type="checkbox" id="agent"> Agent筛选</label>
    </div></div>
  </div>
  <div class="btns">
    <button class="b-primary" id="btnStart">▶ 开始投递</button>
    <button class="b-danger" id="btnStop" disabled>■ 终止</button>
    <button class="b-success" id="btnSave">💾 保存设置</button>
    <button class="b-light" id="btnReset">↩ 恢复默认</button>
    <button class="b-warning" id="btnResetCount">重置今日计数</button>
  </div>
</div>

<div class="card">
  <h2>飞轮</h2>
  <div class="status"><span id="flyText" style="font-size:13px">加载中...</span></div>
  <div class="hint">岗位分组：白名单按你输入的关键词自动切换（如「ai」「算法」各一套），排除词全局共享。已有组：<span id="flyGroups">-</span></div>
</div>

<div class="card">
  <h2>实时日志</h2>
  <pre class="log" id="logBox"></pre>
</div>

<script>
const $=id=>document.getElementById(id);
let cfg={}, defaults={}, cityOpts={}, scaleOpts={}, countOpts=[], speedOpts={};
let lastLogLen=0;

async function loadConfig(){
  const r=await fetch('/api/config');const d=await r.json();
  cfg=d.cfg;defaults=d.defaults;cityOpts=d.city_options;scaleOpts=d.scale_options;
  countOpts=d.count_options;speedOpts=d.speed_options;
  fillForm();
}
function fillForm(){
  $('kw').value=cfg.keywords||'';
  $('city').innerHTML=Object.keys(cityOpts).map(c=>`<option value="${c}">${c}</option>`).join('');
  $('city').value=cfg.city||'北京';
  $('counts').innerHTML=countOpts.map(c=>`<label><input type="radio" name="count" value="${c}"> ${c}</label>`).join('');
  document.querySelectorAll('input[name=count]').forEach(x=>x.checked=x.value==String(cfg.count||130));
  $('speeds').innerHTML=Object.entries(speedOpts).map(([v,t])=>`<label><input type="radio" name="speed" value="${v}"> ${t}</label>`).join('');
  document.querySelectorAll('input[name=speed]').forEach(x=>x.checked=x.value==String(cfg.speed||'1'));
  $('scales').innerHTML=Object.entries(scaleOpts).map(([n,c])=>`<label><input type="checkbox" value="${c}" ${(cfg.scales||[]).includes(c)?'checked':''}> ${n}</label>`).join('');
  $('excl').value=cfg.exclude||'';
  $('intern').checked=!!cfg.intern; $('login').checked=!!cfg.login;
  $('rag').checked=cfg.rag_enabled!==false; $('agent').checked=!!cfg.agent_filter;
}
function collect(){
  return {
    keywords:$('kw').value, city:$('city').value, count:document.querySelector('input[name=count]:checked').value,
    speed:document.querySelector('input[name=speed]:checked').value,
    scales:[...document.querySelectorAll('#scales input:checked')].map(x=>x.value),
    exclude:$('excl').value, intern:$('intern').checked, login:$('login').checked,
    rag_enabled:$('rag').checked, agent_filter:$('agent').checked,
  };
}
async function poll(){
  try{
    const r=await fetch('/api/state');const s=await r.json();
    $('dot').className='dot'+(s.running?' run':'');
    $('runText').textContent=s.running?'运行中':'未运行';
    $('todayBadge').textContent='今日已投 '+s.today_count;
    $('startedAt').textContent=s.started_at?'启动于 '+s.started_at:'';
    $('lastMsg').textContent=s.last_msg||'';
    $('flyText').textContent=(s.flywheel&&s.flywheel.text)||'';
    const gs=s.groups||{};
    const gArr=Object.keys(gs).filter(k=>k).map(k=>`${k}(${gs[k]})`);
    $('flyGroups').textContent=gArr.length?gArr.join('、'):'暂无（投递后自动创建）';
    $('btnStart').disabled=s.running; $('btnStop').disabled=!s.running;
    const lb=$('logBox'); const atBottom=lb.scrollHeight-lb.scrollTop-lb.clientHeight<40;
    if(s.log.length>lastLogLen){
      lb.textContent=s.log.join('\n'); lastLogLen=s.log.length;
      if(atBottom) lb.scrollTop=lb.scrollHeight;
    }
  }catch(e){}
}
$('btnStart').onclick=async()=>{
  const c=collect();
  if(!confirm('确认开始投递？\n关键词: '+c.keywords+'\n城市: '+c.city+'\n数量: '+c.count))return;
  const r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});
  const d=await r.json(); if(!d.ok) alert(d.msg);
};
$('btnStop').onclick=async()=>{await fetch('/api/stop',{method:'POST'});};
$('btnSave').onclick=async()=>{
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collect())});
  const d=await r.json(); alert(d.msg);
};
$('btnReset').onclick=async()=>{
  if(!confirm('恢复默认设置？'))return;
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(defaults)});
  const d=await r.json(); await loadConfig(); alert(d.msg);
};
$('btnResetCount').onclick=async()=>{await fetch('/api/reset-count',{method:'POST'});};
loadConfig(); poll(); setInterval(poll,1500);
</script></body></html>"""

PAGE_LABEL = _PAGE_HEAD + """
<div class="card">
  <div class="status">
    <span id="lblSummary" style="font-size:13px">加载中...</span>
    <span style="flex:1"></span>
    <select id="grpSel" style="width:160px"><option value="">全部岗位</option></select>
    <button class="b-success" id="batchOk">全部投了的标为👍对</button>
    <button class="b-danger" id="batchRej">全部过滤的标为👎该排</button>
    <button class="b-info" id="lblRefresh">刷新</button>
  </div>
  <div id="lblBody"></div>
</div>
<script>
const $=id=>document.getElementById(id);
let curGroup='';
async function loadGroups(){
  const r=await fetch('/api/state');const s=await r.json();
  const gs=s.groups||{};
  $('grpSel').innerHTML='<option value="">全部岗位</option>'+Object.keys(gs).filter(k=>k).map(k=>`<option value="${k}">${k} (${gs[k]})</option>`).join('');
  $('grpSel').value=curGroup;
}
$('grpSel').onchange=e=>{curGroup=e.target.value;render();};
function esc(s){return (s||'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
async function render(){
  const url='/api/pending'+(curGroup?'?group='+encodeURIComponent(curGroup):'');
  const r=await fetch(url);const d=await r.json();
  const a=d.applied,e=d.excluded;
  $('lblSummary').textContent=`待标注: ${a.length+e.length} 条 | 已投待标: ${a.length} | 过滤待标: ${e.length}`;
  let html='';
  if(a.length) html+=`<div class="hdr-sec hdr-app">▼ 已投递的 (${a.length}条待标) — 默认多半投对了</div>`;
  for(const j of a) html+=rowHtml(j,'applied');
  if(e.length) html+=`<div class="hdr-sec hdr-exc">▼ 被过滤的 (${e.length}条待标) — 漏投检查: 该排吗?</div>`;
  for(const j of e) html+=rowHtml(j,'excluded');
  $('lblBody').innerHTML=html||'<div class="hint" style="padding:30px;text-align:center">✅ 没有待标注的职位</div>';
}
function rowHtml(j,st){
  const hit=j.hit_keyword?`<span class="lbl-meta">命中'${esc(j.hit_keyword)}'被排除</span>`:'';
  const ok=st==='applied'?'对':'该投', no=st==='applied'?'错投':'该排';
  return `<div class="lbl-row">
    <div class="lbl-info"><b>${esc(j.job_name)}</b> | ${esc(j.company)} | <span class="lbl-meta">${esc(j.salary)} ${hit} ${esc(j.applied_at)}</span></div>
    <div class="lbl-actions">
      <input data-id="${esc(j.job_id)}" placeholder="备注(可选)">
      <button class="small-btn b-ok" data-act="accepted" data-id="${esc(j.job_id)}">👍 ${ok}</button>
      <button class="small-btn b-no" data-act="rejected" data-id="${esc(j.job_id)}">👎 ${no}</button>
    </div></div>`;
}
$('lblBody').addEventListener('click',async ev=>{
  const btn=ev.target.closest('button[data-act]'); if(!btn)return;
  const id=btn.dataset.id, act=btn.dataset.act;
  const note=btn.parentElement.querySelector('input').value||'';
  await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:id,label_type:act,note})});
  render();
});
async function batch(group){await fetch('/api/label-batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group,target_group:curGroup||null})});render();}
$('batchOk').onclick=()=>{if(confirm((curGroup?`对「${curGroup}」组`: '对全部')+'已投递职位标为投对?'))batch('applied_ok');};
$('batchRej').onclick=()=>{if(confirm((curGroup?`对「${curGroup}」组`: '对全部')+'被过滤职位标为拦对?'))batch('excluded_reject');};
$('lblRefresh').onclick=render;
loadGroups(); render();
</script></body></html>"""

PAGE_TREND = _PAGE_HEAD + """
<div class="card">
  <h2>飞轮指标 / 趋势</h2>
  <div class="status"><span id="tSummary">加载中...</span></div>
  <table><thead><tr><th>轮次</th><th>综合准确率</th><th>G1投对</th><th>G2错投</th><th>G3漏投</th><th>G4拦对</th><th>准确率条</th></tr></thead>
  <tbody id="tBody"></tbody></table>
  <div class="hint" id="tHealth"></div>
</div>
<script>
async function render(){
  const r=await fetch('/api/metrics');const d=await r.json();
  $('tSummary').textContent=(d.summary&&d.summary.text)||'';
  const rows=d.rounds||[]; let html='';
  for(const x of rows){
    const oa=x.overall_accuracy; const pct=oa!=null?(oa*100).toFixed(0):'N/A';
    const w=oa!=null?Math.max(2,Math.round(oa*100)):0;
    html+=`<tr><td>${x.run_id||'-'}</td><td><b>${pct}%</b></td><td>${x.G1??'-'}</td><td>${x.G2??'-'}</td><td>${x.G3??'-'}</td><td>${x.G4??'-'}</td>
      <td><div class="bar" style="width:${w}%;background:${oa>=0.6?'#43a047':'#e53935'}"></div></td></tr>`;
  }
  $('tBody').innerHTML=html||'<tr><td colspan="7" style="text-align:center;color:#888">暂无轮次数据</td></tr>';
}
render();
</script></body></html>"""

PAGE_RULES = _PAGE_HEAD + """
<div class="card">
  <h2>规则库（只读）</h2>
  <div id="rulesBody">加载中...</div>
</div>
<script>
function esc(s){return (s||'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
async function render(){
  const r=await fetch('/api/rules');const d=await r.json();
  let html='';
  if(d.rules){
    const R=d.rules;
    html+=`<h3 style="margin:10px 0 6px">rules.json v${R.version||'?'} (更新于 ${R.updated_at||'-'})</h3>`;
    html+=`<table><tr><th>排除词(${(R.exclude_keywords||[]).length})</th><th>白名单(${(R.include_keywords||[]).length})</th></tr>
      <tr><td style="white-space:pre-wrap">${(R.exclude_keywords||[]).join('、')||'-'}</td>
      <td style="white-space:pre-wrap">${(R.include_keywords||[]).join('、')||'-'}</td></tr></table>`;
  }
  if(d.group_rules){
    const gs=d.group_rules; const gKeys=Object.keys(gs).filter(k=>k && (gs[k].include_keywords.length||gs[k].exclude_keywords.length));
    if(gKeys.length){
      html+=`<h3 style="margin:16px 0 6px">按岗位分组规则（白名单按关键词自动切换）</h3>`;
      html+=`<table><tr><th>岗位组</th><th>该组白名单</th><th>该组排除词</th></tr>`;
      for(const g of gKeys){
        html+=`<tr><td><b>${esc(g)}</b></td><td style="white-space:pre-wrap">${esc((gs[g].include_keywords||[]).join('、')||'-')}</td><td style="white-space:pre-wrap">${esc((gs[g].exclude_keywords||[]).join('、')||'-')}</td></tr>`;
      }
      html+=`</table>`;
    }
  }
  if(d.suggestions){
    const S=d.suggestions;
    html+=`<h3 style="margin:16px 0 6px">rule_suggestions.json</h3><pre style="font-size:12px;background:#f8f9fb;padding:10px;border-radius:8px;white-space:pre-wrap">${JSON.stringify(S,null,2)}</pre>`;
  }
  $('rulesBody').innerHTML=html||'无规则文件';
}
render();
</script></body></html>"""


def main():
    sys.stdout = TeeOut(sys.stdout)
    sys.stderr = TeeOut(sys.stderr)
    log(f"✅ 网页版控制台已启动: http://127.0.0.1:{PORT}  (原 Tkinter GUI 未受影响)")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(f"http://127.0.0.1:{PORT}")), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
