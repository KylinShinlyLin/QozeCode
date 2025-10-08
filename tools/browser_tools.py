# from typing import Optional, List
#
# import nest_asyncio
# from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
# from langchain_community.tools.playwright.utils import create_async_playwright_browser
# from langchain_core.tools import tool
#
# from shared_console import console
#
# # 应用 nest_asyncio 以支持在 Jupyter 等环境中运行
# nest_asyncio.apply()
#
# # 全局浏览器实例
# _browser = None
# _toolkit = None
# _tools_cache = None
#
#
# async def get_browser_toolkit():
#     """获取或创建浏览器工具包"""
#     global _browser, _toolkit, _tools_cache
#
#     if _toolkit is None:
#         try:
#             console.print("🌐 正在初始化浏览器工具包...", style="cyan")
#             _browser = create_async_playwright_browser(headless=False)
#             _toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=_browser)
#             _tools_cache = _toolkit.get_tools()
#             console.print("✅ 浏览器工具包初始化成功", style="green")
#         except Exception as e:
#             console.print(f"❌ 浏览器工具包初始化失败: {str(e)}", style="red")
#             console.print("💡 请确保已安装 playwright: pip install playwright", style="yellow")
#             console.print("💡 并运行: playwright install", style="yellow")
#             raise
#
#     return _toolkit, _tools_cache
#
#
# @tool
# async def navigate_browser(url: str) -> str:
#     """导航到指定的URL
#
#     Args:
#         url: 要访问的网页URL (例如: "https://www.google.com")
#
#     Returns:
#         导航结果信息
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         navigate_tool = tools_by_name["navigate_browser"]
#
#         result = await navigate_tool.arun({"url": url})
#         console.print(f"🌐 已导航到: {url}", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"导航失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def click_element(selector: str) -> str:
#     """点击页面上的元素
#
#     Args:
#         selector: CSS选择器 (例如: "button", "#submit-btn", ".nav-link")
#
#     Returns:
#         点击操作的结果
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         click_tool = tools_by_name["click_element"]
#
#         result = await click_tool.arun({"selector": selector})
#         console.print(f"👆 已点击元素: {selector}", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"点击元素失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def extract_text() -> str:
#     """提取当前页面的文本内容
#
#     Returns:
#         页面的文本内容
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         extract_tool = tools_by_name["extract_text"]
#
#         result = await extract_tool.arun({})
#         console.print("📄 已提取页面文本", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"提取文本失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def extract_hyperlinks() -> str:
#     """提取当前页面的所有超链接
#
#     Returns:
#         页面中的所有链接信息
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         links_tool = tools_by_name["extract_hyperlinks"]
#
#         result = await links_tool.arun({})
#         console.print("🔗 已提取页面链接", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"提取链接失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def get_elements(selector: str, attributes: Optional[List[str]] = None) -> str:
#     """获取页面元素信息
#
#     Args:
#         selector: CSS选择器
#         attributes: 要获取的属性列表 (例如: ["innerText", "href", "src"])
#
#     Returns:
#         匹配元素的信息
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         elements_tool = tools_by_name["get_elements"]
#
#         args = {"selector": selector}
#         if attributes:
#             args["attributes"] = attributes
#
#         result = await elements_tool.arun(args)
#         console.print(f"🔍 已获取元素: {selector}", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"获取元素失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def current_page() -> str:
#     """获取当前页面的URL
#
#     Returns:
#         当前页面的URL
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         current_tool = tools_by_name["current_page"]
#
#         result = await current_tool.arun({})
#         console.print("📍 已获取当前页面URL", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"获取当前页面失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# @tool
# async def navigate_back() -> str:
#     """返回上一页
#
#     Returns:
#         返回操作的结果
#     """
#     try:
#         toolkit, tools = await get_browser_toolkit()
#         tools_by_name = {tool.name: tool for tool in tools}
#         back_tool = tools_by_name["previous_page"]
#
#         result = await back_tool.arun({})
#         console.print("⬅️ 已返回上一页", style="cyan")
#         return result
#     except Exception as e:
#         error_msg = f"返回上一页失败: {str(e)}"
#         console.print(f"❌ {error_msg}", style="red")
#         return error_msg
#
#
# async def close_browser():
#     """关闭浏览器实例"""
#     global _browser, _toolkit, _tools_cache
#
#     if _browser:
#         try:
#             await _browser.close()
#             console.print("🔒 浏览器已关闭", style="cyan")
#         except Exception as e:
#             console.print(f"⚠️ 关闭浏览器时出错: {str(e)}", style="yellow")
#         finally:
#             _browser = None
#             _toolkit = None
#             _tools_cache = None
#
#
# # 导出所有浏览器工具
# browser_tools = [
#     navigate_browser,
#     click_element,
#     extract_text,
#     extract_hyperlinks,
#     get_elements,
#     current_page,
#     navigate_back
# ]
