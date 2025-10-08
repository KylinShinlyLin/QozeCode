from langchain_core.tools import tool
from tavily import AsyncTavilyClient

# 初始化 Tavily 客户端
tavily_client = AsyncTavilyClient(api_key="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")


@tool
async def tavily_search(query: str, max_results: int = 5) -> str:
    """Search the internet using Tavily API to provide real-time information for AI models.
    
    This method searches the internet for up-to-date information, then provides the search 
    results to AI models for analysis and summarization, ultimately generating structured 
    conclusions and insights.
    
    Args:
        query: The search query string
        max_results: Maximum number of search results to return (default: 5)
    
    Returns:
        Formatted search results with titles, URLs, and content snippets for further AI analysis
    """
    try:
        print(f"\n🔍 正在搜索: {query}")

        # 使用 Tavily 进行搜索
        response = await tavily_client.search(
            query=query,
            max_results=max_results,
            include_answer=True,
            include_raw_content=False
        )

        # 格式化搜索结果
        results = []

        # 添加 Tavily 的答案摘要（如果有）
        if response.get('answer'):
            results.append(f"📝 摘要答案: {response['answer']}\n")

        # 添加搜索结果
        if response.get('results'):
            results.append("🔍 搜索结果:")
            for i, result in enumerate(response['results'], 1):
                title = result.get('title', '无标题')
                url = result.get('url', '无链接')
                content = result.get('content', '无内容')

                # # 限制内容长度
                # if len(content) > 300:
                #     content = content[:300] + "..."

                results.append(f"\n{i}. **{title}**")
                results.append(f"   🔗 {url}")
                results.append(f"   📄 {content}")

        formatted_results = "\n".join(results)
        print(f"✅ 搜索完成，找到 {len(response.get('results', []))} 个结果")

        return formatted_results

    except Exception as e:
        error_msg = f"❌ Tavily 搜索失败: {str(e)}"
        print(error_msg)
        return error_msg