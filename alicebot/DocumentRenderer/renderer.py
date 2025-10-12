import traceback
import asyncio
import sys
from bs4 import BeautifulSoup
import tiktoken
import random
import pathlib
from typing import Callable, Any

log_func: Callable[[Any], None]

project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent), log_func=log_func)
wolfram_alpha = package.load_module("wolfram_alpha", log_func=log_func)
typst_render = package.load_module("typst_render", log_func=log_func)
safe_python_executor = package.load_module("safe_python_executor", log_func=log_func)

async def bing_search(browser, query: str, max_results: int = 3):
    page = None
    try:
        page = await browser.newPage()
        log_func('INFO', 'WebSearch', "Searching Bing for:", query)
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
        log_func('INFO', 'WebSearch', "Navigating to Bing")
        try:
            response = await page.goto('https://www.bing.com/',
                                       waitUntil=['networkidle0'])
            if not response.ok:
                raise Exception(f"Failed to load Bing: {response.status}")
        except Exception as e:
            log_func('ERROR', 'WebSearch', f"Navigation error: {e}")
            return [{"title": "Navigation failed", "url": "", "content": str(e)}]
        log_func('INFO', 'WebSearch', "Searching for:", query)
        search_selector = '#sb_form_q'
        await page.waitForSelector(search_selector, {'timeout': 10000})
        await page.type(search_selector, query, {'delay': random.randint(5, 7)})
        await asyncio.sleep(random.uniform(0.5, 1))

        await page.keyboard.press('Enter')
        await page.waitForNavigation({'waitUntil': 'networkidle0'})
        log_func('INFO', 'WebSearch', "Waiting for search results")
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
        log_func('INFO', 'WebSearch', "Results:", results)
        await page.close()

        if not results:
            return ["No results found"]

        return results[:max_results]

    except Exception as e:
        log_func('ERROR', 'WebSearch', f"Error: {str(e)}")
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
        log_func('INFO', 'WebSearch', "Text:", text)
        log_func('INFO', 'WebSearch', "Token Size:", size)
        await page.close()
        return {"text": text, "size": size}
    except Exception as e:
        log_func('ERROR', 'WebSearch', traceback.format_exc())
        return {"text": "ERROR", "size": 0}


def MarkdownRenderer(browser):
    def convert_markdown_to_html(text):
        """简单的Markdown到HTML转换占位函数,实际渲染在浏览器端完成"""
        return text
    
    async def render(text):
        log_func('INFO', 'MarkdownRenderer', "Text:", text)
        
        # 转义JavaScript字符串中的特殊字符
        text_escaped = text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
        
        # 构建HTML - 使用浏览器端渲染
        html_parts = [
            '<!DOCTYPE html>',
            '<html>',
            '<head>',
            '    <meta charset="UTF-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '    <script src="https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js"></script>',
            '    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">',
            '    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>',
            '    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>',
            '    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">',
            '    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>',
            '    <style>',
            '        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; color: #24292f; background: #fff; margin: 20px; padding: 20px; overflow: hidden; }',
            '        html { overflow: hidden; }',
            '        * { scrollbar-width: none; -ms-overflow-style: none; }',
            '        *::-webkit-scrollbar { display: none; }',
            '        h1, h2, h3, h4, h5, h6 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }',
            '        h1 { font-size: 2em; padding-bottom: 0.3em; border-bottom: 1px solid #eaecef; }',
            '        h2 { font-size: 1.5em; padding-bottom: 0.3em; border-bottom: 1px solid #eaecef; }',
            '        h3 { font-size: 1.25em; }',
            '        a { color: #0969da; text-decoration: none; }',
            '        a:hover { text-decoration: underline; }',
            '        table { border-collapse: collapse; margin: 16px 0; width: 100%; }',
            '        th, td { padding: 6px 13px; border: 1px solid #d0d7de; }',
            '        th { font-weight: 600; background: #f6f8fa; }',
            '        tr:nth-child(2n) { background: #f6f8fa; }',
            '        pre { padding: 16px; overflow: hidden; font-size: 85%; background: #f6f8fa; border-radius: 6px; margin: 16px 0; }',
            '        code { padding: 0.2em 0.4em; font-size: 85%; background: rgba(175,184,193,0.2); border-radius: 6px; }',
            '        pre code { padding: 0; background: transparent; }',
            '        blockquote { padding: 0 1em; color: #57606a; border-left: 0.25em solid #d0d7de; margin: 16px 0; }',
            '        ul, ol { padding-left: 2em; margin: 16px 0; }',
            '        img { max-width: 100%; height: auto; margin: 16px 0; }',
            '        .katex { font-size: 1.1em; }',
            '        .katex-display { margin: 1em 0; text-align: center; }',
            '        del { text-decoration: line-through; }',
            '        mark { background: #fff8c5; }',
            '        input[type="checkbox"] { margin-right: 0.5em; }',
            '    </style>',
            '</head>',
            '<body>',
            '    <div id="content"></div>',
            '    <script>',
            '        marked.setOptions({ breaks: true, gfm: true, highlight: function(code, lang) { if (lang && hljs.getLanguage(lang)) { try { return hljs.highlight(code, { language: lang }).value; } catch(e) {} } return hljs.highlightAuto(code).value; } });',
            '        const markdownText = `' + text_escaped + '`;',
            '        const htmlContent = marked.parse(markdownText);',
            '        document.getElementById("content").innerHTML = htmlContent;',
            '        renderMathInElement(document.body, { delimiters: [{ left: "$$", right: "$$", display: true }, { left: "$", right: "$", display: false }], throwOnError: false });',
            '        document.body.setAttribute("data-rendered", "true");',
            '    </script>',
            '</body>',
            '</html>'
        ]
        
        html = '\n'.join(html_parts)
        
        page = await browser.newPage()
        await page.setViewport({"width": 1024, "height": 1080})
        await page.setContent(html)
        
        # 等待渲染完成
        await page.waitForSelector('body[data-rendered="true"]', {'timeout': 10000})
        await asyncio.sleep(0.5)
        
        # 获取内容边界框 - 精确收缩到实际内容
        bounding_box = await page.evaluate('''
            () => {
                return new Promise((resolve) => {
                    document.fonts.ready.then(() => {
                        // 只计算content div内的实际内容
                        const content = document.getElementById('content');
                        if (!content) {
                            resolve({ width: 1024, height: 1080 });
                            return;
                        }
                        
                        // 获取所有有实际内容的元素
                        const elements = content.querySelectorAll('*');
                        let minX = Infinity, minY = Infinity;
                        let maxX = -Infinity, maxY = -Infinity;
                        
                        elements.forEach(element => {
                            // 跳过空元素
                            if (element.offsetWidth === 0 || element.offsetHeight === 0) return;
                            
                            const rect = element.getBoundingClientRect();
                            
                            // 只计算实际占用的空间,不包含margin
                            minX = Math.min(minX, rect.left);
                            minY = Math.min(minY, rect.top);
                            maxX = Math.max(maxX, rect.right);
                            maxY = Math.max(maxY, rect.bottom);
                        });
                        
                        // 检查content本身的边界
                        const contentRect = content.getBoundingClientRect();
                        minX = Math.min(minX, contentRect.left);
                        minY = Math.min(minY, contentRect.top);
                        maxX = Math.max(maxX, contentRect.right);
                        maxY = Math.max(maxY, contentRect.bottom);
                        
                        // 如果没有找到有效元素,使用content的大小
                        if (!isFinite(minX)) {
                            resolve({ 
                                width: Math.ceil(contentRect.width) + 40, 
                                height: Math.ceil(contentRect.height) + 40 
                            });
                            return;
                        }
                        
                        // 计算实际内容宽高,添加body的padding(40px)
                        const width = Math.ceil(maxX - minX) + 40;
                        const height = Math.ceil(maxY - minY) + 40;
                        
                        resolve({ width, height });
                    });
                });
            }
        ''')
        
        width = bounding_box["width"]
        height = bounding_box["height"]
        log_func('INFO', 'MarkdownRenderer', f"Width: {width}, Height: {height}")
        
        # 设置适配的视口大小并截图(+1避免边缘裁切)
        await page.setViewport({"width": int(width) + 1, "height": int(height) + 1})
        img = await page.screenshot({"fullPage": False})
        await page.close()
        
        log_func('INFO', 'MarkdownRenderer', f"Image Size: {len(img)}")
        return img

    return render
