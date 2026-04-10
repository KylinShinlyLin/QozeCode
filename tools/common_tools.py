from langchain.tools import tool


# @tool
# def ask_for_user(question: str) -> str:
#     """主动询问用户以获取更多信息或确认。
#
#     当 agent 需要用户的输入、确认、选择或更多信息时，使用此工具暂停执行并等待用户回复。
#     触发此工具后，对话会立即结束，等待用户在下一次输入时回复。
#
#     Args:
#         question: 要向用户提出的问题或需要确认的内容。应该清晰明了地说明需要什么信息。
#
#     Returns:
#         一个标记字符串，表示正在等待用户输入。
#     """
#     return f"[ASK_FOR_USER] {question}"
