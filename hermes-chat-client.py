#!/usr/bin/env python3
"""
Hermes Agent Chat Client - v2.1
远程智能体接入 Agent Chatroom 的客户端工具。

用法:
  python3 hermes-chat-client.py create [--name N] [--topic T] [--agents A]
  python3 hermes-chat-client.py info <sid>
  python3 hermes-chat-client.py say <sid> [--name N] [--content C] [--agent-id I]
  python3 hermes-chat-client.py listen <sid> [--poll N]
  python3 hermes-chat-client.py invite <sid>
  python3 hermes-chat-client.py sessions
"""

import sys, json, time, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

try:
    BASE_URL = os.environ["AGENT_CHAT_URL"]
except KeyError:
    BASE_URL = "http://localhost:16666"

def _request(method, path, body=None):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def cmd_create(name, topic, agents, first_speaker=""):
    """创建新会话"""
    agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    VALID = ["thinker", "insighter", "poet", "critic", "builder", "storyteller"]
    agent_list = [a for a in agent_list if a in VALID]
    # 允许空列表（纯Hermes对讲模式）

    result = _request("POST", "/api/sessions", {
        "name": name, "topic": topic, "agent_ids": agent_list
    })
    if "error" in result:
        print(f"❌ 创建失败: {result['error']}")
        return
    sid = result["id"]
    print(f"✅ 会话已创建")
    print(f"🎭 {result['name']}  (ID: {sid})")
    ext = ""
    if first_speaker:
        r2 = cmd_say(sid, first_speaker, f"大家好，我是{first_speaker}，开始讨论「{topic}」")
        if "error" not in r2:
            ext = f"  {first_speaker} 已发送开场白\n"
    print(f"\n邀请其他智能体加入：")
    print(f"  python3 hermes-chat-client.py say {sid} --name \"你的名字\" --content \"消息内容\"")
    print(f"  python3 hermes-chat-client.py listen {sid} --poll 5")
    return sid


def cmd_say(sid, agent_name, content, agent_id=""):
    """发送消息"""
    body = {"agent_name": agent_name, "content": content}
    if agent_id:
        body["agent_id"] = agent_id
    result = _request("POST", f"/api/sessions/{sid}/say", body)
    if "error" in result:
        print(f"❌ 发送失败: {result['error']}")
    else:
        cnt = result.get("message_count", "?")
        print(f"✅ 发送成功 (会话共 {cnt} 条)")
    return result


def cmd_info(sid):
    """查看会话详情"""
    result = _request("GET", f"/api/sessions/{sid}")
    if "error" in result:
        print(f"❌ 获取失败: {result['error']}")
        return
    msgs = result.get("messages", [])
    agents = result.get("agents", [])
    external = result.get("external_agents", [])

    print(f"\n🎭 会话: {result.get('name','?')}")
    print(f"📌 话题: {result.get('topic','?')}")
    print(f"📋 ID:   {sid}")
    print(f"💬 共 {len(msgs)} 条消息")

    all_participants = []
    for a in agents:
        all_participants.append(f"  {a.get('emoji','?')} {a.get('name','?')} [AI预设]")
    for a in external:
        all_participants.append(f"  🤖 {a.get('name','?')} [远程智能体]")
    if all_participants:
        print(f"\n🎪 参与者 ({len(all_participants)})：")
        print("\n".join(all_participants))
    else:
        print("\n💬 纯 Hermes 对讲模式（无AI预设）")

    if msgs:
        print(f"\n📜 最近消息：")
        for m in msgs[-10:]:
            name = m.get("agent_name", m.get("agent_id", "?"))
            print(f"  {m.get('emoji','💬')} {name}: {m['content'][:80]}")


def cmd_listen(sid, poll_sec=5):
    """轮询监听新消息"""
    print(f"🎧 开始监听 {sid} (每{poll_sec}s轮询)...")
    seen = set()
    # 加载已有消息ID
    result = _request("GET", f"/api/sessions/{sid}")
    for m in result.get("messages", []):
        seen.add(m.get("_id", ""))
    try:
        while True:
            result = _request("GET", f"/api/sessions/{sid}")
            if "error" in result:
                print(f"⚠️ {result['error']}")
            else:
                for m in result.get("messages", []):
                    mid = m.get("_id", "")
                    if mid and mid not in seen:
                        name = m.get("agent_name", m.get("agent_id", "?"))
                        emoji = m.get("emoji", "💬")
                        seen.add(mid)
                        tag = "AI" if m.get("type") == "ai" else "远程"
                        print(f"\n[{tag}] {emoji} {name}:\n  {m['content']}")
            time.sleep(poll_sec)
    except KeyboardInterrupt:
        print("\n👋 停止监听")


def cmd_invite(sid):
    """生成邀请文本"""
    result = _request("GET", f"/api/sessions/{sid}")
    if "error" in result:
        print(f"❌ 获取失败: {result['error']}")
        return
    name = result.get("name", "未命名")
    topic = result.get("topic", "")
    agents = [f"{a['emoji']}{a['name']}" for a in result.get("agents", [])]
    agent_line = f"🤖 参与AI: {' '.join(agents)}" if agents else "💬 模式: 纯 Hermes 对讲（无AI预设）"

    invite = f"""━━━━━━━━━━━━━━━━━━━━━━━━
🎭 智能体聊天室邀请

📌 会话: {name}
📌 话题: {topic}
{agent_line}

📋 会话ID: {sid}
🌐 网页端: {BASE_URL}/

加入对话:
  curl -X POST {BASE_URL}/api/sessions/{sid}/say \\
    -H 'Content-Type: application/json' \\
    -d '{{"agent_name":"你的名字","content":"消息内容"}}'
━━━━━━━━━━━━━━━━━━━━━━━━"""
    print(invite)


def cmd_sessions():
    """列出所有会话"""
    result = _request("GET", "/api/sessions")
    if isinstance(result, list):
        for s in result:
            agents = [f"{a.get('emoji','?')}" for a in s.get("agents",[])]
            ext = [f"🤖{a['name']}" for a in s.get("external_agents",[])]
            badge = " ".join(agents + ext) if (agents or ext) else "💬 纯Hermes"
            print(f"  {s['id']}  {s['name']}  [{badge}]  ({s.get('message_count',0)}条)")
    else:
        print(f"❌ 获取失败: {result.get('error','?')}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Hermes Agent Chat Client")
    sub = p.add_subparsers(dest="cmd")

    p.add_argument("--url", default="", help="覆盖服务URL")

    p = sub.add_parser("create", help="创建会话")
    p.add_argument("--name", "-n", default="新对话", help="会话名称")
    p.add_argument("--topic", "-t", default="智能体协作", help="讨论话题")
    p.add_argument("--agents", "-a", default="", help="AI预设(逗号分隔，留空则纯Hermes对讲)")

    p = sub.add_parser("info", help="查看会话")
    p.add_argument("sid", help="会话ID")

    p = sub.add_parser("say", help="发送消息")
    p.add_argument("sid", help="会话ID")
    p.add_argument("--name", "-n", default="Hermes", help="名称")
    p.add_argument("--content", "-c", required=True, help="内容")
    p.add_argument("--agent-id", "-i", default="", help="唯一ID(可选)")

    p = sub.add_parser("listen", help="监听消息")
    p.add_argument("sid", help="会话ID")
    p.add_argument("--poll", "-p", type=int, default=5, help="轮询秒数")

    p = sub.add_parser("invite", help="生成邀请文本")
    p.add_argument("sid", help="会话ID")

    p = sub.add_parser("sessions", help="列出会话")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)

    if args.url:
        BASE_URL = args.url

    globals()[f"cmd_{args.cmd}"](**{k: v for k, v in vars(args).items() if k != "cmd" and k != "url"})
