import httpx
import requests
from mcp.server.fastmcp import FastMCP

import asyncio
from loguru import logger

from ddgs import DDGS


mcp = FastMCP("SearchService",host="0.0.0.0",port=8003)


# headers = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# }

@mcp.tool()
async def web_search(query:str):
    """
    快速搜索15个摘要文件，内含标题、链接和摘要
    """
    try:
        logger.info(f'🔍 [Async] 正在搜索: {query}')
        # 确保时效性:最近一个月 | 后续更新可以自由选择需要的时间段

        # 【核心逻辑】使用同步的 DDGS，但用 to_thread 包装成异步
        # 理由：DDGS 官方库变动频繁，AsyncDDGS 可能不存在，而 to_thread 是 Python 标准库，永远稳定。
        def _sync_search():
            # max_results 建议 10-15
            # timelimit="y" (过去一年)
            return list(DDGS().text(query, max_results=15, timelimit="y"))

        # 扔到线程池跑，不阻塞主线程
        results = await asyncio.to_thread(_sync_search)

        if not results:
            return "未找到相关结果，请尝试更换关键词。"

        search_results = []
        for i,r in enumerate(results):
            content = f"结果 [{i}]\n标题: {r['title']}\n链接: {r['href']}\n摘要: {r['body']}\n"
            search_results.append(content)
        return "\n---\n".join(search_results)
    except Exception as e:
        logger.error(f"搜索服务出错: {e}")
        return f'搜索服务暂时不可用: {str(e)}'

@mcp.tool()
async def get_page_content(url:str):
    """
    获取单个url里的全文信息
    """
    logger.info(f'⚡ [Async] 正在抓取: {url}')
    real_url = f"https://r.jina.ai/{url}"

    async with httpx.AsyncClient(timeout=30.0,follow_redirects=True) as client: # 自动跟随重定向
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = await client.get(real_url,headers=headers)
            result = response.text
            return result
        except httpx.TimeoutException as e:
            return "Error:请求超时，网页响应太慢"
        except Exception as e:
            return f"Error:抓取时发生未知错误:{str(e)}"

@mcp.tool()
async def batch_fetch(urls:list[str]):
    """
    批量获取url里的全文信息(并行)
    如果是批量获取，优先使用该工具
    """
    print(f'正在批量获取{len(urls)}个URL的全文信息...')
    tasks = [get_page_content(url) for url in urls]
    contents = await asyncio.gather(*tasks)
    # 这里返回必须是str，不然工具返回接收可能因为看到的不是str而报错
    return "\n\n=== 文章分隔线 ===\n\n".join(contents)



if __name__ == '__main__':
    mcp.run("streamable-http")
    # mcp.run()