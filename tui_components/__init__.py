from rich.default_styles import DEFAULT_STYLES

# 统一定制 TUI 中 RichLog 使用的 markdown 样式，
# 覆盖 rich 默认颜色，避免在部分终端中标题/引用显示为红色导致“像异常”的误解。
# 颜色值与 tui_constants.py 中的 MarkdownWidget CSS 保持一致。
DEFAULT_STYLES["markdown.h1"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.h2"] = "bold #7dcfff"
DEFAULT_STYLES["markdown.h3"] = "bold #2ac3de"
DEFAULT_STYLES["markdown.h4"] = "bold #9ece6a"
DEFAULT_STYLES["markdown.h5"] = "bold #e0af68"
DEFAULT_STYLES["markdown.h6"] = "bold #ff9e64"
DEFAULT_STYLES["markdown.h7"] = "dim #ff9e64"
DEFAULT_STYLES["markdown.block_quote"] = "italic #565f89"
DEFAULT_STYLES["markdown.hr"] = "dim #414868"
DEFAULT_STYLES["markdown.item.bullet"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.item.number"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.code"] = "#ff9e64 on #24283b"
DEFAULT_STYLES["markdown.code_block"] = "#c0caf5 on #1a1b26"
DEFAULT_STYLES["markdown.link"] = "#7dcfff"
DEFAULT_STYLES["markdown.link_url"] = "underline #7dcfff"

