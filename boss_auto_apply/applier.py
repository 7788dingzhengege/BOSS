# 核心投递逻辑模块

import sys
import os
import json
import random
import re
import hashlib
import time
import logging
import urllib.parse
from datetime import datetime, timedelta

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from config import (
    KEYWORDS, CITIES, MAX_DAILY_APPLIES,
    DELAY_RANGE, APPLIED_FILE, FILTER_CONFIG, TEST_LIMIT, SCHEDULE_CONFIG,
    CITY_OPTIONS, SCALE_OPTIONS,
    AGENT_FILTER_CONFIG, JOB_SEEKER_PROFILE,
    RESUME_CONFIG, RAG_CONFIG, BOSS_LIMIT_CONFIG,
    INCLUDE_KEYWORDS,
)
from browser import BrowserManager
from agent_filter import JobFilterAgent
from resume.parser import ResumeParser
from resume.matcher import ResumeMatcher
from resume.optimizer import ResumeOptimizer
from resume.generator import ResumeGenerator
from flywheel import store as flywheel_store
from flywheel import decision as flywheel_decision
from flywheel import metrics as flywheel_metrics

logger = logging.getLogger("boss_applier")

# ====== JS 脚本常量（从方法内抽离，便于维护）======

# 获取职位列表的 JS（无插值）
_JS_GET_JOB_LIST = r'''
    var jobs = [];
    var selectors = [
        '[class*="job-card-box"]',
        '.job-card-wrapper', '.job-card-left',
        '[class*="job-card-body"]',
        'li[class*="job-card"]',
    ];

    // 清理职位名：剥离尾部混入的薪资/周期/学历等污染信息
    function cleanJobName(raw) {
        if (!raw) return '';
        var name = raw.trim();
        // 剥离尾部编号："(MJ003755)" "(J16288)"
        name = name.replace(/\s*[（(]\s*[A-Za-z]{1,4}\d{3,}\s*[)）]\s*$/g, '');
        // 剥离尾部"面议"
        name = name.replace(/\s*面议\s*$/g, '');
        // 剥离尾部薪资：如 "-200元/天" "5天/周" "6个月" "本科" 等
        // 匹配模式：从第一个 "-数字" 或 "数字元" 或 "天/周" 开始截断
        var cutIdx = name.search(/[\-]\d|\d+元|\d+天\/周|\d+个月|本科|硕士|博士|大专|学历不限/);
        if (cutIdx > 3) {
            name = name.substring(0, cutIdx).trim();
        }
        // 再次清理可能残留的尾部标点
        name = name.replace(/[\s\-·]+$/g, '');
        return name;
    }

    for (var si = 0; si < selectors.length; si++) {
        var cards = document.querySelectorAll(selectors[si]);
        if (cards.length > 0) {
            for (var i = 0; i < cards.length; i++) {
                var card = cards[i];

                // 职位名：精准定位 .job-name / .job-title，不取父容器
                var nameEl = card.querySelector('.job-name span') ||
                    card.querySelector('.job-name') ||
                    card.querySelector('.job-title') ||
                    card.querySelector('[class*="job-title"]');

                // 如果精准选择器失败，用宽松选择器但只取叶子节点（无子元素）
                if (!nameEl) {
                    var nameCandidates = card.querySelectorAll(
                        '.job-name, .job-title, [class*="job-name"]'
                    );
                    for (var n = 0; n < nameCandidates.length; n++) {
                        // 只取没有子元素的节点（叶子），避免取到父容器
                        if (nameCandidates[n].children.length === 0) {
                            var t = nameCandidates[n].textContent.trim();
                            if (t.length >= 2 && t.length <= 40) {
                                nameEl = nameCandidates[n];
                                break;
                            }
                        }
                    }
                }

                var rawName = nameEl ? nameEl.textContent.trim() : '';
                var cleanName = cleanJobName(rawName);

                // 公司名称：精准定位
                var companyEl = card.querySelector('.company-name a') ||
                    card.querySelector('.company-name') ||
                    card.querySelector('[class*="company-name"] a') ||
                    card.querySelector('[class*="company-name"]');
                var companyText = '';
                if (companyEl) {
                    companyText = companyEl.textContent.trim();
                    // 去除可能的地区前缀（如 "北京·朝阳·望京"）
                    if (companyText.length > 30) {
                        companyText = companyText.substring(0, 30);
                    }
                }

                // 薪资：精准定位
                var salaryEl = card.querySelector('.salary') ||
                    card.querySelector('[class*="salary"]');
                var salaryText = '';
                if (salaryEl) {
                    // 只取薪资元素自身的文本，不包含子元素
                    salaryText = salaryEl.childNodes.length > 0
                        ? Array.from(salaryEl.childNodes)
                            .map(function(n) { return n.textContent ? n.textContent.trim() : ''; })
                            .join('')
                        : salaryEl.textContent.trim();
                }

                jobs.push({
                    name: cleanName,
                    company: companyText,
                    sizeText: '',
                    salary: salaryText,
                    jid: card.getAttribute('data-jid') ||
                        card.getAttribute('data-id') ||
                        card.getAttribute('data-pid') || '',
                    fullText: card.innerText.substring(0, 300)
                });
            }
            return {selector: selectors[si], count: cards.length, jobs: jobs};
        }
    }
    return {selector: null, count: 0, jobs: []};
'''

# 调试：打印页面上关键元素信息
_JS_DEBUG_ELEMENTS = r'''
    var result = [];
    document.querySelectorAll('[class*="job"]').forEach(function(el) {
        result.push({
            tag: el.tagName,
            class: el.className.substring(0, 60),
            text: el.textContent.substring(0, 50),
            id: el.id,
            dataJid: el.getAttribute('data-jid') || el.getAttribute('data-id')
        });
    });
    return JSON.stringify(result.slice(0, 15), null, 0);
'''


class JobApplier:
    """职位投递器"""

    def __init__(self):
        self.browser = BrowserManager()
        self.applied_jobs = []
        self._applied_ids = set()  # 快速查找已投职位ID
        self.today_count = 0
        self.skip_login = False
        self.interactive = True  # CLI 模式等待输入；GUI 模式设为 False
        # 从GUI/CLI传入的配置（默认值使用config.py中的设置）
        self.keywords = KEYWORDS.copy()
        self.max_daily_applies = MAX_DAILY_APPLIES
        self.test_limit = TEST_LIMIT
        self.boss_limit_config = BOSS_LIMIT_CONFIG.copy()
        self.delay_range = self.boss_limit_config.get("delay_range", DELAY_RANGE)
        self.schedule_config = SCHEDULE_CONFIG.copy()
        self.exclude_keywords = list(FILTER_CONFIG.get("exclude_keywords", []))
        self.include_keywords = list(INCLUDE_KEYWORDS)  # 白名单（必须命中其一）
        self.internship_only = FILTER_CONFIG.get("internship_only", True)
        self.city_code = "101010100"  # 默认北京
        self.scale_codes = ["305", "306"]  # 默认1000-10000人 + 10000人以上
        # Agent 智能筛选
        self.agent_filter_enabled = AGENT_FILTER_CONFIG.get("enabled", False)
        self.agent_filter_config = AGENT_FILTER_CONFIG.copy()
        self.job_seeker_profile = JOB_SEEKER_PROFILE.copy()
        self._agent = None  # 延迟初始化
        # 简历智能匹配与生成
        self.resume_enabled = RESUME_CONFIG.get("enabled", False)
        self.resume_config = RESUME_CONFIG.copy()
        self._resume_parser = None
        self._resume_matcher = None
        self._resume_optimizer = None
        self._resume_generator = None
        self._resume_text = None  # 解析后的简历文本（启动时加载）
        self._resume_generated_count = 0
        self._resume_match_list = []  # 简历匹配记录
        # 飞轮: 本次运行ID(投递时写入 labels.json)
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        # RAG 召回 (n-gram 相似度 + 飞轮历史投票)
        self.rag_config = RAG_CONFIG.copy()
        self.rag_enabled = self.rag_config.get("enabled", False)
        # 终止标志: GUI 点"终止"时设为 True, run() 循环检查后退出
        self.stop_requested = False
        # BOSS限制处理
        self.boss_limit_reached = False  # 运行时标记是否撞到150限制
        self._chat_attempt_count = 0     # 沟通尝试次数（含失败）
        self._load_applied()

    # ---------- 数据持久化 ----------

    def _load_applied(self):
        if os.path.exists(APPLIED_FILE):
            with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.applied_jobs = data.get("jobs", [])
                self._applied_ids = {job["id"] for job in self.applied_jobs if job.get("id")}
                today = datetime.now().strftime("%Y-%m-%d")
                self.today_count = sum(
                    1 for job in self.applied_jobs
                    if job.get("date") == today
                )
        logger.info("已加载 %d 条投递记录，今日已投 %d 次", len(self.applied_jobs), self.today_count)

    def _save_applied(self, job_info):
        """原子写入：先写临时文件，再 os.replace 覆盖，避免写入中断损坏数据"""
        self.applied_jobs.append(job_info)
        self._applied_ids.add(job_info["id"])
        os.makedirs(os.path.dirname(APPLIED_FILE) or '.', exist_ok=True)
        tmp_path = APPLIED_FILE + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({"jobs": self.applied_jobs}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, APPLIED_FILE)

    def _is_applied(self, job_id):
        return job_id in self._applied_ids

    # ---------- 筛选逻辑 ----------

    def _check_exclude(self, text):
        """检查是否包含排除关键词（子串匹配，用于职位名/公司名快速过滤）"""
        if not text:
            return False
        text_lower = text.lower()
        for kw in self.exclude_keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                return True
        return False

    def _check_exclude_detail(self, text):
        """
        检查排除词并返回命中的词
        :return: (是否命中, 命中的词)
        """
        if not text:
            return False, ""
        text_lower = text.lower()
        for kw in self.exclude_keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                return True, kw
        return False, ""

    # ---------- 页面操作 ----------

    def _build_search_url(self, keyword, page=1):
        """构建带筛选参数的搜索URL（使用GUI传入的城市代码和规模代码）"""
        params = {"query": keyword}

        if self.city_code:
            params["city"] = self.city_code

        if self.internship_only:
            params["jobType"] = "1902"

        if self.scale_codes:
            params["scale"] = ",".join(self.scale_codes)

        if FILTER_CONFIG.get("sort_by") == "latest":
            params["ka"] = "sort-time"

        if page > 1:
            params["page"] = str(page)

        query_str = urllib.parse.urlencode(params)
        return f"https://www.zhipin.com/web/geek/jobs?{query_str}"

    def search_job(self, keyword, page=1):
        """搜索职位（URL自带筛选参数：城市代码+实习+规模+排序）"""
        page_driver = self.browser.driver
        url = self._build_search_url(keyword, page)
        city_name = [name for name, code in CITY_OPTIONS.items() if code == self.city_code]
        scale_names = [name for name, code in SCALE_OPTIONS.items() if code in self.scale_codes]
        logger.info("URL: %s", url)
        self._drain_listen()  # 清空监听缓冲，避免旧 joblist（如首页推荐）污染本次搜索
        page_driver.get(url)
        # 等待页面加载：先等1.5秒，再额外等页面稳定
        time.sleep(0.8)
        # 简单等待页面内容加载（确保职位列表出现）
        try:
            page_driver.run_js('''
                // 尝试等待职位卡片出现，最多等2秒
                return new Promise((resolve) => {
                    let count = 0;
                    const check = () => {
                        const cards = document.querySelectorAll('[class*="job-card"], .job-card-wrapper');
                        if (cards.length > 0 || count >= 10) {
                            resolve(cards.length);
                        } else {
                            count++;
                            setTimeout(check, 200);
                        }
                    };
                    check();
                });
            ''')
        except Exception:
            pass
        if page > 1:
            logger.info("关键词: %s, 第%d页, 城市: %s, 规模: %s",
                        keyword, page,
                        city_name[0] if city_name else '全国',
                        ', '.join(scale_names) if scale_names else '不限')
        else:
            logger.info("关键词: %s, 城市: %s, 规模: %s",
                        keyword,
                        city_name[0] if city_name else '全国',
                        ', '.join(scale_names) if scale_names else '不限')

    def apply_filters(self):
        """URL已自带所有筛选参数（城市/实习/规模/排序），无需额外操作"""
        page = self.browser.driver
        time.sleep(0.3)
        scale_names = [name for name, code in SCALE_OPTIONS.items() if code in self.scale_codes]
        city_name = [name for name, code in CITY_OPTIONS.items() if code == self.city_code]
        logger.info("URL已带: %s+实习+%s+最新排序",
                    city_name[0] if city_name else '全国',
                    ', '.join(scale_names) if scale_names else '不限')

    def _debug_page_elements(self, page):
        """调试：打印页面上关键元素信息"""
        try:
            job_els = page.run_js(_JS_DEBUG_ELEMENTS)
            logger.debug("页面job元素:\n%s", job_els)
        except Exception:
            logger.exception("调试打印异常")

    def _drain_listen(self):
        """清空监听缓冲（非阻塞），避免首页推荐等旧 joblist 污染当前搜索"""
        try:
            self.browser.driver.listen.clear()
        except Exception:
            pass

    def _parse_joblist_response(self, resp):
        """解析 BOSS 职位列表接口返回的 JSON，映射成本项目所需的岗位字典"""
        try:
            body = resp.response.body
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8", errors="ignore")
            if isinstance(body, str):
                body = json.loads(body)
            if not isinstance(body, dict):
                return []
            job_list = (body.get("zpData") or {}).get("jobList") or []
            if not job_list:
                return []
            jobs = []
            for item in job_list:
                # 优先用 BOSS 稳定 ID（securityId/jobId/encryptId），没有再用 公司|职位|薪资 哈希兜底
                jid = (item.get("securityId") or item.get("jobId")
                       or item.get("encryptId") or "").strip()
                if not jid:
                    base = "{}|{}|{}".format(
                        item.get("brandName", ""), item.get("jobName", ""),
                        item.get("salaryDesc", ""))
                    jid = "h_" + hashlib.md5(base.encode("utf-8")).hexdigest()[:12]
                name = (item.get("jobName") or "").strip()
                if not name:
                    continue
                jobs.append({
                    "id": jid,
                    "name": name,
                    "company": (item.get("brandName") or item.get("companyName")
                            or item.get("brandCom") or item.get("brand")
                            or item.get("company") or "未知公司").strip(),
                    "salary": (item.get("salaryDesc") or "").strip(),
                    "skills": item.get("skills") or [],
                    "experience": (item.get("jobExperience") or "").strip(),
                    "degree": (item.get("jobDegree") or "").strip(),
                    "industry": (item.get("brandIndustry") or "").strip(),
                    "welfare": item.get("welfareList") or [],
                    "element": None,
                })
            return jobs
        except Exception:
            logger.exception("解析 joblist JSON 异常")
            return []

    def get_job_list(self):
        """获取当前页面的职位列表（优先用接口监听拿 JSON，回退 JS/DOM 解析）"""
        page = self.browser.driver
        jobs = []

        # 方式0：接口监听——直接拦截 BOSS 职位列表接口，拿结构化 JSON（最稳，抗改版）
        # 公司名(brandName)/薪资(salaryDesc) 均为明文，无需详情页 DOM、无需解字体加密
        try:
            def _find_joblist():
                ress = getattr(page.listen, "ress", None) or []
                matched = None
                for r in ress:
                    try:
                        u = r.url or ""
                    except Exception:
                        u = ""
                    if "joblist" in u:           # 只认职位列表接口（文章同款）
                        matched = r              # 取最后一个（最新一页）响应
                return matched

            matched = _find_joblist()
            if matched is None:
                # 非阻塞没拿到，阻塞等最多 4s（带 filter，超时返回 None，不会永久卡死）
                try:
                    matched = page.listen.wait(filter="joblist", timeout=4)
                except Exception:
                    matched = None
            if matched is not None:
                parsed = self._parse_joblist_response(matched)
                if parsed:
                    logger.info("接口监听提取成功: 数量=%d", len(parsed))
                    return parsed
                logger.info("接口监听命中但解析为空，回退 DOM/JS")
        except Exception:
            logger.exception("接口监听提取异常，回退 DOM/JS")

        # 方式1：JS直接从页面提取职位数据
        try:
            raw_jobs = page.run_js(_JS_GET_JOB_LIST)

            if raw_jobs and raw_jobs.get("count", 0) > 0:
                logger.info("JS提取成功: 选择器=%s, 数量=%d", raw_jobs['selector'], raw_jobs['count'])
                for j in raw_jobs["jobs"]:
                    if j.get("name"):
                        jid_raw = j.get("jid") or ""
                        if jid_raw:
                            job_id = jid_raw
                        else:
                            # 无稳定 data-jid 时，用 (公司|职位|薪资) 哈希生成稳定 id，
                            # 避免 "公司_职位名" 同名不同岗撞车、或同岗异写误判已投
                            base = "{}|{}|{}".format(
                                j.get("company", ""), j["name"], j.get("salary", ""))
                            job_id = "h_" + hashlib.md5(base.encode("utf-8")).hexdigest()[:12]
                        jobs.append({
                            "id": job_id,
                            "name": j["name"],
                            "company": j.get("company") or "未知公司",
                            "salary": j.get("salary", ""),
                            "element": None,
                        })
                return jobs

        except Exception:
            logger.exception("JS提取异常")

        # 方式2：DrissionPage DOM选择器（备用）
        logger.info("JS未找到，尝试DOM选择器...")
        try:
            cards = None
            selectors = [
                "css:.job-card-wrapper",
                "css:.job-card-left",
                "css:[class*='job-card-box']",
                "css:[class*='job-card-body']",
                "css:li[class*='job-card']",
                "css:[class*='search-job-result'] li",
                "xpath://div[contains(@class,'job-card')]",
            ]
            for sel in selectors:
                try:
                    cards = page.eles(sel)
                    if cards:
                        logger.info("DOM选择器 '%s' 找到 %d 个", sel, len(cards))
                        break
                except Exception:
                    continue

            if cards:
                for card in cards:
                    try:
                        info = self._parse_job_card(card)
                        if info:
                            jobs.append(info)
                    except Exception:
                        continue
        except Exception:
            logger.exception("DOM提取异常")

        if not jobs:
            logger.info("未找到任何职位卡片，打印页面元素信息...")
            self._debug_page_elements(page)

        return jobs

    def _parse_job_card(self, card):
        """解析单个职位卡片，返回字典或None"""
        job_name_el = (
            card.ele("css:.job-name", timeout=0.3) or
            card.ele("css:.job-title", timeout=0.3) or
            card.ele("css:[class*='job-name']", timeout=0.3) or
            card.ele("css:span[class*='name']", timeout=0.3) or
            card.ele("tag:p", timeout=0.3)
        )
        if not job_name_el or not job_name_el.text.strip():
            return None
        job_name = job_name_el.text.strip()

        company_el = (
            card.ele("css:.company-name a", timeout=0.3) or
            card.ele("css:[class*='company-name']", timeout=0.3) or
            card.ele("css:[class*='company']", timeout=0.3) or
            card.ele("css:[class*='company-tag']", timeout=0.3)
        )
        company = company_el.text.strip() if company_el else ""

        salary_el = (
            card.ele("css:.salary", timeout=0.3) or
            card.ele("css:[class*='salary']", timeout=0.3) or
            card.ele("css:span[class*='red']", timeout=0.3)
        )
        salary = salary_el.text.strip() if salary_el else ""

        job_id = (
            card.attr("data-jid") or
            card.attr("data-id") or
            card.attr("data-pid") or
            f"{company}_{job_name}"
        )

        return {
            "id": job_id,
            "name": job_name,
            "company": company,
            "salary": salary,
            "element": card,
        }

    def _check_salary(self, salary_text, salary_range):
        """
        检查薪资是否符合范围，返回 (是否达标, 原因)
        支持：15-25K、1.5-3万、150-200元/天、20-40元/小时、8000-12000元/月
        """
        if not salary_text:
            return True, ""

        # 面议处理
        if "面议" in salary_text:
            if FILTER_CONFIG.get("allow_salary_negotiable", True):
                return True, ""
            return False, "薪资面议"

        # 清理 "·14薪" "·13薪" 等后缀干扰
        cleaned = re.sub(r'[·\-]\s*\d+\s*薪', '', salary_text)

        # 识别单位（按优先级，万 > K > 元/天 > 元/小时 > 元/月）
        text = cleaned.strip()
        unit = "month"  # 默认按月薪
        multiplier = 1.0
        if '万' in text:
            unit = "month"
            multiplier = 10000
        elif 'K' in text or 'k' in text:
            unit = "month"
            multiplier = 1000
        elif '元/天' in text or '元/日' in text or '/天' in text:
            unit = "day"
        elif '元/小时' in text or '元/时' in text or '/小时' in text or '/时' in text:
            unit = "hour"
        elif '元/月' in text or '/月' in text:
            unit = "month"
        elif '元' in text:
            unit = "month"  # 仅"元"默认按月薪

        # 提取数值（支持小数），取前两个作为范围
        nums = re.findall(r'(\d+(?:\.\d+)?)', text)
        if len(nums) < 2:
            return True, ""  # 解析不出范围，不过滤（避免误杀）

        try:
            low = float(nums[0])
            high = float(nums[1])
        except ValueError:
            return True, ""

        if low > high:  # 容错：顺序颠倒
            low, high = high, low

        # 换算到月薪
        if unit == "month":
            monthly_low = low * multiplier
            monthly_high = high * multiplier
        elif unit == "day":
            # 日薪 × 21.75（月平均工作日）
            monthly_low = low * 21.75
            monthly_high = high * 21.75
        elif unit == "hour":
            # 时薪 × 8小时 × 21.75天
            monthly_low = low * 8 * 21.75
            monthly_high = high * 8 * 21.75
        else:
            monthly_low = low
            monthly_high = high

        min_expect, max_expect = salary_range
        logger.info("[薪资] 原文=%s 单位=%s 换算月薪=%d-%d 期望=%d-%d",
                    salary_text, unit, int(monthly_low), int(monthly_high), min_expect, max_expect)
        # 有交集即通过
        if monthly_high < min_expect or monthly_low > max_expect:
            return False, f"薪资{text}(月薪{int(monthly_low)}-{int(monthly_high)})不在{min_expect}-{max_expect}范围"
        return True, ""

    def _get_agent(self):
        """延迟初始化 Agent（仅在首次需要时创建，避免未配置 API Key 时启动失败）"""
        if self._agent is None:
            self._agent = JobFilterAgent(self.agent_filter_config, self.job_seeker_profile)
        return self._agent

    def _load_resume(self):
        """启动时加载并解析简历 PDF"""
        if not self.resume_enabled:
            return

        pdf_path = self.resume_config.get("pdf_path", "")
        if not pdf_path or not os.path.exists(pdf_path):
            logger.warning("[简历] PDF文件不存在: %s，简历功能禁用", pdf_path)
            self.resume_enabled = False
            return

        self._resume_parser = ResumeParser()
        result = self._resume_parser.parse(pdf_path)
        if result:
            self._resume_text = result["raw_text"]
            logger.info("[简历] 加载成功: %d字符, 提取技能: %s",
                        result["char_count"], result["skills"][:10])
            self._resume_matcher = ResumeMatcher(self.agent_filter_config)
            self._resume_optimizer = ResumeOptimizer(self.agent_filter_config)
            self._resume_generator = ResumeGenerator()
        else:
            logger.error("[简历] 解析失败，简历功能禁用")
            self.resume_enabled = False

    def _do_resume_match(self, job, jd_text):
        """简历-JD匹配分析 + 可选生成定制简历"""
        if not self._resume_text:
            return

        logger.info("      [简历匹配] 分析中...")
        match_result = self._resume_matcher.match(self._resume_text, jd_text, job)

        if not match_result:
            logger.info("      [简历匹配] 分析失败")
            return

        score = match_result.get("overall_score", 0)
        matched_skills = match_result.get("skill_match", {}).get("matched", [])
        missing_skills = match_result.get("skill_match", {}).get("missing", [])

        logger.info("      [简历匹配] 总分=%d 匹配技能=%s 缺失技能=%s",
                    score, matched_skills[:5], missing_skills[:5])

        self._resume_match_list.append({
            "name": job["name"],
            "company": job.get("company", ""),
            "score": score,
            "matched": matched_skills,
            "missing": missing_skills,
        })

        # 匹配度高于阈值时生成定制简历
        threshold = self.resume_config.get("match_threshold", 60)
        max_generate = self.resume_config.get("max_generate_per_run", 5)

        if score >= threshold and self._resume_generated_count < max_generate:
            if self.resume_config.get("auto_generate", False):
                logger.info("      [简历] 匹配度%d>=%d，生成定制简历...", score, threshold)
                self._generate_custom_resume(job, jd_text, match_result)
            else:
                logger.info("      [简历] 匹配度%d>=%d（未开启自动生成，跳过）", score, threshold)

    def _generate_custom_resume(self, job, jd_text, match_result):
        """生成定制简历"""
        template_path = self.resume_config.get("template_path", "")
        output_dir = self.resume_config.get("output_dir", "data/custom_resumes")

        if not template_path or not os.path.exists(template_path):
            logger.warning("      [简历] DOCX模板不存在: %s，跳过生成", template_path)
            return

        # 1. 生成优化建议
        suggestions = self._resume_optimizer.optimize(
            self._resume_text, jd_text, match_result
        )

        if not suggestions:
            logger.warning("      [简历] 优化建议生成失败")
            return

        # 2. 生成定制简历
        pdf_path = self._resume_generator.generate(
            template_path, suggestions, output_dir, job
        )

        if pdf_path:
            self._resume_generated_count += 1
            logger.info("      [简历] 定制简历已生成: %s", pdf_path)
        else:
            logger.warning("      [简历] 定制简历生成失败")

    # ---------- 详情页操作 ----------

    def _open_job_detail(self, job_name):
        """点击卡片进入详情页（不点沟通按钮）"""
        page = self.browser.driver

        # 先清理可能残留的「已向BOSS发送消息」弹窗：只点「留在此页」，绝不点「继续沟通」
        try:
            page.run_js('''
                var bs = document.querySelectorAll('button, [role="button"], a, span');
                for (var i = 0; i < bs.length; i++) {
                    var t = bs[i].textContent.trim();
                    if (t === '留在此页' || t === '留在此頁') { bs[i].click(); break; }
                }
            ''')
        except Exception:
            pass

        try:
            safe_name = job_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")

            js = r'''
                var targetName = '__TARGET_NAME__';
                var cardSelectors = [
                    '[class*="job-card-box"]',
                    '.job-card-wrapper', '.job-card-left',
                    '[class*="job-card-body"]', 'li[class*="job-card"]'
                ];

                // 清理页面上的职位名（与提取逻辑一致）
                function cleanName(raw) {
                    if (!raw) return '';
                    var name = raw.trim();
                    name = name.replace(/\s*[（(]\s*[A-Za-z]{1,4}\d{3,}\s*[)）]\s*$/g, '');
                    name = name.replace(/\s*面议\s*$/g, '');
                    var cutIdx = name.search(/[\-]\d|\d+元|\d+天\/周|\d+个月|本科|硕士|博士|大专|学历不限/);
                    if (cutIdx > 3) name = name.substring(0, cutIdx).trim();
                    name = name.replace(/[\s\-·]+$/g, '');
                    return name;
                }

                for (var si = 0; si < cardSelectors.length; si++) {
                    var cards = document.querySelectorAll(cardSelectors[si]);
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var nameEl = card.querySelector('.job-name span') ||
                            card.querySelector('.job-name') ||
                            card.querySelector('.job-title') ||
                            card.querySelector('[class*="job-title"]');
                        if (!nameEl) {
                            var cands = card.querySelectorAll('.job-name, .job-title, [class*="job-name"]');
                            for (var n = 0; n < cands.length; n++) {
                                if (cands[n].children.length === 0) {
                                    var t = cands[n].textContent.trim();
                                    if (t.length >= 2 && t.length <= 40) { nameEl = cands[n]; break; }
                                }
                            }
                        }
                        if (nameEl) {
                            var pageName = cleanName(nameEl.textContent.trim());
                            // 精确匹配 或 双向包含
                            if (pageName === targetName ||
                                pageName.indexOf(targetName) !== -1 ||
                                targetName.indexOf(pageName) !== -1) {
                                card.scrollIntoView({block: 'center'});
                                card.click();
                                return 'clicked_card';
                            }
                        }
                    }
                }
                return 'not_found';
            '''.replace('__TARGET_NAME__', safe_name)

            result = page.run_js(js)

            if result == "clicked_card":
                time.sleep(0.8)
                return True

            logger.info("未找到卡片: %s", job_name)
            return False

        except Exception:
            logger.exception("打开详情异常")
            return False

    def _extract_jd(self):
        """从详情页右侧面板提取 JD 全文"""
        page = self.browser.driver
        try:
            jd_text = page.run_js('''
                var selectors = [
                    '.job-detail', '[class*="job-detail"]',
                    '[class*="detail-content"]', '[class*="job-desc"]',
                    '[class*="detail-box"]', '[class*="job-info-box"]',
                    '[class*="content-right"]'
                ];
                for (var s = 0; s < selectors.length; s++) {
                    var el = document.querySelector(selectors[s]);
                    if (el && el.textContent.trim().length > 50) {
                        return el.textContent.trim().substring(0, 3000);
                    }
                }
                // 兜底：取整个右侧区域
                var right = document.querySelector('[class*="right-panel"], [class*="content-right"]');
                if (right) {
                    return right.textContent.trim().substring(0, 3000);
                }
                return '';
            ''')
            return jd_text or ""
        except Exception:
            logger.exception("JD 提取异常")
            return ""

    def _extract_detail_info(self):
        """从已打开的详情页一次性抓取 公司名/薪资/JD全文（多选择器 + 文本启发式兜底）"""
        page = self.browser.driver
        try:
            info = page.run_js(r'''
                var out = {company: '', salary: '', jd: ''};

                // 1) JD 全文
                var jdSel = [
                    '.job-detail', '[class*="job-detail"]',
                    '[class*="detail-content"]', '[class*="job-desc"]',
                    '[class*="detail-box"]', '[class*="job-info-box"]',
                    '[class*="content-right"]'
                ];
                for (var s = 0; s < jdSel.length; s++) {
                    var el = document.querySelector(jdSel[s]);
                    if (el && el.textContent.trim().length > 50) {
                        out.jd = el.textContent.trim().substring(0, 5000);
                        break;
                    }
                }

                // 2) 公司名（详情面板）
                var comSel = [
                    '.job-company .name', '.job-company-name',
                    '[class*="job-company"] .name', '[class*="company-name"]',
                    '.company-info .name', '.company-name', '[class*="company-info"] .name'
                ];
                for (var c = 0; c < comSel.length; c++) {
                    var ce = document.querySelector(comSel[c]);
                    if (ce) {
                        var t = (ce.textContent || '').trim();
                        if (t.length >= 2 && t.length <= 40) { out.company = t; break; }
                    }
                }
                // 兜底：任意 class 含 company 且文本长度合理
                if (!out.company) {
                    var all = document.querySelectorAll('[class*="company"]');
                    for (var a = 0; a < all.length; a++) {
                        var t2 = (all[a].textContent || '').trim();
                        if (t2.length >= 2 && t2.length <= 40 && all[a].children.length <= 3) {
                            out.company = t2; break;
                        }
                    }
                }

                // 3) 薪资（详情面板）
                var salSel = ['[class*="salary"]', '.salary', '[class*="job-area"] [class*="salary"]'];
                for (var x = 0; x < salSel.length; x++) {
                    var se = document.querySelector(salSel[x]);
                    if (se) {
                        var st = (se.textContent || '').trim();
                        if (/\d/.test(st) && (st.indexOf('-') !== -1 || st.indexOf('K') !== -1 ||
                            st.indexOf('k') !== -1 || st.indexOf('元') !== -1)) {
                            out.salary = st.substring(0, 40); break;
                        }
                    }
                }

                return out;
            ''')
            if not isinstance(info, dict):
                info = {}
            return {
                "company": (info.get("company") or "").strip(),
                "salary": (info.get("salary") or "").strip(),
                "jd": (info.get("jd") or "").strip(),
            }
        except Exception:
            logger.exception("详情信息提取异常")
            return {"company": "", "salary": "", "jd": ""}

    def _click_chat_and_stay(self):
        """在详情页点击沟通按钮，处理弹窗（原 _click_detail_and_stay）"""
        return self._click_detail_and_stay()

    def _close_job_detail(self):
        """关闭详情页返回列表（按 Esc 或点击空白区域）"""
        page = self.browser.driver
        try:
            page.run_js('''
                // 尝试点关闭按钮
                var closeBtns = document.querySelectorAll('[class*="close"], .job-detail-close');
                for (var i = 0; i < closeBtns.length; i++) {
                    if (closeBtns[i].offsetParent !== null) {
                        closeBtns[i].click();
                        return 'closed';
                    }
                }
                // 兜底：按 Esc
                document.dispatchEvent(new KeyboardEvent('keydown', {keyCode: 27, key: 'Escape'}));
                return 'esc';
            ''')
            time.sleep(0.5)
        except Exception:
            pass

    def _click_by_job_name(self, page, job_name):
        """通过职位名找到卡片，点击后投递（一步到位）"""
        try:
            safe_name = job_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")

            result = page.run_js(f'''
                var targetName = '{safe_name}';
                var cardSelectors = [
                    '[class*="job-card-box"]',
                    '.job-card-wrapper', '.job-card-left',
                    '[class*="job-card-body"]', 'li[class*="job-card"]'
                ];

                for (var si = 0; si < cardSelectors.length; si++) {{
                    var cards = document.querySelectorAll(cardSelectors[si]);
                    for (var i = 0; i < cards.length; i++) {{
                        var card = cards[i];
                        var nameEl = card.querySelector('.job-name') ||
                            card.querySelector('.job-title') ||
                            card.querySelector('[class*="job-name"]');
                        if (!nameEl) {{
                            var allText = card.querySelectorAll('p, span, div');
                            for (var t = 0; t < Math.min(allText.length, 5); t++) {{
                                var txt = allText[t].textContent.trim();
                                if (txt.length >= 3 && txt.length <= 50 &&
                                    txt.indexOf('收藏') === -1 && txt.indexOf('立即沟通') === -1) {{
                                    nameEl = allText[t];
                                    break;
                                }}
                            }}
                        }}
                        if (nameEl) {{
                            var nameText = nameEl.textContent.trim();
                            if (nameText === targetName || nameText.indexOf(targetName) !== -1 ||
                                targetName.indexOf(nameText) !== -1) {{
                                card.scrollIntoView({{block: 'center'}});
                                card.click();
                                return 'clicked_card';
                            }}
                        }}
                    }}
                }}
                return 'not_found';
            ''')

            if result == "clicked_card":
                time.sleep(0.8)
                success = self._click_detail_and_stay()
                if not success:
                    logger.info("尝试直接在卡片内点击...")
                    return self._click_btn_in_any_card(page, safe_name)
                return True

            logger.info("未找到: %s", job_name)
            return False

        except Exception:
            logger.exception("查找异常")
            return False

    def _click_btn_in_any_card(self, page, safe_name):
        """兜底：直接在任意可见卡片中找沟通按钮并点击"""
        try:
            result = page.run_js(f'''
                var targetName = '{safe_name}';
                var cards = document.querySelectorAll('[class*="job-card-box"], .job-card-wrapper, [class*="job-card-body"]');
                for (var i = 0; i < cards.length; i++) {{
                    var card = cards[i];
                    var text = card.innerText || '';
                    if (text.indexOf(targetName) !== -1) {{
                        var btns = card.querySelectorAll('button, [role="button"], div[tabindex], [class*="btn"], [class*="chat"], [class*="apply"]');
                        for (var b = 0; b < btns.length; b++) {{
                            var btn = btns[b];
                            if (btn.offsetParent === null) continue;
                            var cls = btn.className || '';
                            if (cls.indexOf('disabled') !== -1 || btn.disabled) continue;
                            var bt = btn.textContent.trim();
                            if (bt.indexOf('继续') !== -1) continue;   // 绝不点「继续沟通」
                            if (bt.indexOf('沟通') !== -1 || bt.indexOf('投递') !== -1 || bt.indexOf('聊') !== -1) {{
                                btn.click();
                                return 'clicked_btn';
                            }}
                        }}
                        card.click();
                        return 'clicked_card';
                    }}
                }}
                return 'not_found';
            ''')
            if result.startswith("clicked"):
                time.sleep(0.8)
                self._handle_popup(page)
                return True
            return False
        except Exception:
            logger.exception("兜底异常")
            return False

    def _click_detail_and_stay(self):
        """在右侧详情面板点击沟通按钮，然后处理弹窗留在本页"""
        page = self.browser.driver

        btn_clicked = False
        target_texts = ["立即沟通", "立即投递", "聊一聊", "开始沟通"]
        try:
            js_result = page.run_js('''
                var targets = ''' + json.dumps(target_texts) + ''';
                var selectors = [
                    '.job-detail', '[class*="job-detail"]',
                    '[class*="detail-box"]', '[class*="job-info-box"]',
                    '[class*="content-right"]', '[class*="right-panel"]'
                ];
                var allContainers = [];
                for (var s = 0; s < selectors.length; s++) {
                    var els = document.querySelectorAll(selectors[s]);
                    for (var k = 0; k < els.length; k++) allContainers.push(els[k]);
                }
                if (allContainers.length === 0) allContainers.push(document.body);

                for (var ci = 0; ci < allContainers.length; ci++) {
                    var container = allContainers[ci];
                    var candidates = container.querySelectorAll(
                        'button, [role="button"], div[tabindex], span[class*="btn"], a'
                    );
                    for (var i = 0; i < candidates.length; i++) {
                        var el = candidates[i];
                        if (el.offsetParent === null) continue;
                        var cls = el.className || '';
                        if (cls.indexOf('is-disabled') !== -1 ||
                            cls.indexOf('disabled') !== -1 || el.disabled === true)
                            continue;
                        var t = el.textContent.trim();
                        if (t.indexOf('继续') !== -1) continue;   // 绝不点「继续沟通」
                        for (var j = 0; j < targets.length; j++) {
                            if (t === targets[j]) { el.click(); return {text: t}; }
                            if (t.indexOf(targets[j]) !== -1 && t.length < 10) { el.click(); return {text: t}; }
                        }
                    }
                }
                return null;
            ''')
            if js_result:
                btn_clicked = True
            else:
                logger.info("未找到可用按钮")
        except Exception:
            logger.exception("按钮查找异常")

        time.sleep(0.8)

        self._handle_popup(page)

        if btn_clicked:
            if not self._verify_chat_opened(page):
                logger.info("[投递] 已点击但对话未确认打开, 记为失败(不记'已投')")
                return False
        return btn_clicked

    def _verify_chat_opened(self, page):
        """点击沟通后, 校验对话窗口是否真的打开, 防止误记'已投'"""
        try:
            res = page.run_js('''
                var inputs = document.querySelectorAll('textarea, input');
                for (var i = 0; i < inputs.length; i++) {
                    if (inputs[i].offsetParent !== null) return 'input';
                }
                var btns = document.querySelectorAll('button, [role="button"], div[tabindex]');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent !== null &&
                        /发送|聊一聊/.test(btns[i].textContent)) return 'send';
                }
                return '';
            ''')
            return bool(res)
        except Exception:
            logger.debug("[投递] 对话校验异常", exc_info=True)
            return False

    def _handle_popup(self, page):
        """处理「已向BOSS发送消息」弹窗：只点「留在此页」，绝不点「继续沟通」"""
        for attempt in range(6):          # 多轮等待，弹窗可能延迟渲染
            try:
                time.sleep(0.4)

                # 1) 精确文本定位（只认"留在此页"）
                try:
                    stay_btn = page.ele("text=留在此页", timeout=0.3)
                except Exception:
                    stay_btn = None
                if stay_btn:
                    try:
                        # by_js=True：用 JS 直接派发点击，避免真实坐标点击误中相邻的「继续沟通」
                        stay_btn.click(by_js=True)
                        logger.info("[弹窗] 已点击「留在此页」(by_js)")
                        return True
                    except Exception:
                        try:
                            stay_btn.click(by_js=True, timeout=1)
                            logger.info("[弹窗] 已点击「留在此页」(by_js retry)")
                            return True
                        except Exception:
                            pass

                # 2) JS 兜底：只认"留在此页"，显式排除任何含"继续"的按钮
                js_result = page.run_js('''
                    var btns = document.querySelectorAll('button, [role="button"], div[tabindex], a, span');
                    var vis = [];
                    for (var i = 0; i < btns.length; i++) {
                        if (btns[i].offsetParent === null) continue;
                        vis.push({el: btns[i], t: btns[i].textContent.trim()});
                    }
                    // 优先精确"留在此页"
                    for (var j = 0; j < vis.length; j++) {
                        if (vis[j].t === '留在此页' || vis[j].t === '留在此頁') {
                            vis[j].el.click(); return 'stay';
                        }
                    }
                    // 次选：含"留"且不含"继续"（绝不碰"继续沟通"）
                    for (var k = 0; k < vis.length; k++) {
                        var tk = vis[k].t;
                        if (tk.indexOf('留') !== -1 && tk.indexOf('继续') === -1 && tk.length <= 6) {
                            vis[k].el.click(); return 'stay_loose';
                        }
                    }
                    return 'no_btn';
                ''')
                if js_result.startswith('stay'):
                    logger.info("[弹窗] 已点击「留在此页」(%s)", js_result)
                    return True

            except Exception:
                continue
        return False

    def _check_boss_limit(self):
        """检测是否撞到BOSS每日沟通次数限制"""
        page = self.browser.driver
        try:
            limit_hit = page.run_js(r'''
                var body = document.body.innerText || '';
                var limitKeywords = [
                    '今日沟通次数已达上限',
                    '今日沟通人数已达上限',
                    '今日已达沟通上限',
                    '沟通次数已达上限',
                    '今日沟通已达上限',
                    '今日投递次数已达上限',
                    '今日投递已达上限'
                ];
                for (var i = 0; i < limitKeywords.length; i++) {
                    if (body.indexOf(limitKeywords[i]) !== -1) {
                        return limitKeywords[i];
                    }
                }
                return '';
            ''')
            if limit_hit:
                logger.warning("[BOSS限制] 检测到: %s", limit_hit)
                self.boss_limit_reached = True
                return True
        except Exception:
            pass
        return False

    def _wait_until_midnight(self):
        """等待到次日0点继续投递"""
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait_seconds = (midnight - now).total_seconds()
        wait_hours = int(wait_seconds // 3600)
        wait_mins = int((wait_seconds % 3600) // 60)

        print(f"\n{'='*60}", flush=True)
        print(f"⏰ BOSS每日沟通限制已达上限", flush=True)
        print(f"   自动等待到次日0点继续投递", flush=True)
        print(f"   还需等待 {wait_hours}小时{wait_mins}分钟", flush=True)
        print(f"{'='*60}\n", flush=True)

        while True:
            if self.stop_requested:
                print(f"\n🛑 等待期间收到终止信号", flush=True)
                return False
            now = datetime.now()
            remaining = (midnight - now).total_seconds()
            if remaining <= 0:
                break
            h_rem = int(remaining // 3600)
            m_rem = int((remaining % 3600) // 60)
            s_rem = int(remaining % 60)
            print(f"\r   ⏳ 倒计时: {h_rem:02d}:{m_rem:02d}:{s_rem:02d}", end="", flush=True)
            time.sleep(min(30, remaining))

        print(f"\n\n🚀 新的一天！继续投递！\n", flush=True)
        # 重置今日计数和限制标记
        self.today_count = 0
        self.boss_limit_reached = False
        self._chat_attempt_count = 0
        # 重新打开BOSS
        self.browser.open_boss()
        return True

    # ---------- 主流程 ----------

    def _wait_until_schedule(self):
        """定时等待到指定时间"""
        if not self.schedule_config.get("enabled"):
            print("\n" + "=" * 50)
            print("自动开始投递（已登录状态）")
            print("=" * 50 + "\n")
            return

        target_hour = self.schedule_config.get("hour", 9)
        target_minute = self.schedule_config.get("minute", 0)
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        wait_hours = int(wait_seconds // 3600)
        wait_mins = int((wait_seconds % 3600) // 60)

        print("\n" + "=" * 50)
        print(f"⏰ 定时模式: 等待到 {target_hour:02d}:{target_minute:02d}")
        print(f"   还需等待 {wait_hours}小时{wait_mins}分钟")
        print(f"   浏览器已打开，请先完成登录")
        print("=" * 50 + "\n")

        while True:
            now = datetime.now()
            remaining = (target - now).total_seconds()
            if remaining <= 0:
                break
            h_rem = int(remaining // 3600)
            m_rem = int((remaining % 3600) // 60)
            s_rem = int(remaining % 60)
            print(f"\r   ⏳ 倒计时: {h_rem:02d}:{m_rem:02d}:{s_rem:02d}", end="", flush=True)
            time.sleep(min(30, remaining))

        print(f"\n\n{'='*50}")
        print(f"🚀 时间到！开始投递！")
        print(f"{'='*50}\n")

    def _process_job(self, job, keyword, seen_ids):
        """
        处理单个职位，返回状态:
        applied / skipped / filtered / agent_rejected / failed / stop
        """
        if self.stop_requested:
            return "stop"
        if self.today_count >= self.max_daily_applies:
            return "stop"
        if self.test_limit and self._total_applied >= self.test_limit:
            return "stop"
        if self._is_applied(job["id"]):
            return "skipped"

        # ====== 第一阶段：规则筛选（排除词 — 命中即跳过）======
        job_name = job.get('name', '')
        company = job.get('company', '')
        salary = job.get('salary', '')

        # 实时打印职位信息
        print(f"  [{self.today_count+1}/{self.max_daily_applies}] {job_name} | {company} | {salary}", flush=True)

        # 排除词检查（职位名 + 公司名）
        excluded, hit_word = self._check_exclude_detail(job_name)
        if not excluded:
            excluded, hit_word = self._check_exclude_detail(company)

        if excluded:
            print(f"    -> 跳过(排除词命中'{hit_word}')", flush=True)
            self._filtered_list.append({"name": job_name, "company": company, "salary": salary, "reason": f"排除词: {hit_word}"})
            # 飞轮: 记录被过滤的职位(label=pending, 待人工标注是否漏投)
            try:
                flywheel_store.add_pending(
                    job_id=job["id"], job_name=job_name, company=company,
                    salary=salary, status="excluded",
                    hit_keyword=hit_word, run_id=self.run_id, group=keyword,
                )
            except Exception:
                logger.debug("[飞轮] 写labels失败(excluded)", exc_info=True)
            return "filtered"

        # ====== 白名单校验（必须命中目标技能/角色其一，否则跳过）======
        # 按当前岗位分组取生效白名单 = config全局 + 该关键词组规则（多目标隔离，换岗不串）
        inc_list = flywheel_store.get_effective_include_for_group(keyword)
        included, inc_word = flywheel_decision.check_include(
            f"{job_name} {company}", inc_list
        )
        if not included:
            print(f"    -> 跳过(未命中白名单)", flush=True)
            self._filtered_list.append({"name": job_name, "company": company, "salary": salary, "reason": "白名单未命中"})
            try:
                flywheel_store.add_pending(
                    job_id=job["id"], job_name=job_name, company=company,
                    salary=salary, status="excluded",
                    hit_keyword="白名单", run_id=self.run_id, group=keyword,
                )
            except Exception:
                logger.debug("[飞轮] 写labels失败(白名单)", exc_info=True)
            return "filtered"

        # 薪资筛选（可选）
        salary_range = FILTER_CONFIG.get("salary_range")
        if salary_range:
            salary_ok, salary_reason = self._check_salary(salary, salary_range)
            if not salary_ok:
                print(f"    -> 跳过({salary_reason})", flush=True)
                self._filtered_list.append({"name": job_name, "company": company, "salary": salary, "reason": salary_reason})
                return "filtered"

        # ====== RAG 召回层 (关键词+飞轮历史投票) ======
        if getattr(self, 'rag_enabled', False):
            try:
                from flywheel.embedder import embedding_filter as rag_filter
                job_text = f"{job_name} {company}"
                rag_pass, rag_reason = rag_filter(job_text, self.rag_config)
                if not rag_pass:
                    print(f"    -> 跳过(RAG排除: {rag_reason})", flush=True)
                    self._filtered_list.append({"name": job_name, "company": company, "salary": salary, "reason": rag_reason})
                    try:
                        flywheel_store.add_pending(
                            job_id=job["id"], job_name=job_name, company=company,
                            salary=salary, status="excluded",
                            hit_keyword="RAG", run_id=self.run_id, group=keyword,
                        )
                    except Exception:
                        pass
                    return "filtered"
                else:
                    print(f"    -> RAG: {rag_reason}", flush=True)
            except Exception as e:
                logger.debug("[RAG] 召回失败, 兜底: %s", e)

        # ====== 打开详情页 ======
        print(f"    -> 投递中...", flush=True)
        if not self._open_job_detail(job["name"]):
            # 卡片点不开通常是该职位已沟通过/已投递（BOSS 卡片状态变化，无「立即沟通」入口）
            print(f"    -> 已投递过", flush=True)
            logger.info("[跳过] 无法打开详情(判定为已投递过): %s | %s", job_name, company)
            # 页面可能已跳离搜索列表页，重置回搜索页，避免后续连锁失败
            try:
                self.search_job(keyword)
                self.browser.random_delay(*self.delay_range)
            except Exception:
                logger.debug("[恢复] 重新打开搜索页失败", exc_info=True)
            return "skipped"

        # ====== 从详情页补全 公司/薪资/JD（无论Agent/简历是否开启都抓，用于落盘）======
        detail_info = self._extract_detail_info()
        jd_text = detail_info.get("jd", "")
        if detail_info.get("company"):
            company = detail_info["company"]
        if detail_info.get("salary"):
            salary = detail_info["salary"]

        # ====== 打印公司 / JD（让用户可见，便于核对与诊断监听/详情页是否生效）======
        if detail_info.get("company"):
            print(f"    -> 公司: {company}", flush=True)
        else:
            print(f"    -> 公司: (详情页未取到, 列表值={job.get('company', '')})", flush=True)
        if jd_text:
            print(f"    -> JD[{len(jd_text)}字]: {jd_text[:200]}", flush=True)
        else:
            print(f"    -> JD: (详情页未取到)", flush=True)

        # ====== 第二阶段：Agent 智能筛选（按需触发）======
        if self.agent_filter_enabled:
            agent = self._get_agent()
            need_agent = agent.should_trigger(job)

            if need_agent:
                self._agent_triggered += 1
                if not jd_text:
                    jd_text = self._extract_jd()
                if jd_text:
                    agent_passed, agent_reason, score = agent.analyze(job, jd_text)
                    if not agent_passed:
                        print(f"    -> Agent拒绝(评分={score} {agent_reason})", flush=True)
                        self._close_job_detail()
                        self._agent_rejected += 1
                        self._agent_rejected_list.append({"name": job_name, "score": score, "reason": agent_reason})
                        return "agent_rejected"
                    print(f"    -> Agent通过(评分={score})", flush=True)
                else:
                    print(f"    -> Agent: JD提取失败", flush=True)

        # ====== 简历匹配分析（可选）======
        if self.resume_enabled:
            if not jd_text:
                jd_text = self._extract_jd()
            if jd_text:
                self._do_resume_match(job, jd_text)

        # ====== 点沟通投递 ======
        success = self._click_chat_and_stay()
        self._chat_attempt_count += 1

        # 检测是否撞到BOSS每日沟通限制
        if self._check_boss_limit():
            print(f"    -> BOSS限制: 今日沟通次数已达上限", flush=True)
            return "limit_reached"

        if success:
            record = {
                "id": job["id"],
                "name": job_name,
                "company": company,
                "salary": salary,
                "jd": jd_text,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "keyword": keyword,
            }
            self._save_applied(record)
            self.today_count += 1
            self._total_applied += 1
            self._applied_list.append({"name": job_name, "company": company, "salary": salary})
            print(f"    -> OK ({self.today_count}/{self.max_daily_applies})", flush=True)
            # 飞轮: 记录投递成功的职位(label=pending, 待人工标注是否投对)
            try:
                flywheel_store.add_pending(
                    job_id=job["id"], job_name=job_name, company=company,
                    salary=salary, status="applied",
                    hit_keyword="", run_id=self.run_id, group=keyword,
                )
            except Exception:
                logger.debug("[飞轮] 写labels失败(applied)", exc_info=True)
            return "applied"
        else:
            print(f"    -> FAIL 点击失败", flush=True)
            self._total_failed += 1
            self._failed_list.append({"name": job_name, "company": company, "salary": salary})
            self.search_job(keyword)
            self.browser.random_delay(*self.delay_range)
            return "failed"

    def _process_keyword(self, keyword, seen_ids):
        """处理单个关键词的所有职位，更新 self._total_applied / _total_skipped / _total_filtered"""
        kw_start_count = self._total_applied
        logger.info("\n" + "=" * 60)
        logger.info("🔍 关键词 '%s' 开始 (当前已投 %d)", keyword, self._total_applied)
        logger.info("=" * 60)

        max_empty_scrolls = self.boss_limit_config.get("max_empty_scrolls", 30)
        max_filtered_batches = self.boss_limit_config.get("max_filtered_batches", 15)
        refresh_interval = self.boss_limit_config.get("refresh_interval", 300)
        refresh_wait = self.boss_limit_config.get("refresh_wait", 10)

        # 打开搜索结果页（第一页）
        self.search_job(keyword, 1)
        self.apply_filters()
        self.browser.random_delay(*self.delay_range)

        no_new_count = 0
        filtered_batch_count = 0
        scroll_round = 0
        last_refresh_time = time.time()

        while self.today_count < self.max_daily_applies:
            if self.stop_requested:
                return
            if self.test_limit and self._total_applied >= self.test_limit:
                break
            if self.boss_limit_reached:
                return

            # 定时刷新页面（每 refresh_interval 秒刷新一次）
            current_time = time.time()
            if current_time - last_refresh_time >= refresh_interval:
                print(f"\n  🔄 定时刷新页面（每{refresh_interval}秒），等待{refresh_wait}秒...", flush=True)
                logger.info("[刷新] 定时刷新页面，已运行 %d 秒", current_time - last_refresh_time)
                try:
                    self.browser.driver.refresh()
                except Exception:
                    try:
                        self.search_job(keyword, 1)
                    except Exception:
                        pass
                time.sleep(refresh_wait)
                self.apply_filters()
                last_refresh_time = time.time()
                no_new_count = 0
                filtered_batch_count = 0
                print(f"  ✅ 刷新完成，继续投递 (今日 {self.today_count}/{self.max_daily_applies})", flush=True)

            jobs = self.get_job_list()
            logger.info("[搜索] 本轮抓取 %d 条，已见 %d 条", len(jobs), len(seen_ids))

            new_jobs = []
            for j in jobs:
                if j["id"] not in seen_ids:
                    seen_ids.add(j["id"])
                    new_jobs.append(j)

            if not new_jobs:
                no_new_count += 1
                logger.info("[滚动] 无新职位(%d/%d)", no_new_count, max_empty_scrolls)
                if no_new_count >= max_empty_scrolls:
                    # 连续无新职位，说明这个关键词已经滚到底了
                    print(f"  ⚠️ 关键词 '{keyword}' 已无更多新职位", flush=True)
                    logger.info("   '%s' 已无更多结果", keyword)
                    break
                # 滚动加载更多（BOSS直聘是无限滚动，不是URL翻页）
                self.browser.scroll_down(pixel=800, delay=0.05)
                scroll_round += 1
                # 每10次滚动打印一次进度
                if no_new_count % 10 == 0:
                    print(f"    [滚动] 下滑加载中... {no_new_count}/{max_empty_scrolls} (今日 {self.today_count}/{self.max_daily_applies})", flush=True)
                continue

            no_new_count = 0
            logger.info("[处理] %d 条新职位", len(new_jobs))

            applied_in_batch = 0
            for job in new_jobs:
                status = self._process_job(job, keyword, seen_ids)
                if status == "stop":
                    return
                if status == "limit_reached":
                    return
                elif status == "skipped":
                    self._total_skipped += 1
                    continue
                elif status in ("filtered", "agent_rejected"):
                    self._total_filtered += 1
                    continue
                elif status == "applied":
                    applied_in_batch += 1
                elif status == "failed":
                    # 失败也算处理过了，继续
                    pass

            # 如果这批职位全部被过滤，记录连续过滤批次
            if applied_in_batch == 0 and len(new_jobs) > 0:
                filtered_batch_count += 1
                print(f"    [过滤] 本批{len(new_jobs)}条全被过滤 连续{filtered_batch_count}/{max_filtered_batches}批 (今日 {self.today_count}/{self.max_daily_applies})", flush=True)
                logger.info("[处理] 本批 %d 条全部被过滤，连续过滤批次(%d/%d)", len(new_jobs), filtered_batch_count, max_filtered_batches)
                # 连续多批都被过滤，说明当前可见区域没有合适的，继续往下滚找更多
                if filtered_batch_count >= max_filtered_batches:
                    print(f"  ⏬ 连续{max_filtered_batches}批全被过滤，继续下滑加载更多...", flush=True)
                    logger.info("   连续 %d 批被过滤，继续下滑加载", max_filtered_batches)
                    filtered_batch_count = 0
            else:
                # 有投递成功，重置连续过滤计数
                filtered_batch_count = 0

            # 处理完一批立刻滚动，继续找更多职位
            self.browser.scroll_down(pixel=600, delay=0.05)
            scroll_round += 1

        kw_applied = self._total_applied - kw_start_count
        logger.info("\n✅ 关键词 '%s' 完成: 本轮投递 %d 份", keyword, kw_applied)

    def _print_summary(self):
        """打印完整执行统计"""
        print("\n" + "=" * 60)
        print("📊 执行统计")
        print("=" * 60)

        # 基本计数
        print(f"\n【计数】")
        print(f"  投递成功:   {self._total_applied}")
        print(f"  规则跳过:   {self._total_filtered}")
        print(f"  已投跳过:   {self._total_skipped}")
        print(f"  点击失败:   {self._total_failed}")
        print(f"  今日累计:   {self.today_count}/{self.max_daily_applies}")

        # Agent 统计
        if self.agent_filter_enabled:
            agent_total = self._agent_triggered
            agent_rejected = self._agent_rejected
            agent_passed = agent_total - agent_rejected
            if agent_total > 0:
                reject_rate = agent_rejected / agent_total * 100
            else:
                reject_rate = 0
            print(f"\n【Agent 智能筛选】")
            print(f"  触发次数:   {agent_total}")
            print(f"  通过:       {agent_passed}")
            print(f"  拒绝:       {agent_rejected}")
            print(f"  拒绝率:     {reject_rate:.1f}%")

        # 耗时
        elapsed = datetime.now() - self._start_time
        total_seconds = int(elapsed.total_seconds())
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        if self._total_applied > 0:
            avg_per_job = total_seconds / self._total_applied
            print(f"\n【耗时】")
            print(f"  总耗时:     {h:02d}:{m:02d}:{s:02d}")
            print(f"  平均/个:    {avg_per_job:.1f}秒")

        # 投递成功的职位列表
        if self._applied_list:
            print(f"\n【投递成功列表】({len(self._applied_list)} 个)")
            for i, item in enumerate(self._applied_list, 1):
                print(f"  {i:2d}. {item['name']} | {item['company']} | {item['salary']}")

        # 被规则过滤的职位列表
        if self._filtered_list:
            print(f"\n【规则过滤列表】({len(self._filtered_list)} 个)")
            for i, item in enumerate(self._filtered_list, 1):
                print(f"  {i:2d}. {item['name']} | {item['company']} | {item['reason']}")

        # Agent 拒绝的职位列表
        if self.agent_filter_enabled and self._agent_rejected_list:
            print(f"\n【Agent 拒绝列表】({len(self._agent_rejected_list)} 个)")
            for i, item in enumerate(self._agent_rejected_list, 1):
                print(f"  {i:2d}. {item['name']} | 评分={item['score']} | {item['reason']}")

        # 失败的职位列表
        if self._failed_list:
            print(f"\n【点击失败列表】({len(self._failed_list)} 个)")
            for i, item in enumerate(self._failed_list, 1):
                print(f"  {i:2d}. {item['name']} | {item['company']}")

        # 简历匹配统计
        if self.resume_enabled and self._resume_match_list:
            print(f"\n【简历匹配列表】({len(self._resume_match_list)} 个)")
            # 按匹配度排序
            sorted_matches = sorted(self._resume_match_list, key=lambda x: x["score"], reverse=True)
            for i, item in enumerate(sorted_matches, 1):
                print(f"  {i:2d}. {item['name']} | {item['company']} | 匹配度={item['score']}")
                if item.get("matched"):
                    print(f"       匹配技能: {', '.join(item['matched'][:5])}")
                if item.get("missing"):
                    print(f"       缺失技能: {', '.join(item['missing'][:5])}")
            if self._resume_generated_count > 0:
                print(f"\n  定制简历已生成: {self._resume_generated_count} 份")

        # 飞轮状态
        try:
            from flywheel import labeler as flywheel_labeler
            summary = flywheel_labeler.get_review_summary()
            rules = flywheel_store.load_rules()
            print(f"\n【飞轮状态】")
            print(f"  本次run_id:  {self.run_id}")
            print(f"  规则版本:    v{rules.get('version', 1)} (排除词{len(rules.get('exclude_keywords', []))}个, 白名单{len(rules.get('include_keywords', []))}个)")
            print(f"  待标注:      {summary['pending_count']} 条 (已投待标:{summary['applied_pending']} 过滤待标:{summary['excluded_pending']})")
            print(f"  累计标注:    {summary['total_labeled']} (G1投对:{summary['G1']} G2错投:{summary['G2']} G3漏投:{summary['G3']} G4拦对:{summary['G4']})")
            # 计算本轮指标并保存到历史
            run_metrics = flywheel_metrics.compute_run_metrics(self.run_id)
            if run_metrics["total_labeled"] > 0:
                def _pct(v):
                    return f"{v*100:.1f}%" if v is not None else "N/A"
                print(f"  本轮准确率:  投递{_pct(run_metrics['apply_accuracy'])} 过滤{_pct(run_metrics['exclude_accuracy'])} 综合{_pct(run_metrics['overall_accuracy'])}")
            else:
                print(f"  本轮准确率:  尚无标注(标注后可计算)")
            print(f"  💡 提示:     投递完成后到GUI点'📝 标注'进行人工标注, 再点'🔧 挖掘'生成新规则")
        except Exception:
            logger.debug("[飞轮] 打印状态失败", exc_info=True)

        print("\n" + "=" * 60)

    def run(self):
        self.browser.init_browser()
        self.browser.open_boss()

        # 定时等待
        self._wait_until_schedule()

        # 初始化运行时计数器
        self._total_applied = 0
        self._total_skipped = 0
        self._total_filtered = 0
        self._total_failed = 0
        self._agent_triggered = 0
        self._agent_rejected = 0
        # 收集详情列表
        self._applied_list = []         # 投递成功
        self._filtered_list = []        # 规则过滤
        self._agent_rejected_list = []  # Agent 拒绝
        self._failed_list = []          # 点击失败
        self._start_time = datetime.now()
        # 重新生成 run_id(每次 run 都是新轮次)
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 飞轮: 合并 rules.json 的排除词到 self.exclude_keywords
        try:
            gui_exclude = list(self.exclude_keywords)  # GUI/CLI 已设置的
            merged = flywheel_decision.get_merged_exclude_keywords(gui_exclude)
            flywheel_extras = [kw for kw in merged if kw not in self.exclude_keywords]
            if flywheel_extras:
                self.exclude_keywords = merged
                logger.info("[飞轮] 合并规则库排除词 +%d: %s",
                            len(flywheel_extras), ", ".join(flywheel_extras))
            rules = flywheel_store.load_rules()
            # 白名单：config + 飞轮规则库 合并去重
            try:
                rule_inc = list(rules.get("include_keywords", []))
                merged_inc, seen_inc = [], set()
                for kw in self.include_keywords + rule_inc:
                    kw = (kw or "").strip()
                    if kw and kw.lower() not in seen_inc:
                        merged_inc.append(kw)
                        seen_inc.add(kw.lower())
                self.include_keywords = merged_inc
                if rule_inc:
                    logger.info("[飞轮] 合并规则库白名单 +%d", len(rule_inc))
            except Exception:
                logger.debug("[飞轮] 合并白名单失败, 使用 config 白名单", exc_info=True)
            logger.info("[飞轮] 规则版本 v%s, 排除词 %d 个, 白名单 %d 个, run_id=%s",
                        rules.get("version", 1),
                        len(rules.get("exclude_keywords", [])),
                        len(rules.get("include_keywords", [])),
                        self.run_id)
        except Exception:
            logger.exception("[飞轮] 加载规则失败, 使用现有排除词")

        # 加载简历（如果启用）
        if self.resume_enabled:
            self._load_resume()

        # 打印当前参数
        city_name = [name for name, code in CITY_OPTIONS.items() if code == self.city_code]
        scale_names = [name for name, code in SCALE_OPTIONS.items() if code in self.scale_codes]
        logger.info("[参数] 城市=%s(%s) | 规模=%s(%s)",
                    city_name[0] if city_name else '全国', self.city_code,
                    ', '.join(scale_names), ','.join(self.scale_codes))
        logger.info("[参数] 关键词: %s", ', '.join(self.keywords))
        if self.agent_filter_enabled:
            logger.info("[参数] Agent筛选: 开启 (模型=%s, 触发=%s, 最低分=%d)",
                        self.agent_filter_config.get("model"),
                        self.agent_filter_config.get("trigger"),
                        self.agent_filter_config.get("min_score"))
        else:
            logger.info("[参数] Agent筛选: 关闭")
        if self.resume_enabled:
            logger.info("[参数] 简历匹配: 开启 (阈值=%d, 自动生成=%s)",
                        self.resume_config.get("match_threshold", 60),
                        self.resume_config.get("auto_generate", False))
        else:
            logger.info("[参数] 简历匹配: 关闭")

        logger.info("\n[开始] 目标 %d 份，%d 个关键词轮询...\n%s",
                    self.max_daily_applies, len(self.keywords), "=" * 50)

        # 循环轮询关键词，直到达到目标数量
        max_rounds = self.boss_limit_config.get("max_rounds", None)
        max_no_progress_rounds = self.boss_limit_config.get("max_no_progress_rounds", None)
        round_num = 0
        no_progress_rounds = 0  # 连续无进展轮数
        seen_ids = set()  # 全局已见职位ID，跨轮次保持

        while self.today_count < self.max_daily_applies:
            if self.stop_requested:
                print(f"\n🛑 收到终止信号, 停止投递(已投 {self.today_count}/{self.max_daily_applies})", flush=True)
                break
            round_num += 1

            if self.test_limit and self._total_applied >= self.test_limit:
                break

            # 检测到BOSS限制，等待到次日继续
            if self.boss_limit_reached:
                if self.boss_limit_config.get("auto_continue_next_day", True):
                    if not self._wait_until_midnight():
                        break  # 等待期间被终止
                    # 重置seen_ids，新的一天重新搜索
                    seen_ids = set()
                    self.boss_limit_reached = False
                else:
                    print(f"\n⚠️ BOSS每日沟通限制已达上限，停止投递", flush=True)
                    break

            any_new = False  # 标记本轮是否有新投递
            for kw_idx, keyword in enumerate(self.keywords):
                if self.stop_requested:
                    break
                if self.today_count >= self.max_daily_applies:
                    break
                if self.test_limit and self._total_applied >= self.test_limit:
                    break
                if self.boss_limit_reached:
                    break

                print(f"\n{'#' * 60}", flush=True)
                print(f"## 轮次{round_num} 关键词 {kw_idx+1}/{len(self.keywords)}: '{keyword}' (今日 {self.today_count}/{self.max_daily_applies})", flush=True)
                print(f"{'#' * 60}", flush=True)
                kw_before = self._total_applied
                self._process_keyword(keyword, seen_ids)
                kw_applied = self._total_applied - kw_before
                if kw_applied > 0:
                    any_new = True

                if self.today_count >= self.max_daily_applies:
                    print(f"\n✅ 已达成目标 {self.max_daily_applies} 份", flush=True)
                    break

            # 检测BOSS限制（可能在关键词循环中触发）
            if self.boss_limit_reached:
                continue  # 回到while顶部处理限制

            # 连续无进展检测
            if not any_new:
                no_progress_rounds += 1
                logger.info("[轮询] 第 %d 轮无新投递，连续无进展 %d 轮", round_num, no_progress_rounds)
                if max_no_progress_rounds is not None and no_progress_rounds >= max_no_progress_rounds:
                    print(f"\n⚠️ 连续 {no_progress_rounds} 轮无新投递，停止投递", flush=True)
                    break
            else:
                no_progress_rounds = 0

            if max_rounds is not None and round_num >= max_rounds:
                print(f"\n⚠️ 已轮询 {round_num} 轮，停止 (已投 {self.today_count}/{self.max_daily_applies})", flush=True)
                break

        # 统计
        self._print_summary()

        if self.interactive:
            print("\n按回车关闭浏览器...")
            input()
        self.browser.close()
