import html2text
import asyncio
import aiohttp
import re
from openai import OpenAI
from pathlib import Path
import os
import html2text
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
        # """ 以下为新增 """
        # 去除空白符号
        markdown = await clean_chinese_text(markdown)
        # # 存为 txt 文件（uuid+timestame）
        # f_name = await save_text_as_unique_file(markdown)
        # # 提示词
        # prompt = """
        # 您是一款专业的文本摘要专家，擅长语言理解、识别和提炼文本中的主要观点、关键信息摘要总结,需要注意,你必须保留关键的数字信息。
        # 请仔细阅读这篇文章，并将其精炼为一段格式化的摘要。
        # 您的目标是提炼出文本的核心要点，并按照以下格式输出，以帮助用户快速理解讨论的主要内容，无需阅读整篇文章。
        # 摘要需要保持客观性，避免添加主观解释或总结,请避免包含不必要的细节或偏离主题的信息：

        # 【主要内容】
        # - 简要描述文本的主题或核心议题。

        # 【关键点】
        # - 列出文本中的第一个关键内容或重要信息,保留关键数字信息。
        # - 列出文本中的第二个关键内容或重要信息,保留关键数字信息。
        # - 依此类推，列出其他关键点。
        # 仅提供输出内容，不要使用引号包裹回答。请用中文回应。"""
        # # 对网页信息抽取，总结
        # markdown = await get_model_response(prompt=prompt
        #                                    ,file_name=f_name
        #                                    ,model_name='qwen-long'
        #                                    )
        # # 删除 txt 文件
        # if os.path.exists(f_name):
        #     os.remove(f_name)
        
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


async def get_model_response(prompt,file_name,model_name='qwen-long'):
    if model_name=='qwen-long':
        client = OpenAI(
                        api_key="sk-8acaedb4b50d4a478221c2020969ee81",  # 替换成真实DashScope的API_KEY
                        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 填写DashScope服务endpoint
                       )
        file = client.files.create(file=Path(file_name), purpose="file-extract")
        completion = client.chat.completions.create(
            model="qwen-long",
            messages=[
                {
                    'role': 'system',
                    'content': f'fileid://{file.id}'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            stream=False
        )
        # 用完删除文件
        client.files.delete(file.id)
        
        return completion.choices[0].message.content
    
    elif model_name=='hunyuan-lite':
        pass
    else:
        pass

async def save_text_as_unique_file(text):
    # 生成UUID
    unique_id = uuid.uuid4()
    # 获取当前时间戳，精确到纳秒
    timestamp = time.strftime("%Y%m%d%H%M%S", time.localtime())
    # 创建文件名，格式为：文本摘要_时间戳_UUID.txt
    filename = f"./file/temp_txt_{timestamp}_{unique_id}.txt"
    
    # 将文本内容写入文件
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(text)
    
    return filename