import os
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Header
from services.search.serper import get_search_results
from services.document.store import store_results
from services.document.query import query_results
from services.web import batch_fetch_urls
from utils.resp import resp_err, resp_data

import requests
import re
import json

from services.qwen.res_qwen import save_text_as_unique_file,get_model_response


rag_router = APIRouter()


class RagSearchReq(BaseModel):
    query: str
    locale: Optional[str] = ''
    search_n: Optional[int] = 10
    search_provider: Optional[str] = 'google'
    is_reranking: Optional[bool] = False
    is_detail: Optional[bool] = False
    detail_top_k: Optional[int] = 10
    detail_min_score: Optional[float] = 0.00
    is_filter: Optional[bool] = False
    filter_min_score: Optional[float] = 0.00
    filter_top_k: Optional[int] = 10


@rag_router.post("/google-search")
async def rag_search(req: RagSearchReq, authorization: str = Header(None)):
    authApiKey = os.getenv("AUTH_API_KEY")
    apiKey = ""
    if authorization:
        apiKey = authorization.replace("Bearer ", "")
    if apiKey != authApiKey:# 鉴权
        return resp_err("Access Denied")

    if req.query == "": # 是否有查询关键词
        return resp_err("invalid params")

    search_results = []
    # 1. get search results
    try:
        search_results = search(req.query, req.search_n, req.locale)
        search_results = await fetch_details(search_results, req.detail_min_score, req.detail_top_k)

        url_list = [i['link'] for i in search_results] # 记录已经爬取过 content 的 url
        search_results_list = [i for i in search_results if len(i['content']) > len(i['snippet'])]
        target_times = req.search_n # 目标次数（含有 content 的）
        search_times = req.search_n # 实际搜索次数,初始设定为目标次数
        cycle_times = 0   # 记录循环次数 
        while (len(search_results_list) < target_times) and (cycle_times < 5): # 若含content 不满 10 条，且限制最高只循环 5 次
            # search_results_list.append([1])
            search_times += 5
            req.search_n = search_times
            s = search(req.query, req.search_n, req.locale)
            added_url_list = [i['link'] for i in s if i['link'] not in url_list] # 不在 url_list 中的，继续获取 content

            s = [i for i in s if i['link'] in added_url_list] # 从返回的检索结果中抽取 added_url_list

            url_list+=added_url_list # 更新下url_list
 
            s = await fetch_details(s, req.detail_min_score, req.detail_top_k) # 重新拉取后续的content
            # print(s)
            for i in s:
                if ('content' in i) and (len(i['content'])>len(i['snippet'])) and (len(search_results_list)<target_times):
                    search_results_list.append(i)
            cycle_times += 1
        search_results = search_results_list
        return resp_data({
                            "query":req.query,
                            "topN":req.filter_top_k,
                            "search_results": search_results,
                        })
    except Exception as e:
        return resp_err(f"get search results failed: {e}")


class SearchResults(BaseModel):
    query:str
    topN:int
    search_results:list

@rag_router.post("/reranking")
async def reranking_research(search_results:SearchResults):
        # 2. reranking
        # if req.is_reranking:
        try:
            results_to_rerank = search_results.search_results
            reranked_results = reranking(results_to_rerank, search_results.query)

            # 取 topN
            
            reranked_results = reranked_results[:search_results.topN]
            return resp_data({
                                 "query":search_results.query,
                                 "search_results": reranked_results,
                             })
        except Exception as e:
            print(f"reranking search results failed: {e}")


class PageContent(BaseModel):
    query:str
    content:str

@rag_router.post("/summary_content")
async def summary_content(page_content:PageContent):
    question = page_content.query
    content = page_content.content
    filename = save_text_as_unique_file(text=content)
    prompt = f"""
    这是用户的搜索问题：{question}

    您是一款专业的信息筛选处理专家，擅长信息提取、数据整合、格式化输出。
    给您的是关于上述用户搜索问题的网页搜索结果，您的目标是从提供的网页内容中去除不相关信息，提炼出与用户搜索问题直接相关的信息，以帮助用户获取搜索结果或者问题答案。
    需要注意,确保只提取与用户搜索问题直接相关的信息，忽略不相关或次要的细节,如果有关键的数字信息和日期信息请详细保留。
    您需要严格按照以下步骤WorkFlow:
    * WorkFlow
    	1. 仔细阅读并理解用户的搜索问题。
    	2. 仔细阅读并分析提供的相关网页搜索结果，识别与搜索问题相关的关键词和信息。
    	3. 去除网页内容中与用户搜索问题无关的部分。
    	4. 总结出关键信息,严格按照以下markdown格式的模板整理并输出信息:
            ****************************
            搜索问题：[用户的搜索问题]
            相关背景：[简要介绍搜索词的主题和背景,如果有涉及事件的发生日期请带上,并引出下文相关内容，注意对输出内容进行润色]
            	1.	[信息点1总结]：信息点 1 详细内容。
            	2.	[信息点2总结]：信息点 2 详细内容。
            	3.  [信息点3总结]：信息点 3 详细内容。
                4.  [信息点4总结]：信息点 4 详细内容
                。。。
            总结：[对网页信息进行简短总结]
            ****************************
    """
    res = get_model_response(prompt=prompt
                            ,file_name=filename
                            ,model_name='qwen-long'
                            )
    
    if os.path.exists(filename):
        os.remove(filename)

    return res

class FliterResults(BaseModel):
    query:str
    search_results:list

@rag_router.post("/filter")  # 暂时没啥用
async def filter_research(filter_results:FliterResults):
        # 4. filter content
        try:
            filtered_results = filter_content(filter_results.search_results
                                            , filter_results.query
                                            , 0
                                            , 10)
            # return {"1":"sssssssss"}

            return resp_data({
                             "search_results": filtered_results,
                             })
        except Exception as e:
            print(f"filter content failed: {e}")

class SearchStr(BaseModel):
    code:int
    message:str
    data:dict


@rag_router.post("/handle_search")
async def handle_search(search_str:SearchStr):
    return search_str.data

@rag_router.post("/handle_json") # 有问题
def handle_json(json_str: str):
    json_str = re.sub(r"```(?:json|JSON)*([\s\S]*?)```", r"\1", json_str).strip()
    json_str = re.sub(r'\\"', '"',  json_str).strip()
    return json.loads(json_str)

@rag_router.post("/merge_text")
async def merge_text(topn_json:SearchStr):
    all_content_list = [i['content'] for i in topn_json.data['search_results']]
    all_content = '\n'.join(all_content_list)
    return all_content

def search(query, num, locale=''):
    params = {
        "q": query, # 查询关键字
        "num": num  # 查询条数
    }

    if locale:
        params["hl"] = locale

    try: 
        search_results = get_search_results(params=params)

        return search_results
    except Exception as e:
        print(f"search failed: {e}")
        raise e


def reranking(search_results, query):
    try:
        # documents = [i['snippet'] for i in search_results]
        documents = [i['content'] for i in search_results]
        # reranking_dict = {"model": "rerank-english-v3.0"
        #                   ,"query": query
        #                   ,"top_n": 11
        #                   ,"documents": documents
        #                   }
        reranking_dict = {"model": "rerank-multilingual-v3.0"
                          ,"query": query
                          ,"top_n": 11
                          ,"documents": documents
                          } 
        # cohere rerank-multilingual-v3.0
        # url = "http://38.54.107.72:8031/v1/rerank"
        # bge
        url = "http://lyg.blockelite.cn:11588/rank_by_bge"

        headers = {
            "Content-Type": "application/json",
            "Authorization": "bearer TRuIrCx5xgd6le9MhHHYx3BVDLaeouY87bpD0tbS"
        }
        reranking_response = requests.post(url, headers=headers, json=reranking_dict)
        rerank_result = reranking_response.json()

        # return rerank_result
        rerank_sorted = sorted(rerank_result['results'],key=lambda x:x['index'])
        # 匹配reranking分数
        for v in rerank_sorted:
            search_results[v['index']]['score'] = v['relevance_score']
        # 按 reranking 分数重排序
        sorted_search_results = sorted(search_results,key=lambda x:x['score'],reverse=True)
    
        return sorted_search_results
    
    except Exception as e:
        print(f"reranking search results failed: {e}")
        raise e



    # rerank_sorted = sorted(rerank_result['results'],key=lambda x:x['index'])
    # # 匹配reranking分数
    # for v in rerank_sorted:
    #     search_results[v['index']]['score'] = v['relevance_score']
    # # 按 reranking 分数重排序
    # sorted_search_results = sorted(search_results,key=lambda x:x['score'],reverse=True)

    # return sorted_search_results
 

async def fetch_details(search_results, min_score=0.00, top_k=6):
    urls = []
    for res in search_results:
        if len(urls) > top_k:
            break
        if res["score"] >= min_score:
            urls.append(res["link"])

    try:
        details = await batch_fetch_urls(urls)
    except Exception as e:
        print(f"fetch details failed: {e}")
        raise e

    content_maps = {}
    for url, content in details:
        content_maps[url] = content

    for result in search_results:
        if result["link"] in content_maps:
            result["content"] = content_maps[result["link"]]

    return search_results


def filter_content(search_results, query, filter_min_score=0.8, filter_top_k=10):
    try:
        results_with_content = []
        for result in search_results:
            if "content" in result and len(result["content"]) > len(result["snippet"]):
                results_with_content.append(result)

        index = store_results(results=results_with_content)
        match_results = query_results(index, query, filter_min_score, filter_top_k)

    except Exception as e:
        print(f"filter content failed: {e}")
        raise e

    content_maps = {}
    for result in match_results:
        if result["uuid"] not in content_maps:
            content_maps[result["uuid"]] = ""
        else:
            content_maps[result["uuid"]] += result["content"]

    for result in search_results:
        if result["uuid"] in content_maps:
            result["content"] = content_maps[result["uuid"]]

    return search_results
