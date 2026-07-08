#!/usr/bin/env python3
"""
=== DeepAgents 06: 银行场景 + 时间隧道 ===
演示：checkpointer 持久化 + 状态回溯

核心概念：
  - SqliteSaver     → 每步自动存档（类比银行交易日志）
  - thread_id       → 会话标识（类比账户号）
  - get_state_history() → 翻看历史（类比查流水）
  - 从历史 checkpoint 继续 → "冲正"后走不同分支

用法：
  python3 deepagent/06_bank_agent.py

  交互命令：
    直接输入问题  → 正常对话
    /history      → 查看 checkpoint 时间线
    /back N       → 回溯到第 N 个 checkpoint，从此走新分支
    /quit         → 退出
"""
import sqlite3
import os
import time
from datetime import datetime
from deepagents import create_deep_agent
from langgraph.checkpoint.sqlite import SqliteSaver

# ============================================================
# 模拟银行数据库
# ============================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".qoze", "data", "bank_checkpoints.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 模拟账户数据（内存中，每次启动重置）
ACCOUNTS = {
    "621700001": {"name": "张三", "balance": 10000.00, "history": []},
    "621700002": {"name": "李四", "balance": 5000.00,  "history": []},
    "621700003": {"name": "公司账户", "balance": 50000.00, "history": []},
}


def _format_amount(amount: float) -> str:
    return f"¥{amount:,.2f}"


def query_balance(account: str) -> str:
    """查询账户余额。account: 银行卡号"""
    if account not in ACCOUNTS:
        return f"账户 {account} 不存在"
    acc = ACCOUNTS[account]
    return f"账户 {account}（{acc['name']}）当前余额: {_format_amount(acc['balance'])}"


def transfer(from_account: str, to_account: str, amount: float) -> str:
    """转账。from_account: 付款卡号, to_account: 收款卡号, amount: 金额(元)"""
    if from_account not in ACCOUNTS:
        return f"转出账户 {from_account} 不存在"
    if to_account not in ACCOUNTS:
        return f"收款账户 {to_account} 不存在"
    if from_account == to_account:
        return "不能给自己转账"
    if amount <= 0:
        return "转账金额必须大于 0"
    if ACCOUNTS[from_account]["balance"] < amount:
        return f"余额不足！当前余额 {_format_amount(ACCOUNTS[from_account]['balance'])}，需要 {_format_amount(amount)}"

    ACCOUNTS[from_account]["balance"] -= amount
    ACCOUNTS[to_account]["balance"] += amount
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record_out = f"[{timestamp}] 转出 {_format_amount(amount)} → {to_account}({ACCOUNTS[to_account]['name']})"
    record_in = f"[{timestamp}] {from_account}({ACCOUNTS[from_account]['name']}) 转入 {_format_amount(amount)}"

    ACCOUNTS[from_account]["history"].append(record_out)
    ACCOUNTS[to_account]["history"].append(record_in)

    return (
        f"转账成功！{_format_amount(amount)} 已从 {from_account}({ACCOUNTS[from_account]['name']}) "
        f"转入 {to_account}({ACCOUNTS[to_account]['name']})\n"
        f"  付款方余额: {_format_amount(ACCOUNTS[from_account]['balance'])}\n"
        f"  收款方余额: {_format_amount(ACCOUNTS[to_account]['balance'])}"
    )


def transaction_history(account: str) -> str:
    """查询账户交易流水。account: 银行卡号"""
    if account not in ACCOUNTS:
        return f"账户 {account} 不存在"
    acc = ACCOUNTS[account]
    if not acc["history"]:
        return f"账户 {account}（{acc['name']}）暂无交易记录"
    lines = [f"账户 {account}（{acc['name']}）交易流水:"]
    for r in acc["history"]:
        lines.append(f"  • {r}")
    lines.append(f"当前余额: {_format_amount(acc['balance'])}")
    return "\n".join(lines)


# ============================================================
# 流式运行（带状态提示）
# ============================================================
def run_stream(agent, user_input: str, config: dict):
    """流式运行 agent，带实时状态提示"""
    current_node = None
    tool_shown = set()

    for chunk, metadata in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
        stream_mode="messages",
    ):
        node = metadata.get("langgraph_node", "")

        if node != current_node:
            current_node = node
            if node == "agent":
                print("\n💭 [思考中...]", end="")
            elif node == "tools":
                print("\n🔧 [执行操作...]")

        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
            for tc in chunk.tool_calls:
                if tc.get("name") and tc["name"] not in tool_shown:
                    tool_shown.add(tc["name"])
                    args_str = ", ".join(f"{k}={v}" for k, v in tc.get("args", {}).items())
                    print(f"\n   📞 {tc['name']}({args_str})")

        if chunk.type == "tool" and chunk.content:
            content = str(chunk.content)
            lines = content.split("\n")
            for line in lines:
                print(f"   │ {line}")
            tool_shown.clear()

        if chunk.type == "AIMessageChunk" and chunk.content:
            if not hasattr(chunk, "_header_printed"):
                print("\n🤖 [回复]\n", end="")
                chunk._header_printed = True
            print(chunk.content, end="", flush=True)

    print()


# ============================================================
# 时间隧道
# ============================================================
def show_history(agent, config: dict):
    """展示 checkpoint 时间线"""
    print("\n" + "=" * 60)
    print("⏱️  时间隧道 — Checkpoint 历史")
    print("=" * 60)

    snapshots = list(agent.get_state_history(config))
    if not snapshots:
        print("  (暂无历史记录)")
        return snapshots

    for i, snap in enumerate(reversed(snapshots)):
        ts = snap.metadata.get("step", "?")
        created = snap.metadata.get("timestamp", "?")
        if created != "?":
            try:
                created = datetime.fromtimestamp(created).strftime("%H:%M:%S")
            except Exception:
                pass

        msg_count = len(snap.values.get("messages", [])) if snap.values else 0
        parent = snap.metadata.get("checkpoint_id", "?")[:8]

        print(f"  [{i}] step={ts}  time={created}  messages={msg_count}  id={parent}")

    print(f"\n  共 {len(snapshots)} 个 checkpoint")
    return list(reversed(snapshots))


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("🏦 银行智能助手 — 带时间隧道")
    print("=" * 60)
    print("  工具: query_balance | transfer | transaction_history")
    print("  特殊命令: /history | /back N | /quit")
    print("=" * 60)

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        agent = create_deep_agent(
            model="deepseek:deepseek-v4-pro",
            tools=[query_balance, transfer, transaction_history],
            system_prompt="你是一个银行智能助手，帮助客户查询余额、转账、查看交易流水。用中文回答，简洁专业。",
            checkpointer=checkpointer,
        )

        thread_id = f"bank-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        config = {"configurable": {"thread_id": thread_id}}
        print(f"\n📋 会话 ID: {thread_id}")

        while True:
            try:
                user_input = input("\n👤 客户: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break

            if not user_input:
                continue

            if user_input == "/quit":
                print("👋 再见！")
                break

            if user_input == "/history":
                show_history(agent, config)
                continue

            if user_input.startswith("/back"):
                parts = user_input.split()
                if len(parts) != 2 or not parts[1].isdigit():
                    print("⚠️  用法: /back N（N 为 checkpoint 编号）")
                    continue

                idx = int(parts[1])
                snapshots = list(agent.get_state_history(config))
                snapshots.reverse()  # 从旧到新

                if idx < 0 or idx >= len(snapshots):
                    print(f"⚠️  编号 {idx} 超出范围（0~{len(snapshots)-1}）")
                    continue

                target = snapshots[idx]
                ts = datetime.fromtimestamp(target.metadata.get("timestamp", 0)).strftime("%H:%M:%S")
                print(f"\n🔙 回溯到 checkpoint [{idx}] ({ts})")
                print(f"   id: {target.metadata.get('checkpoint_id', '?')[:16]}...")

                # 更新 config，从目标 checkpoint 继续
                config = target.config
                thread_id = config["configurable"]["thread_id"]
                print(f"   新 thread_id: {thread_id}")
                print(f"   ✅ 已就绪，请输入新指令（将从这个时间点走不同分支）")
                continue

            # 正常对话
            run_stream(agent, user_input, config)


if __name__ == "__main__":
    main()
