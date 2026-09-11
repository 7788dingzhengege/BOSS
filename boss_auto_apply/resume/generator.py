# 定制简历生成模块
# 基于优化建议，修改 DOCX 简历模板，导出定制 PDF

import os
import re
import logging

logger = logging.getLogger("boss_applier")


class ResumeGenerator:
    """
    基于 DOCX 模板生成定制简历

    工作流程：
    1. 读取 DOCX 简历模板（或原简历转的 DOCX）
    2. 根据优化建议修改内容
    3. 导出为定制 PDF
    """

    def __init__(self):
        pass

    def generate(self, template_path, suggestions, output_dir, job_info=None):
        """
        生成定制简历

        :param template_path: DOCX 模板路径
        :param suggestions: optimizer.py 的优化建议 dict
        :param output_dir: 输出目录
        :param job_info: 职位信息（用于命名输出文件）
        :return: 生成的 PDF 文件路径，失败返回 None
        """
        if not os.path.exists(template_path):
            logger.error("简历模板不存在: %s", template_path)
            return None

        try:
            from docx import Document
        except ImportError:
            logger.error("未安装 python-docx，请运行: pip install python-docx")
            return None

        # 生成输出文件名
        if job_info:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', job_info.get("name", "resume"))
            company = re.sub(r'[\\/:*?"<>|]', '_', job_info.get("company", ""))
            docx_name = f"简历_{safe_name}_{company}.docx"
            pdf_name = f"简历_{safe_name}_{company}.pdf"
        else:
            docx_name = "简历_定制版.docx"
            pdf_name = "简历_定制版.pdf"

        os.makedirs(output_dir, exist_ok=True)
        docx_path = os.path.join(output_dir, docx_name)
        pdf_path = os.path.join(output_dir, pdf_name)

        try:
            # 1. 读取模板
            doc = Document(template_path)

            # 2. 应用修改建议
            modifications = suggestions.get("modifications", []) if suggestions else []
            applied_count = self._apply_modifications(doc, modifications)
            logger.info("[简历生成] 应用了 %d/%d 条修改建议", applied_count, len(modifications))

            # 3. 保存修改后的 DOCX
            doc.save(docx_path)
            logger.info("[简历生成] DOCX 已保存: %s", docx_path)

            # 4. 转换为 PDF
            pdf_result = self._docx_to_pdf(docx_path, pdf_path)
            if pdf_result:
                logger.info("[简历生成] PDF 已生成: %s", pdf_path)
                return pdf_path
            else:
                logger.warning("[简历生成] PDF 转换失败，返回 DOCX 路径")
                return docx_path

        except Exception:
            logger.exception("简历生成异常")
            return None

    def _apply_modifications(self, doc, modifications):
        """
        将优化建议应用到 DOCX 文档

        :param doc: python-docx Document 对象
        :param modifications: 修改建议列表
        :return: 成功应用的修改数
        """
        applied = 0

        for mod in modifications:
            action = mod.get("action", "")
            section = mod.get("section", "")
            suggested = mod.get("suggested", "")
            original = mod.get("original", "")

            try:
                if action == "modify" and original:
                    # 替换原文
                    if self._replace_text_in_doc(doc, original, suggested):
                        applied += 1
                        logger.debug("  [修改] %s: %s -> %s", section, original[:30], suggested[:30])

                elif action == "add":
                    # 在指定段落后新增内容
                    if self._add_text_to_section(doc, section, suggested):
                        applied += 1
                        logger.debug("  [新增] %s: %s", section, suggested[:30])

                elif action == "highlight":
                    # 突出显示某段文字（加粗）
                    if self._highlight_text(doc, suggested):
                        applied += 1
                        logger.debug("  [突出] %s: %s", section, suggested[:30])

                elif action == "reorder":
                    # 调整顺序 — 较复杂，记录日志即可
                    logger.info("  [调整顺序建议] %s: %s（需手动调整）", section, suggested[:50])

            except Exception:
                logger.debug("应用修改建议异常: %s", mod)
                continue

        return applied

    def _replace_text_in_doc(self, doc, old_text, new_text):
        """
        在 DOCX 中查找并替换文本

        :return: 是否成功替换
        """
        old_text = old_text.strip()
        if not old_text or len(old_text) < 3:
            return False

        replaced = False
        for paragraph in doc.paragraphs:
            if old_text in paragraph.text:
                # 替换段落中的文本，保留格式
                for run in paragraph.runs:
                    if old_text in run.text:
                        run.text = run.text.replace(old_text, new_text)
                        replaced = True
                # 如果 run 级别没替换到，整段替换
                if not replaced and old_text in paragraph.text:
                    # 清空所有 run，在第一个 run 写入新文本
                    if paragraph.runs:
                        paragraph.runs[0].text = paragraph.text.replace(old_text, new_text)
                        for run in paragraph.runs[1:]:
                            run.text = ""
                    replaced = True

        # 也检查表格中的文本
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if old_text in paragraph.text:
                            for run in paragraph.runs:
                                if old_text in run.text:
                                    run.text = run.text.replace(old_text, new_text)
                                    replaced = True

        return replaced

    def _add_text_to_section(self, doc, section_name, text):
        """
        在指定段落后新增内容

        :return: 是否成功添加
        """
        section_keywords = {
            "专业技能": ["专业技能", "技能", "技术栈"],
            "项目经历": ["项目经历", "项目经验", "项目"],
            "工作经历": ["工作经历", "工作经验"],
            "教育经历": ["教育经历", "教育背景"],
            "自我评价": ["自我评价", "个人总结"],
        }

        # 找到匹配的段标题关键词
        target_keywords = section_keywords.get(section_name, [section_name])

        # 在文档中找到该段标题，在其后插入新段落
        for i, paragraph in enumerate(doc.paragraphs):
            para_text = paragraph.text.strip()
            for kw in target_keywords:
                if kw in para_text and len(para_text) <= 10:
                    # 找到段标题，在下一个位置插入
                    # python-docx 没有直接 insert 方法，用 XML 操作
                    new_paragraph = paragraph.insert_paragraph_before(text) if i == 0 else None
                    # 简化方案：在段标题后的段落追加
                    if i + 1 < len(doc.paragraphs):
                        next_para = doc.paragraphs[i + 1]
                        next_para.insert_paragraph_before(text)
                    return True

        return False

    def _highlight_text(self, doc, text):
        """将指定文本加粗突出"""
        text = text.strip()
        if not text or len(text) < 3:
            return False

        for paragraph in doc.paragraphs:
            if text in paragraph.text:
                for run in paragraph.runs:
                    if text in run.text:
                        run.bold = True
                        return True
        return False

    def _docx_to_pdf(self, docx_path, pdf_path):
        """DOCX 转 PDF（Windows 使用 Word COM 接口）"""
        try:
            from docx2pdf import convert
            convert(docx_path, pdf_path)
            return pdf_path if os.path.exists(pdf_path) else None
        except Exception:
            logger.warning("docx2pdf 转换失败（可能未安装 Word），尝试其他方式")
            # 可以在这里加其他转换方式，如 LibreOffice 命令行
            return None
