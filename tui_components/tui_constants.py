# -*- coding: utf-8 -*-

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

CSS = """
    Screen { color: #a9b1d6; }
    TopBar { dock: top; height: 1; color: #c0caf5; }

    #main-container { height: 1fr; width: 100%; layout: horizontal; }
    #chat-area { width: 80%; height: 100%; }

    /* 欢迎区域样式 */
    #welcome-panel {
        width: 100%;
        height: auto;
        padding: 1 2;
        align: center bottom;
    }

    #welcome-art {
        width: 100%;
        height: auto;
        content-align: center middle;
    }

    #welcome-tips {
        width: 100%;
        height: auto;
        content-align: center middle;
        color: #565f89;
        margin-top: 1;
    }

    /* 新消息系统样式 */
    #message-list {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 1 2;
    }

    #main-output {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 1 2;
        overflow-x: hidden;
    }

    #source-output {
        width: 100%;
        height: 1fr;
        border: none;
        color: #c0caf5;
        padding: 1;
        display: none;
    }

    #tool-status { width: 100%; height: auto; min-height: 1; padding: 0 2; display: none; }

    #stream-output {
        color: #565f89;
        width: 100%;
        height: auto;
        max-height: 30%;
        padding: 0 2;
        border-top: heavy #414868;
        display: none;
        overflow-y: auto;
        scrollbar-visibility: hidden;
    }

    #stream-output > BlockQuote {
        border-left: none;
        color: #565f89;
        text-style: italic;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    #sidebar { width: 1fr; height: 100%; padding: 1 2; color: #a9b1d6; border-left: heavy #2f334d; }
    #bottom-container { height: auto; dock: bottom; }
    #input-line { height: 3; width: 100%; align-vertical: middle; padding: 0 1; border-top: heavy #414868; }
    .prompt-symbol { color: #bb9af7; text-style: bold; width: 2; content-align: center middle; }

    Input { width: 1fr; border: none; color: #c0caf5; padding: 0; }
    Input:focus { border: none; }
    Input > .input--cursor { background: #c0c4cc; color: #1a1b26; }
    Input > .input--placeholder { color: #787c99; }

    TextArea { height: 10; width: 100%; border: round #808080; color: #c0caf5; padding: 1; }
    TextArea:dark .text-area--cursor { background: #c0c4cc; color: #1a1b26; }

    .hidden { display: none; }

    #request-indicator { height: 1; width: 100%; color: #7aa2f7; padding: 0 1; }
    StatusBar { height: 1; width: 100%; dock: bottom; }

    #command-suggestions {
        display: none;
        background: #1e1e2e;
        border: round #414868;
        max-height: 12;
        width: 70%;
        margin-left: 2;
        margin-bottom: 0;
        padding: 1;
        overflow-y: auto;
    }
    #command-suggestions > .option-list--option { padding: 0 1; }
    #command-suggestions > .option-list--option:hover { background: #414868; }

    /* --- Markdown Styles --- */
    Markdown { color: #c0caf5; }

    MarkdownH1 { color: #7aa2f7; text-style: bold; margin: 1 0 0 0; }
    MarkdownH2 { color: #7dcfff; text-style: bold; margin: 1 0 0 0; }
    MarkdownH3 { color: #2ac3de; text-style: bold; margin: 1 0 0 0; }
    MarkdownH4 { color: #c0caf5; text-style: bold; margin: 0; }
    MarkdownH5 { color: #c0caf5; text-style: bold; margin: 0; }
    MarkdownH6 { color: #a9b1d6; text-style: bold; margin: 0; }

    /* 内联代码 */
    MarkdownCode { color: #7dcfff; background: #2f334d; }

    /* 代码块 (fenced code blocks) */
    MarkdownFence {
        color: #c0caf5;
        background: #1a1b26;
        margin: 1 0;
        padding: 0 1;
    }
    MarkdownFence > MarkdownFenceStartLine,
    MarkdownFence > MarkdownFenceEndLine {
        color: #565f89;
        background: #2f334d;
        padding: 1;
    }
    MarkdownFence > MarkdownCode {
        color: #c0caf5;
        background: #1a1b26;
    }

    /* 引用块 */
    Markdown > BlockQuote {
        color: #565f89;
        border-left: solid #565f89;
        margin: 0;
        padding: 0 1;
    }

    /* 列表 */
    Markdown > BulletList, Markdown > OrderedList {
        color: #c0caf5;
        margin: 0;
        padding: 0 2;
    }

    /* 分隔线 */
    MarkdownHorizontalRule { color: #414868; margin: 1 0; }

    /* 表格 */
    MarkdownTable {
        color: #c0caf5;
        margin: 1 0;
    }
    MarkdownTableContent {
        keyline: thin #565f89;
    }
    MarkdownTableContent .header {
        color: #7aa2f7;
        text-style: bold;
    }
    MarkdownTableContent .cell {
        color: #a9b1d6;
    }
    MarkdownTable > MarkdownH1 { color: #7aa2f7; text-style: bold; }
    MarkdownTable > MarkdownH2 { color: #7dcfff; text-style: bold; }
    MarkdownTable > MarkdownH3 { color: #2ac3de; text-style: bold; }
    /* ----------------------- */
        """

QOZE_CODE_ART = """
██████╗  ██████╗ ███████╗███████╗     ██████╗ ██████╗ ██████╗ ███████╗
██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
██║   ██║██║   ██║  ███╔╝ █████╗      ██║     ██║   ██║██║  ██║█████╗
██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝
╚██████╔╝╚██████╔╝███████╗███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗
 ╚══▀▀═╝  ╚═════╝ ╚══════╝ ╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
"""
