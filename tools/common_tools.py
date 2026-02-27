# import getpass
# import uuid
#
# from crontab import CronTab
# from langchain.tools import tool
#
#
# @tool
# def manage_cron_job(action: str, command: str = None, schedule: str = None, comment: str = None,
#                     is_one_time: bool = False) -> str:
#     """Manage macOS system cron jobs (scheduled tasks).
#
#     Use this tool to list, add, or remove scheduled tasks in the system's crontab.
#
#     Args:
#         action: The operation to perform. Options:
#             - 'list': Show all current cron jobs.
#             - 'add': Add a new cron job. Requires 'command' and 'schedule'.
#             - 'remove': Remove a cron job. Requires 'comment' (recommended) or 'command' to identify the job.
#         command: The shell command to run. Required for 'add'.
#         schedule: The cron schedule expression (e.g., '*/5 * * * *' for every 5 mins, '0 9 * * 1' for every Monday at 9am). Required for 'add'.
#         comment: A unique identifier for the job. Highly recommended for 'add' and 'remove' to easily identify tasks.
#         is_one_time: If True, the job will remove itself after running once (only applies to 'add').
#
#     Returns:
#         A status message describing the outcome of the operation.
#     """
#     try:
#         current_user = getpass.getuser()
#         cron = CronTab(user=current_user)
#
#         # result_msg = ""
#
#         if action == "list":
#             jobs = list(cron)
#             if not jobs:
#                 result_msg = "No cron jobs found for user: " + current_user
#             else:
#                 lines = [f"**User: {current_user}**"]
#                 for job in jobs:
#                     sched = str(job.slices).strip()
#                     cmd = job.command
#                     cmt = f" ({job.comment})" if job.comment else ""
#                     lines.append(f"- `{sched}`: `{cmd}`{cmt}")
#                 result_msg = "\n".join(lines)
#
#         elif action == "add":
#             if not command or not schedule:
#                 return "[RUN_FAILED] ❌ Error: 'command' and 'schedule' are required for adding a job."
#
#             # 处理一次性任务逻辑
#             final_command = command
#             final_comment = comment
#
#             if is_one_time:
#                 # 如果没有提供注释，生成一个随机的唯一ID，确保删除逻辑能精确定位
#                 if not final_comment:
#                     final_comment = f"onetime_{uuid.uuid4().hex[:8]}"
#
#                 # 构建自删除命令
#                 # 逻辑：执行原命令 ; 读取当前crontab | 过滤掉包含该comment的行 | 写回crontab
#                 # 使用 ; 确保即使原命令失败，删除逻辑也会执行
#                 removal_cmd = f"crontab -l | grep -v '{final_comment}' | crontab -"
#                 final_command = f"{command} ; {removal_cmd}"
#             else:
#                 if not final_comment:
#                     final_comment = ""
#
#             # 创建新任务
#             job = cron.new(command=final_command, comment=final_comment)
#
#             # 设置时间
#             try:
#                 job.setall(schedule)
#             except KeyError:
#                 return f"[RUN_FAILED] ❌ Error: Invalid cron schedule expression '{schedule}'"
#
#             if not job.is_valid():
#                 return "[RUN_FAILED] ❌ Error: Job configuration is invalid."
#
#             cron.write()
#
#             type_str = "One-time" if is_one_time else "Recurring"
#             result_msg = f"✅ Successfully added {type_str} cron job:\nCommand: `{final_command}`\nSchedule: `{schedule}`\nComment: {final_comment}"
#
#         elif action == "remove":
#             if not comment and not command:
#                 return "[RUN_FAILED] ❌ Error: Please provide 'comment' or 'command' to identify the job to remove."
#
#             removed_count = 0
#             # 优先通过 comment 查找
#             if comment:
#                 iter = cron.find_comment(comment)
#                 for job in iter:
#                     cron.remove(job)
#                     removed_count += 1
#             # 其次通过 command 查找
#             elif command:
#                 iter = cron.find_command(command)
#                 for job in iter:
#                     cron.remove(job)
#                     removed_count += 1
#
#             if removed_count > 0:
#                 cron.write()
#                 result_msg = f"✅ Successfully removed {removed_count} cron job(s)."
#             else:
#                 result_msg = "⚠️ No matching cron jobs found to remove."
#
#         else:
#             return f"[RUN_FAILED] ❌ Error: Unknown action '{action}'. Use 'list', 'add', or 'remove'."
#
#         # # 显示结果
#         # panel = Panel(
#         #     Markdown(result_msg),
#         #     title="[bold blue]Cron Job Manager[/bold blue]",
#         #     border_style="blue",
#         #     padding=(0, 2)
#         # )
#         # console.print(panel)
#
#         return result_msg
#
#     except Exception as e:
#         error_msg = f"❌ System Error: {str(e)}"
#         # console.print(Panel(error_msg, style="red"))
#         return "[RUN_FAILED]" + error_msg

#
# class ReadImageFileSchema(BaseModel):
#     file_path: str = Field(..., description="The absolute path to the image file.")
#
#
# @tool(args_schema=ReadImageFileSchema)
# def read_image_file(file_path: str) -> str:
#     """Reads a local image file and returns base64 encoded image data.
#
#     Args:
#         file_path: The absolute path to the image file.
#
#     Returns:
#         A string containing the base64 encoded image data.
#     """
#     try:
#         console.print(f"[cyan]Reading image file... {file_path}[/cyan]")
#         if not os.path.exists(file_path):
#             return f"Error: File not found at {file_path}"
#
#         import mimetypes
#         mime_type, _ = mimetypes.guess_type(file_path)
#         if not mime_type:
#             mime_type = "image/png"
#
#         with open(file_path, "rb") as image_file:
#             import base64
#             encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
#
#         # Return as a single string to avoid LangChain list parsing errors
#         return f"Image data successfully read. Data URI: data:{mime_type};base64,{encoded_string}"
#
#     except Exception as e:
#         return f"Error reading image: {str(e)}"
