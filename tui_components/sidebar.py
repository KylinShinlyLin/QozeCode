# -*- coding: utf-8 -*-
import asyncio
import os
from rich.text import Text
from textual.widgets import Static
import qoze_code_agent

# --- Async Git Helpers ---
async def run_async_cmd(args, timeout=2.0):
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode('utf-8', errors='ignore').strip()
    except Exception:
        return ""

async def get_git_info():
    url = await run_async_cmd(['git', 'remote', 'get-url', 'origin'])
    return url if url else "local"

async def get_git_branch():
    branch = await run_async_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    return branch if branch else None

async def get_modified_files():
    status = await run_async_cmd(['git', 'status', '-s'])
    if not status:
        return []
    files = []
    for line in status.split('\n'):
        parts = line.split()
        if len(parts) >= 2:
            files.append((parts[0], parts[-1]))
    return files

class Sidebar(Static):
    def __init__(self, *args, model_name="Unknown", provider, **kwargs):
        self.model_name = model_name
        self.provider = provider
        super().__init__(*args, **kwargs)

    async def on_mount(self):
        # Initial update
        await self.update_info()
        # Scheduled update (Textual handles async callbacks correctly)
        self.set_interval(5, self.update_info)

    async def update_info(self):
        cwd = os.getcwd()
        repo_url = await get_git_info()
        modified = await get_modified_files()
        branch = await get_git_branch()

        text = Text()
        text.append("\n项目信息\n", style="bold #7aa2f7 underline")
        text.append(f"Repo: ", style="dim white")
        text.append(f"{repo_url.split('/')[-1].replace('.git', '')}\n", style="bold cyan")
        if branch:
            text.append(f"Branch: ", style="dim white")
            text.append(f"{branch}\n", style="bold cyan")

        text.append(f"模型: ", style="dim white")
        text.append(f"{self.model_name}\n", style="bold cyan")
        text.append(f"模型厂商: ", style="dim white")
        text.append(f"{self.provider.value}\n", style="bold cyan")
        text.append(f"当前目录: ", style="dim white")
        text.append(f"{os.getcwd()}\n\n", style="bold cyan")

        # 实时检测图片数量
        image_folder = ".qoze/image"
        img_count = 0
        if os.path.exists(image_folder):
            try:
                img_files = qoze_code_agent.get_image_files(image_folder)
                img_count = len(img_files)
            except Exception:
                pass

        if img_count > 0:
            sent_imgs = qoze_code_agent.conversation_state.get("sent_images", {})
            new_count = 0
            if os.path.exists(image_folder):
                try:
                    for f in qoze_code_agent.get_image_files(image_folder):
                        mtime = os.path.getmtime(f)
                        if f not in sent_imgs or sent_imgs[f] != mtime:
                            new_count += 1
                except:
                    new_count = img_count
            text.append("图片上下文: ", style="dim white")
            if new_count > 0:
                text.append(f"{img_count} 张 ({new_count} 新)", style="bold yellow")
            else:
                text.append(f"{img_count} 张 (已发送)", style="dim green")

        if modified:
            text.append("\nGIT 变更记录\n", style="bold #7dcfff underline")
            for status, filename in modified:
                if 'M' in status:
                    icon = "✹"
                    style = "yellow"
                elif 'A' in status or '?' in status:
                    icon = "+"
                    style = "green"
                elif 'D' in status:
                    icon = "-"
                    style = "dim white"
                else:
                    icon = "•"
                    style = "white"
                text.append(f"{icon} {filename[:20]}\n", style=style)
        else:
            text.append("", style="dim green")

        self.update(text)
