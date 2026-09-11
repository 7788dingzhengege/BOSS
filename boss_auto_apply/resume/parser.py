# PDF 简历解析模块
# 使用 PyMuPDF 提取 PDF 文本，并通过大模型结构化

import re
import logging

logger = logging.getLogger("boss_applier")


class ResumeParser:
    """PDF 简历解析器"""

    def __init__(self):
        pass

    def parse(self, pdf_path):
        """
        解析 PDF 简历，返回结构化文本

        :param pdf_path: PDF 文件路径
        :return: dict {
            "raw_text": 全文,
            "sections": {"基本信息": ..., "教育经历": ..., ...},
            "skills": [提取的技能关键词],
            "char_count": 字符数
        }
        """
        raw_text = self._extract_text(pdf_path)
        if not raw_text:
            logger.error("PDF 文本提取失败: %s", pdf_path)
            return None

        logger.info("简历解析成功: %d 字符", len(raw_text))

        # 按常见标题分段
        sections = self._split_sections(raw_text)
        # 简单提取技能关键词
        skills = self._extract_skills(raw_text)

        return {
            "raw_text": raw_text,
            "sections": sections,
            "skills": skills,
            "char_count": len(raw_text),
        }

    def _extract_text(self, pdf_path):
        """用 PyMuPDF 提取 PDF 全文"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("未安装 PyMuPDF，请运行: pip install PyMuPDF")
            return ""

        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts).strip()
        except Exception:
            logger.exception("PDF 读取异常: %s", pdf_path)
            return ""

    def _split_sections(self, text):
        """
        按常见简历标题分段
        返回 {标题: 内容} 字典
        """
        # 常见简历段标题
        section_titles = [
            "个人信息", "基本信息", "联系方式",
            "教育经历", "教育背景", "学历",
            "工作经历", "工作经验", "实习经历", "工作经历",
            "项目经历", "项目经验", "项目",
            "专业技能", "技能", "技术栈",
            "自我评价", "个人总结", "关于我",
            "获奖经历", "证书", "荣誉",
            "校园经历", "社团活动",
        ]

        sections = {}
        lines = text.split("\n")
        current_title = "未分类"
        current_lines = []

        for line in lines:
            line_stripped = line.strip()
            # 检查是否是段标题（精确匹配或高相似度）
            matched_title = None
            for title in section_titles:
                if line_stripped == title or line_stripped.replace("：", "").replace(":", "") == title:
                    matched_title = title
                    break

            if matched_title:
                if current_lines:
                    sections[current_title] = "\n".join(current_lines).strip()
                current_title = matched_title
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_title] = "\n".join(current_lines).strip()

        return sections

    def _extract_skills(self, text):
        """从简历文本中简单提取技能关键词"""
        # 常见技术技能词库
        skill_patterns = [
            r'Python', r'Java', r'JavaScript', r'TypeScript', r'Go', r'Rust', r'C\+\+',
            r'React', r'Vue', r'Angular', r'Node\.js', r'Flask', r'Django', r'FastAPI',
            r'SQL', r'MySQL', r'Redis', r'MongoDB', r'PostgreSQL',
            r'Docker', r'Kubernetes', r'AWS', r'GCP', r'Azure',
            r'Git', r'Linux', r'Shell',
            r'LLM', r'GPT', r'BERT', r'Transformer', r'RAG', r'AI Agent',
            r'机器学习', r'深度学习', r'自然语言处理', r'NLP', r'计算机视觉', r'CV',
            r'PyTorch', r'TensorFlow', r'Pandas', r'NumPy', r'Scikit-learn',
            r'产品经理', r'产品设计', r'用户研究', r'数据分析',
            r'Prompt Engineering', r'AIGC', r'多模态',
        ]

        skills = []
        for pattern in skill_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                skill = matches[0]
                if skill not in skills:
                    skills.append(skill)

        return skills
