"""
输入处理器模块 - 支持多种输入方式
"""
import traceback
from typing import Optional


def clean_text(text: str) -> str:
    """清理文本中的编码问题"""
    if not text:
        return ""
    # 移除可能的BOM字符
    text = text.replace('\ufeff', '').replace('\ufffe', '')
    # 移除不可打印字符
    text = ''.join(char for char in text if char.isprintable() or char in ['\n', '\t', '\r'])
    return text.strip()


class InputHandler:
    """输入处理器基类"""
    
    def __init__(self):
        pass
    
    async def get_input(self) -> Optional[str]:
        """获取用户输入"""
        raise NotImplementedError("子类必须实现此方法")


class PromptToolkitHandler(InputHandler):
    """使用prompt_toolkit的多行输入处理器"""
    
    async def get_input(self) -> Optional[str]:
        """使用prompt_toolkit获取多行输入"""
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.key_binding import KeyBindings

            # 创建自定义键绑定
            bindings = KeyBindings()

            @bindings.add('c-d')
            def _(event):
                """Ctrl+D 提交输入"""
                event.app.exit(result=event.app.current_buffer.text)

            @bindings.add('c-x')
            def _(event):
                """Ctrl+X 退出多行编辑"""
                event.app.exit(result=None)

            @bindings.add('c-l')
            def _(event):
                """Ctrl+L 清空全部内容"""
                event.app.current_buffer.text = ""


            # 创建异步会话
            session = PromptSession(
                multiline=True,
                key_bindings=bindings,
                bottom_toolbar="💡 输入内容后按 [Ctrl+D] 提交，[Ctrl+X] 退出多行编辑，[Ctrl+L] 清空",
                prompt_continuation=lambda width, line_number,
                                           wrap_count: "... " if line_number > 0 else ">>> ",
                complete_while_typing=False
            )

            # 异步获取输入
            user_input = await session.prompt_async()
            return clean_text(user_input)
            
        except Exception as e:
            traceback.print_exc()
            return None


class BasicInputHandler(InputHandler):
    """基础输入处理器 - 使用标准input函数"""
    
    async def get_input(self) -> Optional[str]:
        """使用基础的多行输入模式"""
        try:
            lines = []
            while True:
                line = input()
                # 检查退出命令
                if line.lower() in ['quit', 'exit', '退出', 'q']:
                    return None
                lines.append(line)
                # 如果输入为空行，则结束输入
                if line.strip() == "":
                    break
            user_input = '\n'.join(lines)
            return clean_text(user_input)
        except (KeyboardInterrupt, EOFError):
            return None


class InputManager:
    """输入管理器 - 支持多种输入方式"""
    
    def __init__(self):
        self.handlers = {
            'prompt_toolkit': PromptToolkitHandler(),
            'basic': BasicInputHandler()
        }
        self.current_handler = 'prompt_toolkit'
    
    async def get_user_input(self) -> Optional[str]:
        """获取用户输入"""
        handler = self.handlers.get(self.current_handler)
        if not handler:
            # 回退到基础输入
            handler = self.handlers['basic']
        
        return await handler.get_input()
    
    def set_handler(self, handler_name: str):
        """设置输入处理器"""
        if handler_name in self.handlers:
            self.current_handler = handler_name
        else:
            raise ValueError(f"不支持的输入处理器: {handler_name}")
    
    def get_available_handlers(self) -> list:
        """获取可用的输入处理器列表"""
        return list(self.handlers.keys())


# 全局输入管理器实例
input_manager = InputManager()