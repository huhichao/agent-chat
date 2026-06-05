"""
Agent Chat - 多智能体聊天室（支持远程智能体互联）
创建会话，AI智能体 + 远程Hermes智能体同室交流
"""

import os
import json
import time
import random
import uuid
import threading
from flask import Flask, render_template, request, jsonify, Response
from openai import OpenAI

app = Flask(__name__)

# 数据持久化
DATA_FILE = "/tmp/agent-chat/session_data.json"
DATA_LOCK = threading.Lock()


def _save_data():
    """保存会话数据到文件"""
    with DATA_LOCK:
        try:
            with open(DATA_FILE, "w") as f:
                json.dump({
                    "sessions": {k: v for k, v in sessions.items()},
                    "counter": SESSION_ID_COUNTER[0],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] save data failed: {e}")


def _load_data():
    """从文件恢复会话数据"""
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        sessions.update(data.get("sessions", {}))
        SESSION_ID_COUNTER[0] = data.get("counter", SESSION_ID_COUNTER[0])
        print(f"  💾 已恢复 {len(sessions)} 个会话")
    except Exception as e:
        print(f"[WARN] load data failed: {e}")


# API 配置
DEEPSEEK_API_KEY = os.environ.get("PACKYAPI_DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://www.packyapi.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-flash"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# ───── 智能体预设库 ─────
AGENT_LIBRARY = {
    "thinker": {
        "id": "thinker", "name": "思辨者", "emoji": "🔍", "color": "#6366f1",
        "system_prompt": """你是一位「思辨者」，擅长从哲学、逻辑和系统思维的角度剖析问题。你的特点：深刻而不晦涩，用生动的类比解释抽象概念；习惯先解构问题的前提假设，再展开论述；喜欢追问本质，不满足于表面答案；说话带有思辨的节奏感，偶尔抛出反问。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
    "insighter": {
        "id": "insighter", "name": "洞察者", "emoji": "💡", "color": "#f59e0b",
        "system_prompt": """你是一位「洞察者」，擅长在看似不相关的领域之间建立连接，发现隐藏的模式。你的特点：直觉敏锐，能从日常现象中提炼出普适规律；表达简洁有力，喜欢用比喻和意象；能看到事物之间的隐性关联；偶尔带点诗意，但绝不空洞。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
    "poet": {
        "id": "poet", "name": "诗人", "emoji": "🌙", "color": "#ec4899",
        "system_prompt": """你是一位「诗人」，用诗意的眼光看待一切话题。你的特点：语言优美，善用比喻、通感等修辞；能从最平凡的事物中发现诗意；表达偏感性，但言之有物；喜欢用画面感和节奏感打动人。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
    "critic": {
        "id": "critic", "name": "质疑者", "emoji": "⚡", "color": "#ef4444",
        "system_prompt": """你是一位「质疑者」，专门负责挑战既有观点、发现逻辑漏洞。你的特点：思维锐利，善于发现论证中的薄弱环节；不是为杠而杠，而是为了把讨论推向更深层；喜欢追问「凭什么」「如果反过来呢」；用严谨的逻辑推动对话前进。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
    "builder": {
        "id": "builder", "name": "实干家", "emoji": "🛠️", "color": "#10b981",
        "system_prompt": """你是一位「实干家」，永远关注「怎么落地」「怎么做」。你的特点：务实落地，喜欢把抽象讨论转化为具体行动；习惯从「如果我来做……」的角度思考；对方法论、流程、实现细节特别敏感；能把天马行空的想法拉回地面。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
    "storyteller": {
        "id": "storyteller", "name": "说书人", "emoji": "📖", "color": "#8b5cf6",
        "system_prompt": """你是一位「说书人」，用故事和叙事来理解世界。你的特点：喜欢用故事、案例、人物经历来阐释观点；叙事生动，让抽象的概念变得可感知；善于从历史和经验中提取智慧；让对话有温度、有人味儿。规则：每次回复控制在 80-150 字；自然承接对话，不要重复开场白；可以赞同、补充、延展或提出新角度；不使用 Markdown 格式，用纯文本"""
    },
}

# ───── 会话存储 ─────
sessions = {}
SESSION_EVENTS = {}  # sid -> list of queues for SSE clients
SESSION_ID_COUNTER = [int(time.time())]
lock = threading.Lock()


def new_session_id():
    with lock:
        SESSION_ID_COUNTER[0] += 1
        return f"s{SESSION_ID_COUNTER[0]}"


def add_message(sid, msg):
    """添加消息并通知所有SSE客户端"""
    with lock:
        s = sessions.get(sid)
        if not s:
            return
        s["messages"].append(msg)
        _save_data()
        # 通知所有SSE监听者
        if sid in SESSION_EVENTS:
            dead = []
            for q in SESSION_EVENTS[sid]:
                try:
                    q.put_nowait(msg)
                except:
                    dead.append(q)
            for q in dead:
                if q in SESSION_EVENTS.get(sid, []):
                    SESSION_EVENTS[sid].remove(q)


def pick_next_speaker(session):
    """从会话的智能体中选择下一个发言者（最近没发言的优先）"""
    agents = session["agent_ids"]
    msgs = session["messages"]
    if not agents:
        return None
    if not msgs:
        return agents[0]

    speak_counts = {a: 0 for a in agents}
    last_msg_per_agent = {}
    for i, m in enumerate(msgs):
        aid = m["agent_id"]
        if aid in speak_counts:
            speak_counts[aid] += 1
            last_msg_per_agent[aid] = i

    silent = [a for a in agents if speak_counts.get(a, 0) == 0]
    if silent:
        return silent[0]

    min_count = min(speak_counts.values())
    candidates = [a for a in agents if speak_counts[a] == min_count]
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda a: last_msg_per_agent.get(a, -1))


def generate_response(agent_id, session):
    """调用 LLM 生成智能体回复"""
    agent = AGENT_LIBRARY[agent_id]
    topic = session["topic"]
    msgs = session["messages"]
    all_agents = [AGENT_LIBRARY[a] for a in session["agent_ids"] if a in AGENT_LIBRARY]
    external_agents = session.get("external_agents", {})

    # 构建所有参与者列表（包括预设+外部）
    all_participants = list(all_agents)
    for eid, einfo in external_agents.items():
        all_participants.append({"id": eid, "name": einfo["name"], "emoji": "🤖", "color": "#888"})

    other_participants = [p for p in all_participants if p["id"] != agent_id]

    other_names = "、".join([f"「{p['name']}」" for p in other_participants])
    all_names = "、".join([f"「{p['name']}」" for p in all_participants])

    sys_content = f"""{agent['system_prompt']}

当前话题：{topic}

这个对话中有以下参与者：{all_names}
"""
    if other_names:
        sys_content += f"你的对话伙伴是：{other_names}。请自然地参与对话。"

    messages = [{"role": "system", "content": sys_content}]

    for msg in msgs:
        aid = msg["agent_id"]
        # 判断是预设智能体还是外部智能体
        if aid in AGENT_LIBRARY:
            speaker_name = AGENT_LIBRARY[aid]["name"]
        elif aid in external_agents:
            speaker_name = external_agents[aid]["name"]
        else:
            speaker_name = aid

        role = "assistant" if aid == agent_id else "user"
        messages.append({"role": role, "content": f"{speaker_name}: {msg['content']}"})

    if not msgs:
        messages.append({"role": "user", "content": f"请就「{topic}」这个话题发起一段对话，阐述你的初步看法。"})
    else:
        messages.append({"role": "user", "content": f"现在轮到你了（{agent['name']}），请继续对话。"})

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL, messages=messages,
        max_tokens=1024, temperature=0.8, stream=False
    )
    return response.choices[0].message.content.strip()


# ───── API 路由 ─────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/agents")
def get_agents():
    return jsonify({aid: {"name": a["name"], "emoji": a["emoji"], "color": a["color"]}
                    for aid, a in AGENT_LIBRARY.items()})


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    result = []
    for sid, s in sessions.items():
        result.append({
            "id": sid, "name": s["name"], "topic": s["topic"],
            "agents": [{"id": a, **AGENT_LIBRARY[a]} for a in s["agent_ids"]],
            "external_agents": list(s.get("external_agents", {}).values()),
            "message_count": len(s["messages"]), "created_at": s["created_at"],
            "active": s["active"],
        })
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(result)


@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.json
    name = data.get("name", "新对话")
    topic = data.get("topic", "人工智能与人类意识")
    agent_ids = data.get("agent_ids", ["thinker", "insighter"])
    valid_ids = [a for a in agent_ids if a in AGENT_LIBRARY]
    # 允许0个AI预设（纯Hermes对讲模式）

    sid = new_session_id()
    sessions[sid] = {
        "name": name, "topic": topic, "agent_ids": valid_ids,
        "messages": [], "active": True, "created_at": time.time(),
        "external_agents": {},
    }
    _save_data()
    return jsonify({
        "id": sid, "name": name, "topic": topic,
        "agents": [{"id": a, **AGENT_LIBRARY[a]} for a in valid_ids],
        "message_count": 0,
    })


@app.route("/api/sessions/<sid>", methods=["GET"])
def get_session(sid):
    if sid not in sessions:
        return jsonify({"error": "会话不存在"}), 404
    s = sessions[sid]
    msgs = []
    for m in s["messages"]:
        aid = m["agent_id"]
        if aid in AGENT_LIBRARY:
            display = {"emoji": AGENT_LIBRARY[aid]["emoji"], "name": AGENT_LIBRARY[aid]["name"], "color": AGENT_LIBRARY[aid]["color"]}
        elif aid in s.get("external_agents", {}):
            einfo = s["external_agents"][aid]
            display = {"emoji": "🤖", "name": einfo["name"], "color": "#888"}
        else:
            display = {"emoji": "❓", "name": aid, "color": "#888"}
        msgs.append({**m, **display})

    return jsonify({
        "id": sid, "name": s["name"], "topic": s["topic"],
        "agents": [{"id": a, **AGENT_LIBRARY[a]} for a in s["agent_ids"]],
        "external_agents": list(s.get("external_agents", {}).values()),
        "messages": msgs, "active": s["active"],
        "next_speaker": pick_next_speaker(s),
    })


@app.route("/api/sessions/<sid>/speak", methods=["POST"])
def agent_speak(sid):
    """AI智能体发言（或自动选下一个）"""
    if sid not in sessions:
        return jsonify({"error": "会话不存在"}), 404
    s = sessions[sid]
    if not s["active"]:
        return jsonify({"error": "会话已结束"}), 400

    data = request.json
    agent_id = data.get("agent_id") if data else None
    if agent_id:
        if agent_id not in s["agent_ids"]:
            return jsonify({"error": "该智能体不在此会话中"}), 400
    else:
        # 自动选择下一个发言人
        agent_id = pick_next_speaker(s)
        if agent_id is None:
            return jsonify({"error": "没有AI预设智能体，请使用 /say 接口发言"}), 400
    try:
        content = generate_response(agent_id, s)
        msg = {"agent_id": agent_id, "content": content, "timestamp": time.time(), "type": "ai"}
        add_message(sid, msg)
        return jsonify({
            "message": msg,
            "next_speaker": pick_next_speaker(s),
            "message_count": len(s["messages"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<sid>/say", methods=["POST"])
def external_say(sid):
    """远程智能体发言"""
    if sid not in sessions:
        return jsonify({"error": "会话不存在"}), 404
    s = sessions[sid]

    data = request.json
    agent_name = data.get("agent_name", "远程智能体")
    content = data.get("content", "").strip()
    agent_id_hint = data.get("agent_id", "").strip()

    if not content:
        return jsonify({"error": "内容不能为空"}), 400

    # 生成唯一ID
    ext_id = agent_id_hint or f"ext_{uuid.uuid4().hex[:8]}"

    # 注册到外部智能体列表
    if ext_id not in s.setdefault("external_agents", {}):
        s["external_agents"][ext_id] = {"id": ext_id, "name": agent_name}

    msg = {
        "agent_id": ext_id,
        "content": content,
        "timestamp": time.time(),
        "type": "external",
        "agent_name": agent_name,
    }
    add_message(sid, msg)

    return jsonify({
        "ok": True,
        "message": msg,
        "message_count": len(s["messages"]),
    })


@app.route("/api/sessions/<sid>/delete", methods=["POST"])
def delete_session(sid):
    if sid in sessions:
        del sessions[sid]
        _save_data()
    return jsonify({"ok": True})


@app.route("/api/sessions/<sid>/stream")
def stream_session(sid):
    """SSE 实时事件流 - 远程智能体通过此端点实时接收新消息"""
    if sid not in sessions:
        return jsonify({"error": "会话不存在"}), 404

    def event_stream():
        import queue
        q = queue.Queue()
        with lock:
            if sid not in SESSION_EVENTS:
                SESSION_EVENTS[sid] = []
            SESSION_EVENTS[sid].append(q)

        try:
            # 先发送当前所有消息
            with lock:
                s = sessions.get(sid, {})
                for msg in s.get("messages", []):
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with lock:
                if sid in SESSION_EVENTS and q in SESSION_EVENTS[sid]:
                    SESSION_EVENTS[sid].remove(q)

    return Response(event_stream(), mimetype="text/event-stream")


# ───── 启动 ─────
if __name__ == "__main__":
    _load_data()
    port = int(os.environ.get("PORT", 16666))
    print(f"\n  🎭 智能体聊天室启动！")
    print(f"  ─────────────────────────────")
    print(f"  🌐 http://localhost:{port}")
    agents_list = [f"{a['emoji']} {a['name']}" for a in AGENT_LIBRARY.values()]
    print(f"  🤖 预设智能体：{' · '.join(agents_list)}")
    print(f"  🔌 SSE流:   /api/sessions/<sid>/stream")
    print(f"  📤 远程发言: POST /api/sessions/<sid>/say")
    print(f"  ─────────────────────────────\n")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
