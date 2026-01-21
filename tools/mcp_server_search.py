import requests
from mcp.server.fastmcp import FastMCP
from ddgs import DDGS
import asyncio
from loguru import logger

mcp = FastMCP("SearchService",host="0.0.0.0",port=8002)


# headers = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# }

@mcp.tool()
async def web_search(query:str):
    """
    快速搜索15个摘要文件，内含标题、链接和摘要
    """
    try:
        logger.info('正在搜索...')
        # 确保时效性:最近一个月 | 后续更新可以自由选择需要的时间段
        results = DDGS().text(query,max_results=15,timelimit="m")
        if not results:
            return "未找到相关结果，请尝试更换关键词。"

        search_results = []
        for i,r in enumerate(results):
            content = f"结果 [{i}]\n标题: {r['title']}\n链接: {r['href']}\n摘要: {r['body']}\n"
            search_results.append(content)
        return "\n---\n".join(search_results)
    except Exception as e:
        return f'搜索服务暂不可用:{str(e)}'

@mcp.tool()
async def get_page_content(url:str):
    """
    获取单个url里的全文信息
    """
    logger.info(f'正在抓取{url}')
    try:
        real_url = f"https://r.jina.ai/{url}"
        response = requests.get(real_url)
        result = response.text
        return result
    except requests.exceptions.Timeout as e:
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
    return contents



if __name__ == '__main__':
    mcp.run("streamable-http")