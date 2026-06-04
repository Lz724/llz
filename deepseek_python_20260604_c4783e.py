import streamlit as st
import pandas as pd
import time
from datetime import datetime

# ---------------------------- 初始化 Session State ----------------------------
def init_state():
    if "running" not in st.session_state:
        st.session_state.running = False           # 模拟开关
        st.session_state.seq = 0                   # 最新心跳序号
        st.session_state.last_ts = None            # 最后一次心跳的时间戳
        st.session_state.records = []              # 存储 (序号, 时间戳)
        st.session_state.alert_msg = ""            # 报警信息

init_state()

# ---------------------------- 辅助函数 ----------------------------
def add_heartbeat(seq, ts):
    """添加一条心跳记录，保留最近 20 条"""
    st.session_state.records.insert(0, (seq, ts))
    if len(st.session_state.records) > 20:
        st.session_state.records.pop()
    st.session_state.seq = seq
    st.session_state.last_ts = ts

def reset_all():
    """完全重置系统"""
    st.session_state.running = False
    st.session_state.seq = 0
    st.session_state.last_ts = None
    st.session_state.records = []
    st.session_state.alert_msg = ""

# ---------------------------- 页面 UI ----------------------------
st.title("🛸 无人机心跳监测系统")
st.markdown("模拟无人机每秒发送心跳包，地面站实时监测并绘制折线图，3 秒未收到自动报警")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🚀 启动模拟"):
        reset_all()
        st.session_state.running = True
        # 立即生成第一条心跳
        add_heartbeat(1, time.time())
        st.rerun()   # 立即刷新，开始自动循环
with col2:
    if st.button("⏸️ 暂停/恢复"):
        st.session_state.running = not st.session_state.running
        st.rerun()
with col3:
    if st.button("🛑 停止模拟"):
        reset_all()
        st.rerun()

# ---------------------------- 心跳生成逻辑（仅在运行中执行）----------------------------
if st.session_state.running:
    now = time.time()
    last = st.session_state.last_ts

    # 首次启动时确保有 last_ts
    if last is None:
        add_heartbeat(1, now)
    else:
        diff = now - last
        if diff >= 1.0:
            # 补偿丢失的心跳（最多补偿5个，避免突然跳变太大）
            n = min(int(diff), 5)
            for i in range(n):
                new_seq = st.session_state.seq + 1
                sim_ts = last + (i + 1)   # 模拟均匀间隔
                add_heartbeat(new_seq, sim_ts)

    # 超时检测（3 秒未收到心跳即报警）
    if st.session_state.last_ts and (time.time() - st.session_state.last_ts) > 3.0:
        st.session_state.alert_msg = f"⚠️ 连接超时！已 {time.time() - st.session_state.last_ts:.1f} 秒未收到心跳"
    else:
        st.session_state.alert_msg = ""

    # 等待 1 秒，然后自动刷新页面，模拟实时更新
    time.sleep(1)
    st.rerun()

# ---------------------------- 状态显示 ----------------------------
col_status, col_alert = st.columns(2)
with col_status:
    st.metric("📡 最新心跳序号", st.session_state.seq if st.session_state.seq > 0 else "—")
    status_text = "✈️ 飞行中" if st.session_state.running else "🛬 已停止"
    st.write(f"无人机状态：{status_text}")

with col_alert:
    if st.session_state.alert_msg:
        st.error(st.session_state.alert_msg)
    else:
        st.success("✅ 连接正常")

# ---------------------------- 折线图 ----------------------------
if st.session_state.records:
    df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
    df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
    df = df.sort_values("时间")   # 时间顺序从左到右
    st.subheader("📈 心跳序号变化趋势")
    st.line_chart(df.set_index("时间")["序号"])
else:
    st.info("尚未收到任何心跳包，请点击「启动模拟」")

# ---------------------------- 最近记录表格 ----------------------------
if st.session_state.records:
    df_table = pd.DataFrame(st.session_state.records, columns=["心跳序号", "时间戳"])
    df_table["接收时间"] = df_table["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
    df_table = df_table[["心跳序号", "接收时间"]]
    st.subheader("📋 心跳包记录（最近 20 条）")
    st.dataframe(df_table, use_container_width=True)
else:
    st.info("暂无记录")