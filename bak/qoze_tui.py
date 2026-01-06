#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import asyncio
import subprocess
from datetime import datetime
from typing import List

from rich.text import Text
from rich.console import RenderableType
from rich.style import Style

from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical, Horizontal
from textual.widgets import Header, Footer, Input, Static, Label, RichLog, LoadingIndicator
from textual.binding import Binding
from textual import work
from textual.reactive import reactive
from textual.message import Message

# Import core agent components
# We need to set up the environment first
os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')

# Monkey patch or redirect shared_console before importing other modules if possible,
# or we will redirect it in on_mount.
import shared_console
from model_initializer import initialize_llm
from qoze_code_agent import agent, tools, conversation_state, create_message_with_images
import qoze_code_agent # To access global llm_with_tools

# We need to reimplement StreamOutput for TUI to avoid Rich Progress conflicts
from langchain_core.messages import AIMessage, ToolMessage

class TitleWidget(Static):
    """Title of the sidebar."""
    pass

class GitStatusWidget(Static):
    """Widget to display git status."""
    
    def on_mount(self) -> None:
        self.set_interval(5, self.refresh_status)
        self.refresh_status()

    def refresh_status(self) -> None:
        try:
            # Check if inside git repo
            subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], stderr=subprocess.DEVNULL)
            
            # Get status
            output = subprocess.check_output(["git", "status", "-s"], text=True)
            lines = output.strip().split('\n')
            
            if not output.strip():
                content = Text("No changes", style="dim italic")
            else:
                content = Text()
                for line in lines:
                    if not line.strip(): continue
                    status = line[:2]
                    file = line[3:]
                    
                    if '??' in status:
                        style = "bold red"
                    elif 'M' in status:
                        style = "bold yellow"
                    elif 'A' in status:
                        style = "bold green"
                    elif 'D' in status:
                        style = "bold red strike"
                    else:
                        style = "white"
                        
                    content.append(f"{status} {file}\n", style=style)
            
            self.update(content)
        except subprocess.CalledProcessError:
            self.update(Text("Not a git repository", style="dim"))
        except Exception as e:
            self.update(Text(f"Error: {str(e)}", style="red"))

class SessionInfoWidget(Static):
    """Widget for session info and CWD."""
    
    cwd = reactive(os.getcwd())
    
    def on_mount(self) -> None:
        self.set_interval(2, self.update_cwd)
        
    def update_cwd(self):
        self.cwd = os.getcwd()
        
    def render(self) -> RenderableType:
        text = Text()
        text.append("Project: ", style="bold")
        text.append("QozeCode\n", style="cyan")
        text.append("Version: ", style="bold")
        text.append("v0.2.3\n\n", style="dim")
        
        text.append("CWD:\n", style="bold")
        text.append(f"{self.cwd}\n\n", style="bright_black")
        
        text.append("Session Goal:\n", style="bold")
        text.append("Assisting user with development", style="green")
        return text

class TUIStreamOutput:
    """Adapted StreamOutput for Textual RichLog."""
    
    def __init__(self, agent, log_widget: RichLog):
        self.agent = agent
        self.log = log_widget
        
    async def stream_response(self, model_name, current_state, conversation_state):
        """Handle streaming response and write to RichLog."""
        current_response_text = ""
        current_reasoning = ""
        
        self.log.write(Text(f"\nThinking ({model_name})...", style="dim cyan"))
        
        # We accumulate text chunks to write them cleanly
        buffer = ""
        
        try:
            async for message_chunk, metadata in self.agent.astream(
                current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                if isinstance(message_chunk, ToolMessage):
                    # Tool outputs are usually handled by the node, but we might see them here
                    continue
                
                # Handling Reasoning (DeepSeek / Gemini)
                reasoning = ""
                if hasattr(message_chunk, 'additional_kwargs'):
                    reasoning = message_chunk.additional_kwargs.get('reasoning_content', '')
                
                if isinstance(message_chunk.content, list):
                     for item in message_chunk.content:
                         if isinstance(item, dict) and item.get('type') == 'thinking':
                             reasoning += item.get('thinking', '')

                if reasoning:
                    current_reasoning += reasoning
                    # Optionally display reasoning in a different color/block
                    # For now, let's just log it if it's new
                    pass 

                # Handling Content
                chunk_text = ""
                if isinstance(message_chunk.content, str):
                    chunk_text = message_chunk.content
                elif isinstance(message_chunk.content, list):
                    for item in message_chunk.content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            chunk_text += item.get('text', '')
                
                if chunk_text:
                    current_response_text += chunk_text
                    # self.log.write(chunk_text) # Writing every chunk might be too spammy for RichLog line breaks
                    # Instead, we write to the LAST line if possible, but RichLog appends.
                    # Textual RichLog doesn't support easy "streaming update of last line".
                    # We will accumulate and print on newlines or just print chunks.
                    self.log.write(Text(current_response_text, style="white"), scroll_end=True)
            
            # Finalize
            if current_reasoning:
                self.log.write(Text(f"\n[Reasoning]: {current_reasoning[:100]}...", style="dim"))
                
            conversation_state["messages"].append(AIMessage(content=current_response_text))
            conversation_state["llm_calls"] += 1
            self.log.write("\n") # Spacing
            
        except Exception as e:
            self.log.write(Text(f"Stream Error: {e}", style="red"))

class QozeTui(App):
    """The QozeCode Terminal User Interface."""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 2fr 1fr; 
        grid-rows: 1fr auto;
        background: #111111;
    }

    .box {
        height: 100%;
        border: solid #333333;
    }

    #main-log {
        background: #111111;
        color: #e0e0e0;
        padding: 1;
        overflow-y: scroll;
        scrollbar-gutter: stable;
    }

    #sidebar {
        background: #0d0d0d;
        border-left: solid #333333;
        padding: 1;
        row-span: 2;
    }

    #input-area {
        column-span: 1;
        height: auto;
        background: #111111;
        border-top: solid #333333;
        padding: 0 1;
    }

    Input {
        border: none;
        background: #111111;
        width: 100%;
    }
    Input:focus {
        border: none;
    }
    
    #status-bar {
        column-span: 2;
        background: #222222;
        color: #888888;
        height: 1;
        dock: bottom;
    }
    
    .status-label {
        padding: 0 1;
    }
    
    .status-right {
        dock: right;
        background: #005faf;
        color: white;
        padding: 0 1;
    }

    TitleWidget {
        color: #d75f00;
        text-style: bold;
        padding-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_screen", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        # Main Layout
        with Container(id="main-container"):
             yield RichLog(id="main-log", markup=True, wrap=True)

        # Sidebar
        with Vertical(id="sidebar"):
            yield TitleWidget("QozeCode TUI")
            yield SessionInfoWidget()
            yield TitleWidget("Modified Files")
            yield GitStatusWidget()

        # Input Area
        with Horizontal(id="input-area"):
             yield Label("[bold orange1]>[/]")
             yield Input(placeholder="Type your instruction...", id="command-input")
        
        # Status Bar
        with Horizontal(id="status-bar"):
            yield Label("ctrl+c quit | ctrl+l clear", classes="status-label")
            yield Label("Context: 24K", classes="status-label")
            yield Label("Claude 3.7 Sonnet", classes="status-right")

    def on_mount(self):
        self.query_one(Input).focus()
        self.log_widget = self.query_one("#main-log", RichLog)
        
        # Redirect shared_console print to our log
        # We create a simple wrapper
        class TUIConsole:
            def __init__(self, log_widget):
                self.log = log_widget
            def print(self, *args, **kwargs):
                # Convert args to string or renderable
                msg = " ".join(str(a) for a in args)
                style = kwargs.get("style", None)
                if style:
                    self.log.write(Text(msg, style=style))
                else:
                    self.log.write(msg)
            def status(self, *args, **kwargs):
                # Dummy status context for now
                from contextlib import contextmanager
                @contextmanager
                def nothing():
                    yield
                return nothing()
                
        # Inject the console redirection
        shared_console.console = TUIConsole(self.log_widget)
        
        self.log_widget.write(Text("Initializing Agent Environment...", style="dim"))
        self.init_agent_background()

    @work(thread=True)
    def init_agent_background(self):
        """Initialize the LLM in background."""
        try:
            model_name = "claude-4" # Default for now
            llm = initialize_llm(model_name)
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(tools)
            self.call_from_thread(self.log_widget.write, Text("Agent Ready. Model: " + model_name, style="bold green"))
        except Exception as e:
            self.call_from_thread(self.log_widget.write, Text(f"Failed to init agent: {e}", style="bold red"))

    async def on_input_submitted(self, message: Input.Submitted):
        user_input = message.value
        if not user_input:
            return
            
        self.query_one(Input).value = ""
        
        # Display user message
        self.log_widget.write(Text(f"\n> {user_input}", style="bold white"))
        
        if user_input.lower() in ['exit', 'quit']:
            self.exit()
        elif user_input.lower() == 'clear':
            self.log_widget.clear()
        else:
            self.run_agent_cycle(user_input)

    @work(thread=True)
    async def run_agent_cycle(self, user_input: str):
        """Runs the ReAct cycle."""
        try:
            # Prepare state
            image_folder = ".qoze/image"
            user_message = create_message_with_images(user_input, image_folder)
            
            # Update global state (simplified)
            current_state = {
                "messages": conversation_state["messages"] + [user_message],
                "llm_calls": conversation_state["llm_calls"]
            }
            
            # Stream Output
            streamer = TUIStreamOutput(agent, self.log_widget)
            await streamer.stream_response("claude-4", current_state, conversation_state)
            
            # Update conversation state globally (important for memory)
            # conversation_state is updated inside stream_response by reference normally,
            # but we need to ensure the user message is added.
            conversation_state["messages"].append(user_message)
            
        except Exception as e:
            self.call_from_thread(self.log_widget.write, Text(f"Error: {e}", style="red"))

    def action_clear_screen(self):
        self.query_one(RichLog).clear()

if __name__ == "__main__":
    app = QozeTui()
    app.run()
