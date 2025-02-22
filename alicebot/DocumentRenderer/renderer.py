import markdown.util
import requests
import traceback
import asyncio
import re
import os
import sys
import asyncio
from pyppeteer import launch
from bs4 import BeautifulSoup
import tiktoken
import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import SimpleTagPattern
from markdown.blockprocessors import BlockProcessor
import base64
import xml.etree.ElementTree as ET
import threading
import random
from queue import Queue
import pathlib

from typing import Callable, Any

log_func: Callable[[Any], None]

project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent), log_func=log_func)
latex = package.load_module("latex", log_func=log_func)
wolfram_alpha = package.load_module("wolfram_alpha", log_func=log_func)
typst_render = package.load_module("typst_render", log_func=log_func)
safe_python_executor = package.load_module("safe_python_executor", log_func=log_func)


async def setup_browser():
    try:
        cache_dir = "./.pyppeteer"
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        if sys.platform.startswith("linux"):
            browser = await launch(headless=True, executablePath="/usr/bin/chromium-browser", dumpio=True,
                                   args=['--no-sandbox', '--disable-setuid-sandbox'], userDataDir=cache_dir)
            return browser
        else:
            browser = await launch(headless=True, dumpio=True, userDataDir=cache_dir)
        return browser
    except Exception as e:
        log_func("[Web Search]Chrome not found, using Edge instead")
        edge_path = os.environ.get("EDGE_PATH", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe")
        browser = await launch(headless=True, executablePath=edge_path)
        return browser


async def bing_search(browser, query: str, max_results: int = 3):
    page = None
    try:
        page = await browser.newPage()
        log_func("[Web Search]Searching Bing for:", query)
        await page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        await page.setExtraHTTPHeaders({
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive'
        })

        await page.setJavaScriptEnabled(True)
        page.setDefaultNavigationTimeout(120000)

        await asyncio.sleep(random.uniform(1, 3))
        log_func("[Web Search]Navigating to Bing")
        try:
            response = await page.goto('https://www.bing.com/',
                                       waitUntil=['networkidle0'])
            if not response.ok:
                raise Exception(f"Failed to load Bing: {response.status}")
        except Exception as e:
            log_func(f"Navigation error: {e}")
            return [{"title": "Navigation failed", "url": "", "content": str(e)}]
        log_func("[Web Search]Searching for:", query)
        search_selector = '#sb_form_q'
        await page.waitForSelector(search_selector, {'timeout': 10000})
        await page.type(search_selector, query, {'delay': random.randint(5, 7)})
        await asyncio.sleep(random.uniform(0.5, 1))

        await page.keyboard.press('Enter')
        await page.waitForNavigation({'waitUntil': 'networkidle0'})
        log_func("[Web Search]Waiting for search results")
        results_selector = '#b_results .b_algo'
        await page.waitForSelector(results_selector, {'timeout': 10000})

        results = await page.evaluate('''
            () => {
                const results = [];
                
                // 普通结果
                document.querySelectorAll('#b_results .b_algo').forEach(item => {
                    const titleEl = item.querySelector('h2 a');
                    const snippetEl = item.querySelector('.b_caption p, .b_snippet');
                    
                    if(titleEl && titleEl.innerText && titleEl.href) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            url: titleEl.href,
                            content: snippetEl ? snippetEl.innerText.trim() : ''
                        });
                    }
                });
                
                // 图片+标题布局
                document.querySelectorAll('.b_imgcap_altitle').forEach(item => {
                    const titleEl = item.querySelector('h2 a');
                    const snippetEl = item.querySelector('.b_lineclamp3, p');
                    
                    if(titleEl && titleEl.innerText && titleEl.href) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            url: titleEl.href,
                            content: snippetEl ? snippetEl.innerText.trim() : ''
                        });
                    }
                });

                // 顶部答案框
                document.querySelectorAll('.b_ans').forEach(item => {
                    const titleEl = item.querySelector('.b_entityTitle a, h2 a');
                    const snippetEl = item.querySelector('.b_caption, .b_snippet, .b_factrow');
                    
                    if(titleEl && titleEl.innerText) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            url: titleEl.href || '',
                            content: snippetEl ? snippetEl.innerText.trim() : ''
                        });
                    }
                });

                // 垂直列表结果
                document.querySelectorAll('.b_vList').forEach(item => {
                    const titleEl = item.querySelector('h2 a, .b_title a');
                    const snippetEl = item.querySelector('.b_caption, .b_snippet');
                    
                    if(titleEl && titleEl.innerText && titleEl.href) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            url: titleEl.href,
                            content: snippetEl ? snippetEl.innerText.trim() : ''
                        });
                    }
                });

                // 大片段结果
                document.querySelectorAll('.b_snippetLarge').forEach(item => {
                    const titleEl = item.querySelector('h2 a');
                    const snippetEl = item.querySelector('.b_text');
                    
                    if(titleEl && titleEl.innerText && titleEl.href) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            url: titleEl.href,
                            content: snippetEl ? snippetEl.innerText.trim() : ''
                        });
                    }
                });
                
                return results.filter(r => r.title);
            }
        ''')
        log_func("[Web Search]Results:", results)
        await page.close()

        if not results:
            return ["No results found"]

        return results[:max_results]

    except Exception as e:
        log_func(f"[Search Error] {str(e)}")
        return [f"Search failed: {str(e)}"]
    finally:
        if page and not page.isClosed():
            await page.close()


async def web_search(browser, query, max_results=3, search_engine="Bing"):
    if search_engine == "Bing":
        return await bing_search(browser, query, max_results)
    else:
        return ["Invalid search engine"]


async def get_webpage(browser, url, only_text=False, max_token=2048):
    try:
        page = await browser.newPage()
        await page.goto(url, timeout=60000)

        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        text = ""
        for i in soup.find_all(
                ["p", "span", "h1", "h2", "h3", "h4", "h5", "h6", "code", "img", "cite", "a", "ul", "ol", "li", "br",
                 "dl", "dt", "dd"]):
            if i.name == "p" or i.name == "a" or i.name == "span":
                text += i.get_text(" ", strip=True) + " "
            elif i.name[0] == "h" and i.name[1].isdigit():
                text += "\n" + "#" * int(i.name[1]) + " " + i.get_text(" ", strip=True) + "\n"
            elif i.name == "code":
                text += "```\n" + i.get_text(" ", strip=True) + "\n```" + "\n\n"
            elif i.name == "img":
                if only_text:
                    continue
                if "src" not in i.attrs:
                    continue
                text += "![](" + i["src"] + ")" + "\n\n"
            elif i.name == "cite":
                if only_text:
                    continue
                text += "> " + i.get_text(" ", strip=True) + "\n\n"
            elif i.name == "ul":
                text += "\n"
                for j in i.find_all("li"):
                    text += "- " + j.get_text(" ", strip=True) + "\n"
                text += "\n"
            elif i.name == "ol":
                text += "\n"
                for j in i.find_all("li"):
                    text += "1. " + j.get_text(" ", strip=True) + "\n"
                text += "\n"
            elif i.name == "br":
                text += "\n"
            elif i.name == "dl":
                text += "\n"
                for j in i.find_all("dt"):
                    text += "**" + j.get_text(" ", strip=True) + "**" + "\n"
                    for k in j.find_next_siblings():
                        if k.name == "dd":
                            text += k.get_text(" ", strip=True) + "\n"
                        else:
                            break
                text += "\n"
        tokens = tiktoken.encoding_for_model("gpt-3.5-turbo-1106").encode(text)
        size = len(tokens)
        if size > max_token:
            tokens = tokens[:max_token]
            size = max_token
            text = tiktoken.encoding_for_model("gpt-3.5-turbo-1106").decode(tokens) + "\n\n[Text too long, truncated]"
        else:
            text = tiktoken.encoding_for_model("gpt-3.5-turbo-1106").decode(tokens)
        log_func("[Web Search]Text:", text)
        log_func("[Web Search]Token Size:", size)
        await page.close()
        return {"text": text, "size": size}
    except Exception as e:
        log_func(traceback.format_exc())
        return {"text": "ERROR", "size": 0}


def MarkdownRenderer(browser):
    html_replacements = []

    class _MarkdownRenderer:
        def __init__(self) -> None:
            pass

        class DelExtension(Extension):
            def extendMarkdown(self, md):
                DEL_RE = r'(?<!\\)(~~)(?![^\\]*\\)(.+?)(?<!\\)(~~)'
                md.inlinePatterns.register(SimpleTagPattern(DEL_RE, 'del'), 'del', 170)

        class InsExtension(Extension):
            def extendMarkdown(self, md):
                INS_RE = r'(?<!\\)(\+\+)(?![^\\]*\\)(.+?)(?<!\\)(\+\+)'
                md.inlinePatterns.register(SimpleTagPattern(INS_RE, 'ins'), 'ins', 170)

        class SubExtension(Extension):
            def extendMarkdown(self, md):
                SUB_RE = r'(?<!\\)(~)(?![^\\]*\\)(.+?)(?<!\\)(~)'
                md.inlinePatterns.register(SimpleTagPattern(SUB_RE, 'sub'), 'sub', 170)

        class SupExtension(Extension):
            def extendMarkdown(self, md):
                SUP_RE = r'(?<!\\)(\^)(?![^\\]*\\)(.+?)(?<!\\)(\^)'
                md.inlinePatterns.register(SimpleTagPattern(SUP_RE, 'sup'), 'sup', 170)

        class MarkExtension(Extension):
            def extendMarkdown(self, md):
                MARK_RE = r'(?<!\\)(==)(?![^\\]*\\)(.+?)(?<!\\)(==)'
                md.inlinePatterns.register(SimpleTagPattern(MARK_RE, 'mark'), 'mark', 170)

        class UnderlineExtension(Extension):
            def extendMarkdown(self, md):
                UNDERLINE_RE = r'(?<!\\)(__)(?![^\\]*\\)(.+?)(?<!\\)(__)'
                md.inlinePatterns.register(SimpleTagPattern(UNDERLINE_RE, 'u'), 'u', 170)

        class SmallExtension(Extension):
            def extendMarkdown(self, md):
                SMALL_RE = r'(?<!\\)(,,)(?![^\\]*\\)(.+?)(?<!\\)(,,)'
                md.inlinePatterns.register(SimpleTagPattern(SMALL_RE, 'small'), 'small', 170)

        class TtExtension(Extension):
            def extendMarkdown(self, md):
                TT_RE = r'(?<!\\)(``)(?![^\\]*\\)(.+?)(?<!\\)(``)'
                md.inlinePatterns.register(SimpleTagPattern(TT_RE, 'tt'), 'tt', 170)

        class PieChartExtension(Extension):
            def extendMarkdown(self, md):
                # 饼图
                # 格式：
                # <piechart>label1: value1, label2: value2, ...</piechart>
                PIECHART_RE = r'<piechart>(.*?)</piechart>'
                md.inlinePatterns.register(_MarkdownRenderer.PieChartProcessor(PIECHART_RE), 'piechart', 170)

        class PieChartProcessor(SimpleTagPattern):
            def __init__(self, pattern):
                self.pattern = pattern
                super().__init__(pattern, 'piechart')

            def handleMatch(self, m):
                try:
                    log_func("[Pie Chart]", m.group(2))
                    data = m.group(2)
                    if not data or not data.strip():
                        return m.group(0)

                    data = data.split(",")
                    labels = []
                    values = []

                    for i in data:
                        try:
                            i = i.strip().split(":")
                            if len(i) != 2:
                                return m.group(0)
                            value = float(i[1].strip())
                            if value < 0:
                                return m.group(0)
                            labels.append(i[0])
                            values.append(value)
                        except:
                            return m.group(0)

                    img = latex.get_pie_chart_image_data(values, labels)
                    if img is None:
                        return m.group(0)

                    img = base64.b64encode(img).decode()
                    replacement = f"\x02HTML:{len(html_replacements[-1])}\x03"
                    html_replacements[-1].append(
                        (
                        replacement, f'<img src="data:image/png;base64,{img}" style="display: block; margin: 0 auto;">')
                    )
                    return replacement

                except:
                    return m.group(0)

        class ImgExtension(Extension):
            def extendMarkdown(self, md):
                # 图片
                # ![alt](url) 或 ![alt](url "title") 或 ![alt](data:image/...)
                IMG_RE = r'!\[(.*?)\]\((data:image\/.*?;base64,.*?|.*?)(?:\s+"(.*?)")?\)'  # 支持 base64 编码的图片
                md.inlinePatterns.register(_MarkdownRenderer.GenerateImgTag(IMG_RE), 'img', 180)

        class GenerateImgTag(SimpleTagPattern):
            def __init__(self, pattern):
                self.pattern = pattern
                super().__init__(pattern, "img")

            def handleMatch(self, m):
                alt = m.group(2)
                img = m.group(3)
                # 判断是base64编码还是url，如果是url则尝试下载
                not_middle = len(alt) > 0 and alt[0] == "@"
                if img.startswith("data:image/"):
                    # 居中对齐
                    if not_middle:
                        alt = alt[1:]
                        # 自由图片位置（可以插入到任意位置，非居中）
                        return ET.Element("img", alt=alt, src=img, style="vertical-align:middle;")
                    else:
                        return ET.Element("img", alt=alt, src=img, style="display: block; margin: 0 auto;")
                else:
                    try:
                        img_format = img.split(".")[-1]
                        img = requests.get(img).content

                        img = base64.b64encode(img).decode()
                    except:
                        if not_middle:
                            alt = alt[1:]
                            # 自由图片位置（可以插入到任意位置，非居中）
                            return ET.Element("img", alt=alt, src=img)
                        else:
                            return ET.Element("img", alt=alt, src=img, style="display: block; margin: 0 auto;")
                if not_middle:
                    alt = alt[1:]
                    # 自由图片位置（可以插入到任意位置，非居中）
                    return ET.Element("img", alt=alt, src=f"data:image/{img_format};base64,{img}")
                else:
                    return ET.Element("img", alt=alt, src=f"data:image/{img_format};base64,{img}",
                                      style="display: block; margin: 0 auto;")

        class FontExtension(Extension):
            def extendMarkdown(self, md):
                FONT_RE = r'(?s)<font=(.*?)>(.*?)</font>'
                md.parser.blockprocessors.register(_MarkdownRenderer.FontPattern(md.parser, FONT_RE), 'font', 183)

        class FontPattern(BlockProcessor):
            def __init__(self, parser, pattern):
                super().__init__(parser)
                self.pattern = re.compile(pattern, re.DOTALL | re.MULTILINE)

            def test(self, parent, block):
                return bool(self.pattern.search(block))

            def run(self, parent, blocks):
                block = blocks.pop(0)
                match = self.pattern.search(block)
                if match:
                    remaining_blocks = block[match.end():].lstrip()
                    if remaining_blocks:
                        blocks.insert(0, remaining_blocks)
                    font_name = match.group(1)
                    text = match.group(2)
                    el = ET.SubElement(parent, 'span', attrib={'style': f'font-family: {font_name};'})
                    el.text = text

        class WolframAlphaExtension(Extension):
            def extendMarkdown(self, md):
                md.parser.blockprocessors.register(_MarkdownRenderer.WolframAlphaProcessor(md.parser), 'wolframalpha',
                                                   184)

        class WolframAlphaProcessor(BlockProcessor):
            def __init__(self, parser):
                super().__init__(parser)
                self.WOLFRAM_RE = re.compile(r'(?s)<wolframalpha>(.*?)</wolframalpha>', re.DOTALL | re.MULTILINE)

            def test(self, parent, block):
                return bool(self.WOLFRAM_RE.search(block))

            def run(self, parent, blocks):
                block = blocks.pop(0)
                match = self.WOLFRAM_RE.search(block)
                if match:
                    remaining_blocks = block[match.end():].lstrip()
                    if remaining_blocks:
                        blocks.insert(0, remaining_blocks)

                    log_func("[Wolfram Alpha]Query:", match.groups())
                    query = match.group(1)
                    try:
                        result = asyncio.run(wolfram_alpha.wolfram_alpha_compute(query))
                        if result is None:
                            html = """<div class="alert alert-warning" role="alert">No results</div>"""
                        else:
                            html = asyncio.run(wolfram_alpha.format_to_HTML(result))
                    except:
                        log_func(f"[Wolfram Alpha]Error: {traceback.format_exc()}")
                        html = """<div class="alert alert-warning" role="alert">No results</div>"""

                    replacement = f"\x02HTML:{len(html_replacements[-1])}\x03"
                    html_replacements[-1].append((replacement, html))

                    chart = ET.SubElement(parent, 'div')
                    chart.text = replacement
                    return True
                return False

        class MatplotlibExtension(Extension):
            def extendMarkdown(self, md):
                md.parser.blockprocessors.register(_MarkdownRenderer.MatplotlibProcessor(md.parser), 'matplotlib', 184)

        class MatplotlibProcessor(BlockProcessor):
            def __init__(self, parser):
                super().__init__(parser)
                self.MATPLOT_RE = re.compile(r'(?s)<matplotlib_plot>(.*?)</matplotlib_plot>', re.DOTALL | re.MULTILINE)

            def test(self, parent, block):
                return bool(self.MATPLOT_RE.search(block))

            def run(self, parent, blocks):
                block = blocks.pop(0)
                match = self.MATPLOT_RE.search(block)
                if match:
                    remaining_blocks = block[match.end():].lstrip()
                    if remaining_blocks:
                        blocks.insert(0, remaining_blocks)

                    result = self.process_plot(match)
                    replacement = f"\x02HTML:{len(html_replacements[-1])}\x03"
                    html_replacements[-1].append((replacement, result))

                    chart = ET.SubElement(parent, 'div')
                    chart.text = replacement
                    return True
                return False

            def process_plot(self, match):
                log_func("[Matplotlib Plot]Query:", match.groups())
                query = match.group(1)
                try:
                    result, success = safe_python_executor.safe_exec(query)
                    if not success:
                        return f"""<div class="alert alert-warning" role="alert">{result}</div>"""
                    return f'<img src="data:image/png;base64,{result}" style="display: block; margin: 0 auto;">'
                except:
                    log_func(f"[Matplotlib Plot]Error: {traceback.format_exc()}")
                    return """<div class="alert alert-warning" role="alert">No results</div>"""

        class TableExtension(Extension):
            def extendMarkdown(self, md):
                md.parser.blockprocessors.register(_MarkdownRenderer.TableProcessor(md.parser), 'table', 181)

        class TableProcessor(BlockProcessor):
            RE_TABLE = re.compile(r'^\s*\|(\s*[^|]+\s*\|)+\s*$')
            RE_SEPARATOR = re.compile(r'^\s*\|\s*:?---+:?\s*\|(?:\s*:?---+:?\s*\|)*\s*$')

            def test(self, parent, block):
                return bool(self.RE_TABLE.search(block))

            def run(self, parent, blocks):
                block = blocks.pop(0)
                rows = block.split('\n')
                table = ET.SubElement(parent, 'table', attrib={'class': 'table'})
                thead = ET.SubElement(table, 'thead')
                tbody = ET.SubElement(table, 'tbody')
                header = True
                for row in rows:
                    if self.RE_SEPARATOR.search(row):
                        header = False
                        continue
                    row_elem = ET.SubElement(thead if header else tbody, 'tr', attrib={'class': 'table-row'})
                    cells = [cell.strip() for cell in row.strip('|').split('|')]
                    for cell in cells:
                        cell_elem = ET.SubElement(row_elem, 'th' if header else 'td', attrib={'class': 'table-cell'})
                        # cell_elem.text = cell.strip()
                        # 这里可以进一步处理 Markdown 语法
                        html = convert_markdown_to_html(cell.strip())
                        cell_elem.text = html

    def convert_markdown_to_html(text):
        try:
            html_replacements.append([])
            text = text.encode("utf-8").decode("utf-8")
            # 使用占位符替换代码块
            CODE_BLOCK_RE = r'```.*?```|~~~.*?~~~'
            code_blocks = re.findall(CODE_BLOCK_RE, text, re.DOTALL)
            placeholders = {}
            for i, code_block in enumerate(code_blocks):
                placeholder = f"\x02{{CODE_BLOCK_{i}}}\x03"
                placeholders[placeholder] = code_block
                text = text.replace(code_block, placeholder)
            log_func("[Markdown Renderer]Text:", text)
            # 处理Matplot代码
            MATPLOT_RE = r'(?s)<matplotlib_plot>(.*?)</matplotlib_plot>'
            matplot_codes = re.findall(MATPLOT_RE, text)
            for i, code in enumerate(matplot_codes):
                placeholder = f"\x02{{MATPLOT_{i}}}\x03"
                log_func("[Markdown Renderer]Matplot:", code)
                image_data, success = safe_python_executor.safe_exec(code)
                if success:
                    image_base64 = base64.b64encode(image_data).decode()
                    result = f'![Matplot](data:image/png;base64,{image_base64})'
                    placeholders[placeholder] = result
                    text = text.replace(f"<matplotlib_plot>{code}</matplotlib_plot>", placeholder)

            # 处理Typst公式
            TYPST_RE = r'(?s)<typst>(.*?)</typst>'
            typst_formulas = re.findall(TYPST_RE, text)
            for i, formula in enumerate(typst_formulas):
                log_func("[Markdown Renderer]Typst:", formula)
                placeholder = f"\x02{{TYPST_{i}}}\x03"
                try:
                    image_data = typst_render.render(
                        "#set page(width: auto, height: auto, margin: (x: 10pt, y: 10pt))\n" + formula)
                except:
                    image_data = None
                if image_data is not None:
                    image_base64 = base64.b64encode(image_data).decode()
                    alt = "Typst Formula"
                    img_format = "png"
                    result = f'![Typst](data:image/png;base64,{image_base64})"'
                    placeholders[placeholder] = result
                    text = text.replace(f"<typst>{formula}</typst>", placeholder)

            LATEX_RE = r'(?s)((?<!\\)(\$\$).*?(?<!\\)(\$\$)|(?<!\\)\$.+?(?<!\\)\$|(?<!\\)<latex>.+?(?<!\\)</latex>)'
            # 优先处理LaTeX公式
            latex_formulas = re.findall(LATEX_RE, text, re.VERBOSE | re.MULTILINE)
            for formula__ in latex_formulas:
                if formula__[0].startswith("<latex>"):
                    formula = formula__[0][7:-8]
                else:
                    formula = formula__[0]
                log_func("[Markdown Renderer]Formula:", formula)
                formula_ = formula
                # formula = re.sub(r'[^\x20-\x7E]', '', formula)
                image_data = latex.get_formula_image_data(formula)
                if image_data is not None:
                    image_base64 = base64.b64encode(image_data, altchars=b'+/').decode()
                    if formula__[0].startswith("$$"):
                        # 多行公式
                        result = f"![LATEX](data:image/png;base64,{image_base64})\n"
                    elif formula__[0].startswith("$"):
                        # 单行公式
                        result = f"![@LATEX](data:image/png;base64,{image_base64})"
                    else:
                        # LaTeX标签
                        result = f"![LATEX](data:image/png;base64,{image_base64})"
                    text = text.replace(formula__[0], result)

            # 恢复代码块
            for placeholder, code_block in placeholders.items():
                text = text.replace(placeholder, code_block)

            md = markdown.Markdown(extensions=[
                "extra", "smarty", "toc", "tables", "attr_list",
                "def_list", "admonition", "meta", "nl2br", "sane_lists", "wikilinks",
                "fenced_code", "abbr", "footnotes", "md_in_html",
                _MarkdownRenderer.DelExtension(), _MarkdownRenderer.InsExtension(), _MarkdownRenderer.SubExtension(),
                _MarkdownRenderer.SupExtension(),
                _MarkdownRenderer.MarkExtension(), _MarkdownRenderer.UnderlineExtension(),
                _MarkdownRenderer.SmallExtension(), _MarkdownRenderer.TtExtension(),
                "markdown_checklist.extension", _MarkdownRenderer.ImgExtension(), _MarkdownRenderer.TableExtension(),
                _MarkdownRenderer.WolframAlphaExtension(), _MarkdownRenderer.PieChartExtension(),
                _MarkdownRenderer.FontExtension()
            ])
            md.set_output_format("html")
            html = md.convert(text)

            # 替换HTML中的占位符
            for i, (placeholder, replacement) in enumerate(html_replacements[-1]):
                html = html.replace(placeholder, replacement)
            html_replacements.pop()
            return html
        except Exception as e:
            log_func("[Markdown Renderer]Error:", str(e))
            return f"<div class='alert alert-danger' role='alert'>Error: {str(e)}</div>"

    async def render(text):
        log_func("[Markdown Renderer]Text:", text)

        def convert(text, queue):
            queue.put(convert_markdown_to_html(text))

        queue = Queue()
        convert_thread = threading.Thread(target=convert, args=(text, queue))
        convert_thread.start()
        while convert_thread.is_alive():
            await asyncio.sleep(0.1)
        convert_thread.join()
        html = queue.get()

        global_styles = """
        <style>
            body {
                font-family: 'Fira Code', sans-serif; /* 设置默认字体 */
                -webkit-font-smoothing: antialiased;
                font-smooth: always;
            }
            a {
                color: #32CD32; /* 设置超链接颜色 */
            }
            table {
                border-collapse: collapse;
                width: 100%;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
            }
            th {
                background-color: #f2f2f2;
                text-align: left;
            }
            tr:nth-child(even) {
                background-color: #f2f2f2;
            }
            .table {
                width: 100%;
                border-collapse: collapse;
            }
            .table-row {
                border-bottom: 1px solid #ddd;
            }
            .table-cell {
                padding: 8px;
            }
            pre {
                background-color: #f2f2f2;
                padding: 10px;
                border-radius: 5px;
                white-space: pre-wrap;       /* CSS3 */
                white-space: -moz-pre-wrap;  /* Firefox */
                white-space: -pre-wrap;      /* Opera <7 */
                white-space: -o-pre-wrap;    /* Opera 7 */
                word-wrap: break-word;       /* IE */
                overflow-x: auto;            /* Horizontal scroll */
                line-height: 1.25;
                font-size: 18px;
                font-family: 'Fira Code', monospace;
            }
            blockquote {
                border-left: 4px solid #ccc;
                padding-left: 16px;
                color: #666;
                margin: 0;
            }
            ul, ol {
                margin-left: 20px; /* 设置列表缩进 */
            }
            del {
                text-decoration: line-through;
            }
            ins {
                text-decoration: underline;
            }
            sub {
                vertical-align: sub;
                font-size: smaller;
            }
            sup {
                vertical-align: super;
                font-size: smaller;
            }
            mark {
                background-color: #ff0;
            }
            u {
                text-decoration: underline;
            }
            small {
                font-size: smaller;
            }
            tt {
                font-family: 'Fira Code', monospace;
            }
            img {
                max-width: 100%;
                height: auto;
            }
            .center {
                text-align: center;
            }
            .right {
                text-align: right;
            }
            .left {
                text-align: left;
            }
            .justify {
                text-align: justify;
            }
            code {
                background-color: #f2f2f2;
                padding: 2px 4px;
                border-radius: 3px;
            }
            alert {
                padding: 15px;
                margin-bottom: 20px;
                border: 1px solid transparent;
                border-radius: 4px;
            }
            alert-info {
                color: #31708f;
                background-color: #d9edf7;
                border-color: #bce8f1;
            }
            alert-warning {
                color: #8a6d3b;
                background-color: #fcf8e3;
                border-color: #faebcc;
            }
            alert-danger {
                color: #a94442;
                background-color: #f2dede;
                border-color: #ebccd1;
            }
            alert-success {
                color: #3c763d;
                background-color: #dff0d8;
                border-color: #d6e9c6;
            }
            pre code {
                background-color: #f2f2f2;
                border-radius: 5px;
            }
            pre code::before {
                content: '';
            }
            pre code::after {
                content: '';
            }
            pre code span {
                display: inline;
            }
            pre code span::before {
                content: '';
            }
            pre code span::after {
                content: '';
            }
            pre code span::selection {
                background-color: transparent;
            }
            pre code span::-moz-selection {
                background-color: transparent;
            }
            pre code span::-webkit-selection {
                background-color: transparent;
            }
            pre code span::-ms-selection {
                background-color: transparent;
            }
            pre code span::placeholder {
                color: transparent;
            }
            pre code span::-moz-placeholder {
                color: transparent;
            }
            pre code span::-webkit-placeholder {
                color: transparent; 
            }
            pre code span::-ms-placeholder {
                color: transparent;
            }
            details {
                display: block;
            }

            details > * {
                display: block;
            }

            details[open] {
                display: block;
            }

            details:not([open])::before {
                content: " ";
                display: block;
                height: 0;
            }            
            </style>
        """

        code_highlight = """<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.3.1/styles/default.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.3.1/highlight.min.js"></script>
    <script>hljs.highlightAll();</script>\n"""
        html = global_styles + code_highlight + "\n<body>" + html + "</body>"

        page = await browser.newPage()
        await page.setViewport({"width": 1024, "height": 1080})
        await page.setContent(html)
        # 获取最小包围盒的宽度和高度
        await page.waitForSelector('body')
        bounding_box = await page.evaluate('''
            () => {
                return new Promise((resolve) => {
                    // 等待字体加载完成
                    document.fonts.ready.then(() => {
                        const body = document.body;
                        const elements = body.querySelectorAll('*');
                        let minX = Infinity, minY = Infinity;
                        let maxX = -Infinity, maxY = -Infinity;

                        elements.forEach(element => {
                            // 确保元素完全渲染
                            const range = document.createRange();
                            range.selectNode(element);
                            const rect = range.getBoundingClientRect();
                            const style = window.getComputedStyle(element);
                            
                            // 获取所有边距值
                            const margins = {
                                left: parseFloat(style.marginLeft) || 0,
                                top: parseFloat(style.marginTop) || 0,
                                right: parseFloat(style.marginRight) || 0,
                                bottom: parseFloat(style.marginBottom) || 0
                            };
                            
                            const borders = {
                                left: parseFloat(style.borderLeftWidth) || 0,
                                top: parseFloat(style.borderTopWidth) || 0,
                                right: parseFloat(style.borderRightWidth) || 0,
                                bottom: parseFloat(style.borderBottomWidth) || 0
                            };
                            
                            const padding = {
                                left: parseFloat(style.paddingLeft) || 0,
                                top: parseFloat(style.paddingTop) || 0,
                                right: parseFloat(style.paddingRight) || 0,
                                bottom: parseFloat(style.paddingBottom) || 0
                            };

                            minX = Math.min(minX, rect.left - margins.left - borders.left - padding.left);
                            minY = Math.min(minY, rect.top - margins.top - borders.top - padding.top);
                            maxX = Math.max(maxX, rect.right + margins.right + borders.right + padding.right);
                            maxY = Math.max(maxY, rect.bottom + margins.bottom + borders.bottom + padding.bottom);
                        });

                        resolve({
                            width: Math.ceil(maxX - minX),
                            height: Math.ceil(maxY - minY)
                        });
                    });
                });
            }
        ''')
        width = bounding_box["width"]
        height = bounding_box["height"]
        log_func("[Markdown Renderer]Width:", width)
        log_func("[Markdown Renderer]Height:", height)
        await page.setViewport({"width": int(width) + 1, "height": int(height) + 1})
        # save image to variable
        await page.waitForSelector("body")
        img = await page.screenshot()
        await page.close()
        log_func("[Markdown Renderer]Image Size:", len(img))
        return img

    return render


async def __test__():
    browser = await setup_browser()
    markdown_text = """
🥵

 <typst>$ integral x^2 $</typst>

<latex>$\\int x^2 dx$</latex>

| Tables        | Are           | Cool  |
| ------------- |:-------------:| -----:|
| col 3 is      | right-aligned | 1600 |
| col 2 is      | centered      |   12 |
| zebra stripes | are neat      |    1 |

<font=Arial>Font Test\n</font>

<font=Times New Roman>Font Test\n</font>

<font=Comic Sans MS>Font Test\n</font>

<font=Georgia>Font Test\n</font>

# Heading 1

## Heading 2

### Heading 3

#### Heading 4

##### Heading 5

###### Heading 6

**Bold Text**

*Italic Text*

~~Strikethrough Text~~

++Underline Text++

<ins>Inserted Text</ins>

<sub>Subscript Text</sub>

<sup>Superscript Text</sup>

<mark>Marked Text</mark>

<u>Underline Text</u>

<small>Small Text</small>

"""

    img = await MarkdownRenderer(browser)(markdown_text)
    with open("output.png", "wb") as f:
        f.write(img)
    print("Markdown rendered to output.png")
    await browser.close()
