# -*- coding: utf-8 -*-

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


CSS = """
    Screen { background: #1a1b26; color: #a9b1d6; }
    TopBar { dock: top; height: 1; background: #13131c; color: #c0caf5; }

    #main-container { height: 1fr; width: 100%; layout: horizontal; }
    #chat-area { width: 78%; height: 100%; }

    #main-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        padding: 1 2;
    }

    #source-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        color: #c0caf5;
        padding: 1;
        display: none;
    }

    #tool-status { width: 100%; height: auto; min-height: 1; background: #13131c; padding: 0 2; display: none; }

    #stream-output { color: #565f89;
        width: 100%;
        height: auto;
        max-height: 60%;
        background: #13131c;
        padding: 0 2;
        border-top: solid #414868;
        display: none;
        overflow-y: auto;
        scrollbar-visibility: hidden;
    }

    #stream-output > BlockQuote {
        border-left: none;
        color: #565f89;
        background: #13131c;
        text-style: italic;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    #sidebar { width: 22%; height: 100%; background: #16161e; padding: 1 2; color: #565f89; border-left: solid #2f334d; }
    #bottom-container { height: auto; dock: bottom; background: #13131c; }
    #input-line { height: 3; width: 100%; align-vertical: middle; padding: 0 1; border-top: solid #414868; background: #13131c; }
    .prompt-symbol { color: #bb9af7; text-style: bold; width: 2; content-align: center middle; }

    Input { width: 1fr; background: #13131c; border: none; color: #c0caf5; padding: 0; }
    Input:focus { border: none; }

    TextArea { height: 10; width: 100%; background: #13131c; border: round #808080; color: #c0caf5; padding: 1; }

    .hidden { display: none; }

    #request-indicator { height: 1; width: 100%; background: #13131c; color: #7aa2f7; padding: 0 1; }
    StatusBar { height: 1; width: 100%; background: #13131c; dock: bottom; }

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
    MarkdownH1 { color: #7aa2f7; text-style: bold; border-bottom: wide #7aa2f7; }
    MarkdownH2 { color: #7dcfff; text-style: bold; border-bottom: wide #7dcfff; }
    MarkdownH3 { color: #2ac3de; text-style: bold; }
    MarkdownH4 { color: #9ece6a; text-style: bold; }
    MarkdownH5 { color: #e0af68; text-style: bold; }
    MarkdownH6 { color: #ff9e64; text-style: bold; }
    MarkdownCode { color: #ff9e64; background: #24283b; }
    Markdown > BlockQuote { color: #565f89; border-left: solid #565f89; }
    /* ----------------------- */
        """

QOZE_CODE_ART = """
██████╗  ██████╗ ███████╗███████╗     ██████╗ ██████╗ ██████╗ ███████╗   
██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝  
██║   ██║██║   ██║  ███╔╝ █████╗      ██║     ██║   ██║██║  ██║█████╗    
██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝    
╚██████╔╝╚██████╔╝███████╗███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗  
 ╚══▀▀═╝  ╚═════╝ ╚═════╝ ╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝  
     """