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
        search_times = req.search_n # 实际搜索次数
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
                            "search_results": search_results,
                        })
    except Exception as e:
        return resp_err(f"get search results failed: {e}")

 
class SearchResults(BaseModel):
    query:str
    search_results:list 
 
@rag_router.post("/reranking")
async def reranking_research(search_results:SearchResults):
        # 2. reranking
        # if req.is_reranking:
        try:
            results_to_rerank = search_results.search_results
            reranked_results = reranking(results_to_rerank, search_results.query)
            return resp_data({
                                 "query":search_results.query,
                                 "search_results": reranked_results,
                             })
        except Exception as e:
            print(f"reranking search results failed: {e}")

class FliterResults(BaseModel):
    query:str
    search_results:list

@rag_router.post("/filter")
async def filter_research(filter_results:FliterResults):
        # 4. filter content
        try:
            filtered_results = filter_content(filter_results.search_results
                                            , filter_results.query
                                            , 0
                                            , 10)
            return {"1":"sssssssss"}

            return resp_data({
                             "search_results": filtered_results,
                             })
        except Exception as e:
            print(f"filter content failed: {e}")


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


# def reranking(search_results, query):
#     try:
#         index = store_results(results=search_results)
#         match_results = query_results(index, query, 0.00, len(search_results))
#     except Exception as e:
#         print(f"reranking search results failed: {e}")
#         raise e

#     score_maps = {}
#     for result in match_results:
#         score_maps[result["uuid"]] = result["score"]

#     for result in search_results:
#         if result["uuid"] in score_maps:
#             result["score"] = score_maps[result["uuid"]]

#     sorted_search_results = sorted(search_results,
#                                    key=lambda x: (x['score']),
#                                    reverse=True)

#     return sorted_search_results

def reranking(search_results, query):
    try:
        documents = [i['snippet'] for i in search_results]
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
