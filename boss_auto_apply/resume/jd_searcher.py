# BOSS直聘JD搜索器
# 用DrissionPage搜索职位并提取JD全文，供智能简历模块使用

import time
import logging
import urllib.parse

logger = logging.getLogger("boss_applier")


class JDSearcher:
    """BOSS直聘JD搜索器"""

    def __init__(self):
        self._page = None

    def _get_page(self):
        """延迟初始化浏览器页面"""
        if self._page is None:
            from DrissionPage import ChromiumPage
            self._page = ChromiumPage()
        return self._page

    def search(self, keyword, city_code="101010100", internship_only=True):
        """
        搜索职位，返回职位列表

        :param keyword: 搜索关键词
        :param city_code: 城市代码
        :param internship_only: 是否只搜实习
        :return: [{name, company, salary, jid}]
        """
        page = self._get_page()

        params = {"query": keyword, "city": city_code}
        if internship_only:
            params["jobType"] = "1902"
        params["ka"] = "sort-time"

        url = f"https://www.zhipin.com/web/geek/jobs?{urllib.parse.urlencode(params)}"
        logger.info("[JD搜索] URL: %s", url)
        page.get(url)
        time.sleep(2)

        # 滚动加载更多
        for _ in range(2):
            page.run_js("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.5)

        jobs = page.run_js(r'''
            var jobs = [];
            var selectors = [
                '[class*="job-card-box"]',
                '.job-card-wrapper', '.job-card-left',
                '[class*="job-card-body"]', 'li[class*="job-card"]'
            ];

            function cleanName(raw) {
                if (!raw) return '';
                var name = raw.trim();
                name = name.replace(/\s*[（(]\s*[A-Za-z]{1,4}\d{3,}\s*[)）]\s*$/g, '');
                name = name.replace(/\s*面议\s*$/g, '');
                var cutIdx = name.search(/[\-]\d|\d+元|\d+天\/周|\d+个月|本科|硕士|博士|大专/);
                if (cutIdx > 3) name = name.substring(0, cutIdx).trim();
                name = name.replace(/[\s\-·]+$/g, '');
                return name;
            }

            for (var si = 0; si < selectors.length; si++) {
                var cards = document.querySelectorAll(selectors[si]);
                if (cards.length > 0) {
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var nameEl = card.querySelector('.job-name span') ||
                            card.querySelector('.job-name') ||
                            card.querySelector('.job-title');
                        var companyEl = card.querySelector('.company-name a') ||
                            card.querySelector('.company-name') ||
                            card.querySelector('[class*="company-name"]');
                        var salaryEl = card.querySelector('.salary') ||
                            card.querySelector('[class*="salary"]');
                        var jid = card.getAttribute('data-jid') ||
                            card.getAttribute('data-id') ||
                            card.getAttribute('data-pid') || '';

                        if (nameEl) {
                            jobs.push({
                                name: cleanName(nameEl.textContent.trim()),
                                company: companyEl ? companyEl.textContent.trim().substring(0, 30) : '',
                                salary: salaryEl ? salaryEl.textContent.trim() : '',
                                jid: jid
                            });
                        }
                    }
                    return jobs;
                }
            }
            return jobs;
        ''')

        logger.info("[JD搜索] 找到 %d 个职位", len(jobs) if jobs else 0)
        return jobs or []

    def fetch_jd(self, job_name):
        """
        点击指定职位卡片，获取JD全文

        :param job_name: 职位名称
        :return: JD文本
        """
        page = self._get_page()

        safe_name = (job_name.replace("\\", "\\\\")
                     .replace("'", "\\'").replace('"', '\\"')
                     .replace("\n", "\\n"))

        result = page.run_js(rf'''
            var targetName = '{safe_name}';
            var cardSelectors = [
                '[class*="job-card-box"]',
                '.job-card-wrapper', '.job-card-left',
                '[class*="job-card-body"]', 'li[class*="job-card"]'
            ];

            function cleanName(raw) {{
                if (!raw) return '';
                var name = raw.trim();
                name = name.replace(/\s*[（(]\s*[A-Za-z]{{1,4}}\d{{3,}}\s*[)）]\s*$/g, '');
                name = name.replace(/\s*面议\s*$/g, '');
                var cutIdx = name.search(/[\-]\d|\d+元|\d+天\/周|\d+个月|本科|硕士|博士|大专/);
                if (cutIdx > 3) name = name.substring(0, cutIdx).trim();
                name = name.replace(/[\s\-·]+$/g, '');
                return name;
            }}

            for (var si = 0; si < cardSelectors.length; si++) {{
                var cards = document.querySelectorAll(cardSelectors[si]);
                for (var i = 0; i < cards.length; i++) {{
                    var card = cards[i];
                    var nameEl = card.querySelector('.job-name span') ||
                        card.querySelector('.job-name') ||
                        card.querySelector('.job-title');
                    if (nameEl) {{
                        var pageName = cleanName(nameEl.textContent.trim());
                        if (pageName === targetName ||
                            pageName.indexOf(targetName) !== -1 ||
                            targetName.indexOf(pageName) !== -1) {{
                            card.scrollIntoView({{block: 'center'}});
                            card.click();
                            return 'clicked';
                        }}
                    }}
                }}
            }}
            return 'not_found';
        ''')

        if result != 'clicked':
            logger.warning("[JD搜索] 未找到职位: %s", job_name)
            return ""

        time.sleep(1.5)

        jd = page.run_js(r'''
            function cleanJD(raw) {
                if (!raw) return '';
                var lines = raw.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
                var out = [];
                var stopKeywords = ['工作地址', '公司介绍', '工商信息', '工作地点',
                    '求职工具', '热门职位', '热门城市', '热门企业', '附近城市',
                    '去App', '前往App', '与BOSS', '去升级', '升级VIP',
                    '职位描述', '岗位描述', '岗位职责', '职位要求', '岗位要求'];
                var startFound = false;
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (!startFound) {
                        if (/^[\d一二三四五六七八九十][、\.\)）]/.test(line) ||
                            line.indexOf('岗位职责') !== -1 ||
                            line.indexOf('职位描述') !== -1 ||
                            line.indexOf('工作内容') !== -1 ||
                            line.length > 8 && (line.indexOf('、') !== -1 || line.indexOf('，') !== -1)) {
                            startFound = true;
                        } else {
                            continue;
                        }
                    }
                    var stop = false;
                    for (var k = 0; k < stopKeywords.length; k++) {
                        if (line.indexOf(stopKeywords[k]) !== -1 && out.length > 2) {
                            stop = true;
                            break;
                        }
                    }
                    if (stop) break;
                    if (line.length < 2) continue;
                    if (line.match(/^[a-zA-Z_$][a-zA-Z0-9_$]*\{/)) continue;
                    if (line.indexOf('display:') !== -1) continue;
                    if (line.indexOf('font-size:') !== -1) continue;
                    if (line.indexOf('{display:') !== -1) continue;
                    out.push(line);
                }
                return out.join('\n').substring(0, 2000);
            }

            var selectors = [
                '[class*="job-detail"] [class*="desc"]',
                '[class*="job-detail"] [class*="content"]',
                '[class*="detail-content"]',
                '[class*="job-desc"]',
                '[class*="job-detail"]',
                '[class*="detail-box"]',
                '[class*="content-right"]'
            ];
            for (var s = 0; s < selectors.length; s++) {
                var el = document.querySelector(selectors[s]);
                if (el) {
                    var cleaned = cleanJD(el.textContent);
                    if (cleaned.length > 50) return cleaned;
                }
            }
            return '';
        ''')

        logger.info("[JD搜索] JD提取: %d 字符", len(jd) if jd else 0)
        return jd or ""

    def close(self):
        """关闭浏览器"""
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass
            self._page = None
