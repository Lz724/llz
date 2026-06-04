import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static
from geopy.distance import geodesic

# ---------------------------- 坐标系转换算法 ----------------------------
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
    if out_of_china(lng, lat):
        return lng, lat
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
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat

def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

def convert_coords(lat, lng, from_system, to_system="WGS-84"):
    if from_system == to_system:
        return lng, lat
    if from_system == "WGS-84" and to_system == "GCJ-02":
        return wgs84_to_gcj02(lng, lat)
    if from_system == "GCJ-02" and to_system == "WGS-84":
        return gcj02_to_wgs84(lng, lat)
    return lng, lat

# ---------------------------- 初始化 Session State ----------------------------
def init_state():
    if "running" not in st.session_state:
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_ts = None
        st.session_state.records = []
        st.session_state.alert_msg = ""
    if "coord_system" not in st.session_state:
        st.session_state.coord_system = "GCJ-02"
    if "point_A" not in st.session_state:
        st.session_state.point_A = {"lat": 32.2322, "lng": 118.749, "set": False}
    if "point_B" not in st.session_state:
        st.session_state.point_B = {"lat": 32.2343, "lng": 118.749, "set": False}
    if "flight_height" not in st.session_state:
        st.session_state.flight_height = 50.0
    if "obstacles" not in st.session_state:
        st.session_state.obstacles = [
            {"lat": 32.2328, "lng": 118.7485, "radius": 30, "name": "教学楼"},
            {"lat": 32.2335, "lng": 118.7492, "radius": 35, "name": "图书馆"},
            {"lat": 32.2330, "lng": 118.7500, "radius": 28, "name": "实验楼"},
            {"lat": 32.2325, "lng": 118.7495, "radius": 25, "name": "食堂"},
            {"lat": 32.2318, "lng": 118.7482, "radius": 22, "name": "体育馆"},
        ]
    if "map_zoom" not in st.session_state:
        st.session_state.map_zoom = 16

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

def create_folium_map():
    if st.session_state.point_A["set"]:
        center_lat = st.session_state.point_A["lat"]
        center_lng = st.session_state.point_A["lng"]
    elif st.session_state.point_B["set"]:
        center_lat = st.session_state.point_B["lat"]
        center_lng = st.session_state.point_B["lng"]
    else:
        center_lat = 32.2332
        center_lng = 118.7492

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles='OpenStreetMap'
    )

    # A点
    if st.session_state.point_A["set"]:
        folium.Marker(
            location=[st.session_state.point_A["lat"], st.session_state.point_A["lng"]],
            popup="起点A",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)
        folium.Circle(
            radius=20,
            location=[st.session_state.point_A["lat"], st.session_state.point_A["lng"]],
            color="green", fill=True, fill_opacity=0.2
        ).add_to(m)

    # B点
    if st.session_state.point_B["set"]:
        folium.Marker(
            location=[st.session_state.point_B["lat"], st.session_state.point_B["lng"]],
            popup="终点B",
            icon=folium.Icon(color="red", icon="flag-checkered"),
        ).add_to(m)
        folium.Circle(
            radius=20,
            location=[st.session_state.point_B["lat"], st.session_state.point_B["lng"]],
            color="red", fill=True, fill_opacity=0.2
        ).add_to(m)

    # 航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        points = [
            [st.session_state.point_A["lat"], st.session_state.point_A["lng"]],
            [st.session_state.point_B["lat"], st.session_state.point_B["lng"]]
        ]
        folium.PolyLine(points, color="yellow", weight=5, opacity=0.8).add_to(m)

    # 障碍物
    for obs in st.session_state.obstacles:
        folium.Circle(
            radius=obs["radius"],
            location=[obs["lat"], obs["lng"]],
            color="red", fill=True, fill_opacity=0.4,
            popup=obs["name"]
        ).add_to(m)

    return m

# ---------------------------- 页面导航 ----------------------------
st.set_page_config(page_title="无人机地面站", layout="wide")
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# ============================ 航线规划 ============================
if page == "航线规划":
    st.title("🗺️ 无人机航线规划")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("坐标设置")
        a_lat = st.number_input("A点纬度", value=st.session_state.point_A["lat"], format="%.6f")
        a_lng = st.number_input("A点经度", value=st.session_state.point_A["lng"], format="%.6f")
        if st.button("✅ 设置起点A"):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.rerun()

        b_lat = st.number_input("B点纬度", value=st.session_state.point_B["lat"], format="%.6f")
        b_lng = st.number_input("B点经度", value=st.session_state.point_B["lng"], format="%.6f")
        if st.button("✅ 设置终点B"):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.rerun()

        st.session_state.flight_height = st.number_input("飞行高度(m)", value=50.0)

        st.subheader("障碍物管理")
        obs_name = st.text_input("障碍物名称", "新障碍物")
        obs_lat = st.number_input("障碍物纬度", value=32.2330, format="%.6f")
        obs_lng = st.number_input("障碍物经度", value=118.7495, format="%.6f")
        obs_radius = st.number_input("半径(m)", value=25)
        if st.button("➕ 添加障碍物"):
            st.session_state.obstacles.append({
                "lat": obs_lat, "lng": obs_lng, "radius": obs_radius, "name": obs_name
            })
            st.rerun()

    with col2:
        st.subheader("状态信息")
        if st.session_state.point_A["set"]:
            st.success("✅ A点已设置")
        if st.session_state.point_B["set"]:
            st.success("✅ B点已设置")

        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            dis = geodesic((a_lat, a_lng), (b_lat, b_lng)).meters
            st.info(f"📏 航线距离：{dis:.1f} 米")

    st.subheader("地图预览")
    m = create_folium_map()
    folium_static(m, width=1000, height=600)

# ============================ 飞行监控 ============================
else:
    st.title("🛸 无人机心跳监控")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 启动"):
            reset_monitor()
            st.session_state.running = True
    with c2:
        if st.button("⏸️ 暂停/继续"):
            st.session_state.running = not st.session_state.running
    with c3:
        if st.button("🛑 停止"):
            reset_monitor()

    if st.session_state.running:
        now = time.time()
        last = st.session_state.last_ts
        if last is None or now - last >= 1.0:
            add_heartbeat(st.session_state.seq + 1, now)

    # 状态
    if st.session_state.last_ts:
        gap = time.time() - st.session_state.last_ts
        if gap > 3:
            st.error(f"⚠️ 超时！{gap:.1f} 秒未收到心跳")
        else:
            st.success(f"✅ 正常，最后心跳 {gap:.1f} 秒前")

    # 图表
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间"])
        df["时间"] = pd.to_datetime(df["时间"], unit="s")
        st.line_chart(df.set_index("时间")["序号"])

        df_show = df.copy()
        df_show["接收时间"] = df_show["时间"].dt.strftime("%H:%M:%S")
        st.dataframe(df_show[["序号", "接收时间"]], height=300)
    else:
        st.info("请点击启动开始监控")

st.markdown("---")
st.caption("© 无人机地面站系统 | 稳定版")
