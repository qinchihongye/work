from openai import OpenAI
from pathlib import Path
import uuid
import time


def get_model_response(prompt,file_name,model_name='qwen-long'):
    if model_name=='qwen-long':
        # 原 qwen
        client = OpenAI(
                        api_key="sk-8acaedb4b50d4a478221c2020969ee81",  # 替换成真实DashScope的API_KEY
                        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 填写DashScope服务endpoint
                       )
        # # 阿里云上one-api
        # client = OpenAI(
        #                 api_key="sk-vXnBgjiDte15VTKQ128469D3967149Aa8aC56d3dD3927736",  # 替换成真实DashScope的API_KEY
        #                 base_url="http://121.41.60.137:8025/v1",  # 填写DashScope服务endpoint
        #                 )
        
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

def save_text_as_unique_file(text):
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