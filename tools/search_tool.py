import httpx
from langchain_core.tools import tool
from rich.progress import Progress, TimeElapsedColumn, TextColumn, SpinnerColumn
from tavily import AsyncTavilyClient

import config_manager
from shared_console import console

# 初始化 Tavily 客户端
tavily_client = AsyncTavilyClient(api_key=config_manager.get_tavily_key())

# 定义颜色常量
CYAN = "\033[36m"
RESET = "\033[0m"


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
        # print(f"\n🔍 正在搜索: {query}")
        with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                transient=False
        ) as progress:
            task = progress.add_task(f"[bold dim cyan]正在搜索: {query} [/bold dim cyan]",
                                     total=None)
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
            progress.update(task,
                            description=f"[bold green]✓[/bold green] [bold dim cyan] 搜索完成:找到 {len(response.get('results', []))} 个结果 [/bold dim cyan]")

            return formatted_results

    except Exception as e:
        error_msg = f"❌ Tavily 搜索失败: {str(e)}"
        print(error_msg)
        return error_msg


@tool
async def read_url(url: str) -> str:
    """Visit and read url webpage and convert its content to Markdown
    
    This tool uses to fetch webpage content and convert it directly to clean Markdown format.
    - This tool is well-suited for reading URL documents or URL literature.
    
    Args:
        url: The URL of the webpage to parse (must be a valid, accessible URL)
    
    Returns:
        The webpage content converted to Markdown format by Jina Reader API,
        or an error message if the API call fails
    """
    try:

        # 构建 Jina Reader API 请求URL
        api_url = f"https://r.jina.ai/{url}"

        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }

        with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                transient=False
        ) as progress:
            task = progress.add_task(
                f"[bold dim cyan]访问页面: {url[:66]}{'...' if len(url) > 66 else ''}[/bold dim cyan]", total=None)
            # 调用 Jina Reader API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(api_url, headers=headers, follow_redirects=True)

                # 检查响应状态
                if response.status_code == 200:
                    markdown_content = response.text

                    # 限制输出长度（避免token过多）
                    max_length = 8000
                    if len(markdown_content) > max_length:
                        markdown_content = markdown_content[:max_length] + "\n\n... (内容过长，已截断)"

                    # 添加来源信息
                    result = f"# 网页内容解析\n\n**来源URL**: {url}\n\n---\n\n{markdown_content}"

                    progress.update(task,
                                    description=f"[bold green]✓[/bold green] [bold dim cyan] 阅读完成: {url[:66]}{'...' if len(url) > 66 else ''}[/bold dim cyan]")
                    return result
                else:
                    error_msg = f"❌ Jina Reader API 返回错误: {response.status_code} - {response.text}"
                    progress.update(task,
                                    description=f"[bold red]✗ 阅读失败: {url[:66]}{'...' if len(url) > 66 else ''}{RESET}")
                    return error_msg

    except httpx.RequestError as e:
        error_msg = f"❌ 网络请求失败: {str(e)}"
        print(error_msg)
        return error_msg
    except httpx.HTTPStatusError as e:
        error_msg = f"❌ HTTP错误: {e.response.status_code} - {str(e)}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ 网页解析失败: {str(e)}"
        print(error_msg)
        return error_msg
