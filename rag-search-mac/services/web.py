import html2text
import asyncio
import aiohttp
import re

import uuid
import time



async def fetch_url(session, url):
    async with session.get(url) as response:
        try:
            response.raise_for_status()
            response.encoding = 'utf-8'
            html = await response.text()

            return html
        except Exception as e:
            print(f"fetch url failed: {url}: {e}")
            return ""


async def html_to_markdown(html):
    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True

        markdown = h.handle(html)

        # 新增
        markdown = await clean_chinese_text(markdown)

        return markdown
    except Exception as e:
        print(f"html to markdown failed: {e}")
        return ""


async def fetch_markdown(session, url):
    try:
        html = await fetch_url(session, url)
        markdown = await html_to_markdown(html)
        markdown = re.sub(r'\n{2,n}', '\n', markdown)

        return url, markdown
    except Exception as e:
        print(f"fetch markdown failed: {url}: {e}")
        return url, ""


async def batch_fetch_urls(urls):
    print("urls", urls)
    try:
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_markdown(session, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            return results
    except aiohttp.ClientResponseError as e:
        print(f"batch fetch urls failed: {e}")
        return []


async def clean_chinese_text(text):
    # 去除文本中的所有非中文字符、数字和标点符号
    # cleaned_text = re.sub(r'[^\u4e00-\u9fa5\w\s,.!?;:]', '', text)
    
    # 转换为全角字符，以统一中文标点符号
    cleaned_text = re.sub(r'[，。！？；：]', lambda x: {
        '，': '，',
        '。': '。',
        '！': '！',
        '？': '？',
        '；': '；',
        '：': '：'
    }[x.group()], text)
    
    # 去除文本中的所有空白符（包括换行符）
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    # 去除字符串首尾的空白符
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text





async def save_text_as_unique_file(text):
    # 生成UUID
    unique_id = uuid.uuid4()
    # 获取当前时间戳，精确到纳秒
    timestamp = time.strftime("%Y%m%d%H%M%S", time.localtime())
    # 创建文件名，格式为：文本摘要_时间戳_UUID.txt
    filename = f"text_summary_{timestamp}_{unique_id}.txt"
    
    # 将文本内容写入文件
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(text)
    
    return filename