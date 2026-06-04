import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import pydeck as pdk
import numpy as np

# ---------------------------- 坐标系转换算法 ----------------------------
# WGS-84 与 GCJ-02 互转（高德/百度使用GCJ-02，实际百度是BD-09，但用户要求GCJ-02）
# 以下为简化版转换，精确度足够演示使用

def transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    """WGS-84 转 GCJ-02"""
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 / sqrtmagic) * math.cos(radlat) * math.pi / 180.0)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi / 180.0)
    return lng + dlng, lat + dlat

def gcj02_to_wgs84(lng, lat):
    """GCJ-02 转 WGS-84"""
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat

def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

# ---------------------------- 初始化 Session State ----------------------------
def init_state():
    # 飞行监控相关
    if "running" not in st.session_state:
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_ts = None
        st.session_state.records = []
        st.session_state.alert_msg = ""
    # 航线规划相关
    if "coord_system" not in st.session_state:
        st.session_state.coord_system = "GCJ-02"  # 默认高德坐标系
    if "point_A" not in st.session_state:
        st.session_state.point_A = {"lat": 32.2322, "lng": 118.749, "set": False}
    if "point_B" not in st.session_state:
        st.session_state.point_B = {"lat": 32.2343, "lng": 118.749, "set": False}
    if "flight_height" not in st.session_state:
        st.session_state.flight_height = 50.0

init_state()

# ---------------------------- 辅助函数 ----------------------------
def add_heartbeat(seq, ts):
    st.session_state.records.insert(0, (seq, ts))
    if len(st.session_state.records) > 20:
        st.session_state.records.pop()
    st.session_state.seq = seq
    st.session_state.last_ts = ts

def reset_monitor():
    st.session_state.running = False
    st.session_state.seq = 0
    st.session_state.last_ts = None
    st.session_state.records = []
    st.session_state.alert_msg = ""

def convert_to_wgs84(lat, lng, src_system):
    """将输入的坐标转换为WGS-84（供地图使用）"""
    if src_system == "WGS-84":
        return lng, lat
    else:  # GCJ-02
        return gcj02_to_wgs84(lng, lat)

# ---------------------------- 生成障碍物（位于校园内，AB之间）------------------------
# 校园大致范围（南京某大学校园示例，中心约118.75, 32.233）
# 定义几个固定障碍物坐标（WGS-84）
obstacles_wgs84 = [
    {"lng": 118.7485, "lat": 32.2328, "radius": 20, "name": "教学楼"},
    {"lng": 118.7492, "lat": 32.2335, "radius": 25, "name": "图书馆"},
    {"lng": 118.7500, "lat": 32.2330, "radius": 18, "name": "实验楼"},
    {"lng": 118.7495, "lat": 32.2325, "radius": 15, "name": "食堂"},
]

# ---------------------------- 页面导航 ----------------------------
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# ---------------------------- 航线规划页面 ----------------------------
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("规划无人机飞行路线，设置起点/终点及飞行高度，地图显示障碍物（红色区域）")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("控制面板")
        # 坐标系选择
        coord_sys = st.selectbox("输入坐标系", ["WGS-84", "GCJ-02(高德/百度)"], 
                                 index=0 if st.session_state.coord_system == "WGS-84" else 1)
        st.session_state.coord_system = coord_sys.split("(")[0]

        # A点输入
        st.write("#### 起点A")
        a_lat = st.number_input("纬度", value=st.session_state.point_A["lat"], format="%.6f", key="a_lat")
        a_lng = st.number_input("经度", value=st.session_state.point_A["lng"], format="%.6f", key="a_lng")
        if st.button("设置A点"):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}

        # B点输入
        st.write("#### 终点B")
        b_lat = st.number_input("纬度", value=st.session_state.point_B["lat"], format="%.6f", key="b_lat")
        b_lng = st.number_input("经度", value=st.session_state.point_B["lng"], format="%.6f", key="b_lng")
        if st.button("设置B点"):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}

        # 飞行高度
        height = st.number_input("设定飞行高度 (m)", value=st.session_state.flight_height, step=5.0)
        st.session_state.flight_height = height

    with col2:
        st.subheader("系统状态")
        a_status = "✅ A点已设" if st.session_state.point_A["set"] else "❌ A点未设"
        b_status = "✅ B点已设" if st.session_state.point_B["set"] else "❌ B点未设"
        st.write(a_status)
        st.write(b_status)
        st.write(f"飞行高度: {st.session_state.flight_height} m")

    # 地图显示（3D，使用pydeck）
    st.subheader("3D 航线地图")
    
    # 获取当前A/B点（原始坐标系）
    a_original = (st.session_state.point_A["lng"], st.session_state.point_A["lat"])
    b_original = (st.session_state.point_B["lng"], st.session_state.point_B["lat"])
    
    # 转换为WGS-84用于地图显示
    a_wgs84 = convert_to_wgs84(a_original[1], a_original[0], st.session_state.coord_system)
    b_wgs84 = convert_to_wgs84(b_original[1], b_original[0], st.session_state.coord_system)
    
    # 构建地图图层
    layers = []
    
    # 起点终点标记（绿色和红色圆点）
    if st.session_state.point_A["set"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"lng": a_wgs84[0], "lat": a_wgs84[1], "color": [0, 255, 0], "size": 100}],
            get_position='[lng, lat]',
            get_color='color',
            get_radius='size',
            pickable=True,
            auto_highlight=True,
        ))
    if st.session_state.point_B["set"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"lng": b_wgs84[0], "lat": b_wgs84[1], "color": [255, 0, 0], "size": 100}],
            get_position='[lng, lat]',
            get_color='color',
            get_radius='size',
        ))
    
    # AB连线（带高度，体现3D）
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        line_data = [{
            "path": [[a_wgs84[0], a_wgs84[1], st.session_state.flight_height],
                     [b_wgs84[0], b_wgs84[1], st.session_state.flight_height]],
            "color": [255, 255, 0]
        }]
        layers.append(pdk.Layer(
            "LineLayer",
            data=line_data,
            get_path='path',
            get_color='color',
            get_width=5,
            width_min_pixels=2,
            pickable=True,
        ))
    
    # 障碍物（红色圆形，带半透明填充，并可显示高度块）
    # 注意障碍物坐标我们直接使用WGS-84（默认障碍物为WGS-84，但校园内偏差不大）
    obs_data = []
    for obs in obstacles_wgs84:
        # 将障碍物坐标转换为WGS-84（已经是WGS-84，但为了统一，不再转换）
        obs_data.append({
            "lng": obs["lng"],
            "lat": obs["lat"],
            "radius": obs["radius"],
            "name": obs["name"]
        })
    if obs_data:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=obs_data,
            get_position='[lng, lat]',
            get_radius='radius',
            get_fill_color="[255, 0, 0, 100]",
            get_line_color="[255, 0, 0]",
            pickable=True,
            auto_highlight=True,
            radius_scale=1,
        ))
        # 添加文本标签（pydeck不支持原生文本，但可用ScatterplotLayer + tooltip）
    
    # 设置视图（中心点取A和B的中点）
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        center_lng = (a_wgs84[0] + b_wgs84[0]) / 2
        center_lat = (a_wgs84[1] + b_wgs84[1]) / 2
    elif st.session_state.point_A["set"]:
        center_lng, center_lat = a_wgs84
    else:
        center_lng, center_lat = 118.749, 32.233  # 校园中心
    
    view_state = pdk.ViewState(
        longitude=center_lng,
        latitude=center_lat,
        zoom=16,
        pitch=45,      # 倾斜角度，实现3D效果
        bearing=0,
        height=500
    )
    
    r = pdk.Deck(layers=layers, initial_view_state=view_state, tooltip={"text": "{name}"})
    st.pydeck_chart(r)
    
    st.info("💡 提示：红色圆圈为障碍物，绿色为起点A，红色为终点B，黄色线为规划航线（飞行高度已设定）。地图支持缩放、倾斜（鼠标右键拖拽）查看3D效果。")

# ---------------------------- 飞行监控页面 ----------------------------
else:  # 飞行监控
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测并绘制折线图，3秒未收到自动报警")
    
    # 自动刷新（仅在运行时）
    if st.session_state.running:
        st_autorefresh(interval=1000, key="heartbeat_refresh")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 启动模拟"):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with col2:
        if st.button("⏸️ 暂停/恢复"):
            st.session_state.running = not st.session_state.running
    with col3:
        if st.button("🛑 停止模拟"):
            reset_monitor()
    
    # 心跳生成逻辑
    if st.session_state.running:
        now = time.time()
        last = st.session_state.last_ts
        if last is None:
            add_heartbeat(1, now)
        else:
            diff = now - last
            if diff >= 1.0:
                n = min(int(diff), 5)  # 最多补偿5个
                for i in range(n):
                    new_seq = st.session_state.seq + 1
                    sim_ts = last + (i + 1)
                    add_heartbeat(new_seq, sim_ts)
        
        # 超时检测
        if st.session_state.last_ts and (time.time() - st.session_state.last_ts) > 3.0:
            st.session_state.alert_msg = f"⚠️ 连接超时！已 {time.time() - st.session_state.last_ts:.1f} 秒未收到心跳"
        else:
            st.session_state.alert_msg = ""
    
    # 状态显示
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
    
    # 折线图
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        df = df.sort_values("时间")
        st.subheader("📈 心跳序号变化趋势")
        st.line_chart(df.set_index("时间")["序号"])
    else:
        st.info("尚未收到任何心跳包，请点击「启动模拟」")
    
    # 表格
    if st.session_state.records:
        df_table = pd.DataFrame(st.session_state.records, columns=["心跳序号", "时间戳"])
        df_table["接收时间"] = df_table["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        df_table = df_table[["心跳序号", "接收时间"]]
        st.subheader("📋 心跳包记录（最近20条）")
        st.dataframe(df_table, use_container_width=True)
    else:
        st.info("暂无记录")
