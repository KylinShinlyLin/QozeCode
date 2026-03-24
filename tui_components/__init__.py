from rich.default_styles import DEFAULT_STYLES

# 统一定制 TUI 中 RichLog 使用的 markdown 样式。
# 重点：弱化深层标题的层级感，避免在宽终端里出现“标题漂浮/疑似居中”的视觉效果。
DEFAULT_STYLES["markdown.h1"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.h2"] = "bold #7dcfff"
DEFAULT_STYLES["markdown.h3"] = "bold #2ac3de"
DEFAULT_STYLES["markdown.h4"] = "bold #c0caf5"
DEFAULT_STYLES["markdown.h5"] = "bold #c0caf5"
DEFAULT_STYLES["markdown.h6"] = "bold #a9b1d6"
DEFAULT_STYLES["markdown.h7"] = "dim #a9b1d6"
DEFAULT_STYLES["markdown.block_quote"] = "italic #565f89"
DEFAULT_STYLES["markdown.hr"] = "dim #414868"
DEFAULT_STYLES["markdown.item.bullet"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.item.number"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.code"] = "#ffd580 on #2f3549"
DEFAULT_STYLES["markdown.code_block"] = "#d5def5 on #202437"
DEFAULT_STYLES["markdown.link"] = "#7dcfff"
DEFAULT_STYLES["markdown.link_url"] = "underline #7dcfff"

# 兼容不同 rich 版本可能使用的 heading 命名
DEFAULT_STYLES["markdown.heading"] = "bold #c0caf5"
DEFAULT_STYLES["markdown.heading.1"] = "bold #7aa2f7"
DEFAULT_STYLES["markdown.heading.2"] = "bold #7dcfff"
DEFAULT_STYLES["markdown.heading.3"] = "bold #2ac3de"
DEFAULT_STYLES["markdown.heading.4"] = "bold #c0caf5"
DEFAULT_STYLES["markdown.heading.5"] = "bold #c0caf5"
DEFAULT_STYLES["markdown.heading.6"] = "bold #a9b1d6"
