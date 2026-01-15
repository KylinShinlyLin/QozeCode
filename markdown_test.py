from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.geometry import Offset
from textual.message import Message
from textual.widgets import Header, Footer, Static, MarkdownViewer


class SelectableMarkdownWidget(MarkdownViewer):
    """支持多行选择的 Markdown 组件"""

    DEFAULT_CSS = """
    SelectableMarkdownWidget {
        scrollbar-gutter: stable;
    }

    SelectableMarkdownWidget .selected {
        background: blue 50%;
        color: white;
    }
    """

    class SelectionChanged(Message):
        """选择改变时的消息"""

        def __init__(self, selected_text: str) -> None:
            self.selected_text = selected_text
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.selected_text = ""

    def on_mount(self) -> None:
        """组件挂载时的初始化"""
        self.can_focus = True

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """鼠标按下事件"""
        if event.button == 1:  # 左键
            self.capture_mouse()
            self.is_selecting = True
            # 使用 Offset 来存储位置
            self.selection_start = Offset(event.x, event.y)
            self.selection_end = self.selection_start
            self.refresh()
            event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """鼠标移动事件"""
        if self.is_selecting and event.button == 1:
            self.selection_end = Offset(event.x, event.y)
            self.refresh()
            event.prevent_default()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """鼠标释放事件"""
        if event.button == 1 and self.is_selecting:
            self.release_mouse()
            self.is_selecting = False
            self._update_selection()
            event.prevent_default()

    def _update_selection(self) -> None:
        """更新选择的文本"""
        if not self.selection_start or not self.selection_end:
            return

        # 获取选择区域内的文本
        selected_text = self._get_selected_text()
        self.selected_text = selected_text

        # 发送选择改变消息
        self.post_message(self.SelectionChanged(selected_text))

    def _get_selected_text(self) -> str:
        """获取选中的文本内容"""
        if not self.selection_start or not self.selection_end:
            return ""

        try:
            # 确定选择区域的边界
            start_row = min(self.selection_start.y, self.selection_end.y)
            end_row = max(self.selection_start.y, self.selection_end.y)
            start_col = min(self.selection_start.x, self.selection_end.x) if start_row == end_row else (
                self.selection_start.x if self.selection_start.y < self.selection_end.y else self.selection_end.x
            )
            end_col = max(self.selection_start.x, self.selection_end.x) if start_row == end_row else (
                self.selection_end.x if self.selection_start.y < self.selection_end.y else self.selection_start.x
            )

            # 简单模拟选择的文本
            return f"选中区域: ({start_row},{start_col}) 到 ({end_row},{end_col})"

        except Exception as e:
            return f"选择区域: {self.selection_start} 到 {self.selection_end}"

    def render(self):
        """渲染组件"""
        # 直接返回父类的渲染结果，暂时不添加高亮效果
        return super().render()

    def clear_selection(self) -> None:
        """清除选择"""
        self.selection_start = None
        self.selection_end = None
        self.selected_text = ""
        self.is_selecting = False
        self.refresh()

    def get_selected_text(self) -> str:
        """获取当前选中的文本"""
        return self.selected_text


class MarkdownApp(App):
    """主应用"""

    CSS = """
    #info_panel {
        dock: bottom;
        height: 10;
        border: solid $primary;
        padding: 1;
    }

    #markdown_container {
        border: solid $secondary;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "copy", "复制选中文本"),
        Binding("escape", "clear_selection", "清除选择"),
    ]

    def __init__(self):
        super().__init__()
        # 留空，用户可以在这里填入自己的 markdown 内容
        self.markdown_content = """
        
        ---
__Advertisement :)__

- __[pica](https://nodeca.github.io/pica/demo/)__ - high quality and fast image
  resize in browser.
- __[babelfish](https://github.com/nodeca/babelfish/)__ - developer friendly
  i18n with plurals support and easy syntax.

You will like those projects!

---

# h1 Heading 8-)
## h2 Heading
### h3 Heading
#### h4 Heading
##### h5 Heading
###### h6 Heading


## Horizontal Rules

___

---

***


## Typographic replacements

Enable typographer option to see result.

(c) (C) (r) (R) (tm) (TM) (p) (P) +-

test.. test... test..... test?..... test!....

!!!!!! ???? ,,  -- ---

"Smartypants, double quotes" and 'single quotes'


## Emphasis

**This is bold text**

__This is bold text__

*This is italic text*

_This is italic text_

~~Strikethrough~~


## Blockquotes


> Blockquotes can also be nested...
>> ...by using additional greater-than signs right next to each other...
> > > ...or with spaces between arrows.


## Lists

Unordered

+ Create a list by starting a line with `+`, `-`, or `*`
+ Sub-lists are made by indenting 2 spaces:
  - Marker character change forces new list start:
    * Ac tristique libero volutpat at
    + Facilisis in pretium nisl aliquet
    - Nulla volutpat aliquam velit
+ Very easy!

Ordered

1. Lorem ipsum dolor sit amet
2. Consectetur adipiscing elit
3. Integer molestie lorem at massa


1. You can use sequential numbers...
1. ...or keep all the numbers as `1.`

Start numbering with offset:

57. foo
1. bar


## Code

Inline `code`

Indented code

    // Some comments
    line 1 of code
    line 2 of code
    line 3 of code


Block code "fences"

```
Sample text here...
```

Syntax highlighting

``` js
var foo = function (bar) {
  return bar++;
};

console.log(foo(5));
```

## Tables

| Option | Description |
| ------ | ----------- |
| data   | path to data files to supply the data that will be passed into templates. |
| engine | engine to be used for processing templates. Handlebars is the default. |
| ext    | extension to be used for dest files. |

Right aligned columns

| Option | Description |
| ------:| -----------:|
| data   | path to data files to supply the data that will be passed into templates. |
| engine | engine to be used for processing templates. Handlebars is the default. |
| ext    | extension to be used for dest files. |


## Links

[link text](http://dev.nodeca.com)

[link with title](http://nodeca.github.io/pica/demo/ "title text!")

Autoconverted link https://github.com/nodeca/pica (enable linkify to see)


## Images

![Minion](https://octodex.github.com/images/minion.png)
![Stormtroopocat](https://octodex.github.com/images/stormtroopocat.jpg "The Stormtroopocat")

Like links, Images also have a footnote style syntax

![Alt text][id]

With a reference later in the document defining the URL location:

[id]: https://octodex.github.com/images/dojocat.jpg  "The Dojocat"


## Plugins

The killer feature of `markdown-it` is very effective support of
[syntax plugins](https://www.npmjs.org/browse/keyword/markdown-it-plugin).


### [Emojies](https://github.com/markdown-it/markdown-it-emoji)

> Classic markup: :wink: :cry: :laughing: :yum:
>
> Shortcuts (emoticons): :-) :-( 8-) ;)

see [how to change output](https://github.com/markdown-it/markdown-it-emoji#change-output) with twemoji.


### [Subscript](https://github.com/markdown-it/markdown-it-sub) / [Superscript](https://github.com/markdown-it/markdown-it-sup)

- 19^th^
- H~2~O


### [\<ins>](https://github.com/markdown-it/markdown-it-ins)

++Inserted text++


### [\<mark>](https://github.com/markdown-it/markdown-it-mark)

==Marked text==


### [Footnotes](https://github.com/markdown-it/markdown-it-footnote)

Footnote 1 link[^first].

Footnote 2 link[^second].

Inline footnote^[Text of inline footnote] definition.

Duplicated footnote reference[^second].

[^first]: Footnote **can have markup**

    and multiple paragraphs.

[^second]: Footnote text.


### [Definition lists](https://github.com/markdown-it/markdown-it-deflist)

Term 1

:   Definition 1
with lazy continuation.

Term 2 with *inline markup*

:   Definition 2

        { some code, part of Definition 2 }

    Third paragraph of definition 2.

_Compact style:_

Term 1
  ~ Definition 1

Term 2
  ~ Definition 2a
  ~ Definition 2b


### [Abbreviations](https://github.com/markdown-it/markdown-it-abbr)

This is HTML abbreviation example.

It converts "HTML", but keep intact partial entries like "xxxHTMLyyy" and so on.

*[HTML]: Hyper Text Markup Language

### [Custom containers](https://github.com/markdown-it/markdown-it-container)

::: warning
*here be dragons*
:::

        """

    def compose(self) -> ComposeResult:
        """构建界面"""
        yield Header(show_clock=True)

        with Vertical():
            with Container(id="markdown_container"):
                yield SelectableMarkdownWidget(
                    self.markdown_content,
                    id="markdown_widget",
                    show_table_of_contents=False  # 禁用目录
                )

            yield Static(
                "选中的文本将显示在这里...\n使用鼠标拖拽选择文本，按 C 复制，ESC 清除选择，Q 退出",
                id="info_panel"
            )

        yield Footer()

    def on_selectable_markdown_widget_selection_changed(
            self, event: SelectableMarkdownWidget.SelectionChanged
    ) -> None:
        """处理选择改变事件"""
        info_panel = self.query_one("#info_panel", Static)

        if event.selected_text.strip():
            info_panel.update(
                f"选中的文本:\n{'-' * 40}\n{event.selected_text}\n{'-' * 40}\n"
                f"字符数: {len(event.selected_text)}"
            )
        else:
            info_panel.update("没有选中文本\n使用鼠标拖拽选择文本")

    def action_copy(self) -> None:
        """复制选中文本到剪贴板"""
        markdown_widget = self.query_one("#markdown_widget", SelectableMarkdownWidget)
        selected_text = markdown_widget.get_selected_text()

        if selected_text.strip():
            try:
                # 尝试复制到系统剪贴板（需要安装 pyperclip）
                import pyperclip
                pyperclip.copy(selected_text)
                self.notify("文本已复制到剪贴板", severity="information")
            except ImportError:
                self.notify("未安装 pyperclip，无法复制到剪贴板", severity="warning")
            except Exception as e:
                self.notify(f"复制失败: {e}", severity="error")
        else:
            self.notify("没有选中文本", severity="warning")

    def action_clear_selection(self) -> None:
        """清除选择"""
        markdown_widget = self.query_one("#markdown_widget", SelectableMarkdownWidget)
        markdown_widget.clear_selection()
        self.notify("已清除选择", severity="information")

    def action_quit(self) -> None:
        """退出应用"""
        self.exit()


if __name__ == "__main__":
    # 运行应用
    app = MarkdownApp()
    app.run()
