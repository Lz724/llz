import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static, st_folium
from branca.element import Figure
import branca.colormap as cm
import numpy as np

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
    """坐标转换统一接口"""
    if from_system == to_system:
        return lng, lat
    if from_system == "WGS-84" and to_system == "GCJ-02":
        return wgs84_to_gcj02(lng, lat)
    if from_system == "GCJ-02" and to_system == "WGS-84":
        return gcj02_to_wgs84(lng, lat)
    return lng, lat

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
    if "obstacles" not in st.session_state:
        # 障碍物列表，每个障碍物为 {lat, lng, radius, name}
        st.session_state.obstacles = [
            {"lat": 32.2328, "lng": 118.7485, "radius": 30, "name": "教学楼"},
            {"lat": 32.2335, "lng": 118.7492, "radius": 35, "name": "图书馆"},
            {"lat": 32.2330, "lng": 118.7500, "radius": 28, "name": "实验楼"},
            {"lat": 32.2325, "lng": 118.7495, "radius": 25, "name": "食堂"},
            {"lat": 32.2332, "lng": 118.7488, "radius": 20, "name": "行政楼"},
        ]

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

def create_map():
    """创建带障碍物和航线规划的folium地图"""
    # 获取当前坐标系统下的A、B点（用于显示，保持用户输入的坐标系）
    a_lng, a_lat = st.session_state.point_A["lng"], st.session_state.point_A["lat"]
    b_lng, b_lat = st.session_state.point_B["lng"], st.session_state.point_B["lat"]
    
    # 地图中心点（如果有A点则居中到A，否则居中校园中心）
    if st.session_state.point_A["set"]:
        center_lat, center_lng = a_lat, a_lng
    elif st.session_state.point_B["set"]:
        center_lat, center_lng = b_lat, b_lng
    else:
        center_lat, center_lng = 32.2332, 118.7492
    
    # 创建地图（使用OpenStreetMap，支持缩放）
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=16,
        control_scale=True
    )
    
    # 添加全屏按钮
    folium.plugins.Fullscreen().add_to(m)
    
    # 添加测量工具（方便圈选障碍物）
    folium.plugins.MeasureControl().add_to(m)
    
    # 绘制A点（绿色）
    if st.session_state.point_A["set"]:
        folium.Marker(
            location=[a_lat, a_lng],
            popup=f"起点A<br>纬度: {a_lat:.6f}<br>经度: {a_lng:.6f}",
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
            tooltip="起点A"
        ).add_to(m)
        
        # 添加圆形标记突出显示
        folium.Circle(
            radius=15,
            location=[a_lat, a_lng],
            color="green",
            fill=True,
            fill_opacity=0.3
        ).add_to(m)
    
    # 绘制B点（红色）
    if st.session_state.point_B["set"]:
        folium.Marker(
            location=[b_lat, b_lng],
            popup=f"终点B<br>纬度: {b_lat:.6f}<br>经度: {b_lng:.6f}",
            icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
            tooltip="终点B"
        ).add_to(m)
        
        folium.Circle(
            radius=15,
            location=[b_lat, b_lng],
            color="red",
            fill=True,
            fill_opacity=0.3
        ).add_to(m)
    
    # 绘制AB连线（航线）
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        points = [[a_lat, a_lng], [b_lat, b_lng]]
        folium.PolyLine(
            points,
            color="yellow",
            weight=4,
            opacity=0.8,
            popup=f"规划航线 (高度: {st.session_state.flight_height}m)"
        ).add_to(m)
        
        # 添加方向箭头（中点位置）
        mid_lat = (a_lat + b_lat) / 2
        mid_lng = (a_lng + b_lng) / 2
        folium.plugins.PolygonDrawToolbar().add_to(m)  # 辅助圈选工具
    
    # 绘制障碍物（红色半透明圆）
    for obs in st.session_state.obstacles:
        # 将障碍物坐标转换到当前用户坐标系进行显示
        obs_lng_display, obs_lat_display = convert_coords(
            obs["lat"], obs["lng"], 
            from_system="WGS-84", 
            to_system=st.session_state.coord_system
        )
        
        folium.Circle(
            radius=obs["radius"],
            location=[obs_lat_display, obs_lng_display],
            color="red",
            fill=True,
            fill_opacity=0.4,
            popup=f"⚠️ {obs['name']}<br>半径: {obs['radius']}m",
            tooltip=obs["name"]
        ).add_to(m)
        
        # 添加文字标签
        folium.map.Marker(
            [obs_lat_display, obs_lng_display],
            icon=folium.DivIcon(
                html=f'<div style="font-size: 10pt; color: red; font-weight: bold;">{obs["name"]}</div>'
            )
        ).add_to(m)
    
    # 添加图例
    legend_html = '''
    <div style="position: fixed; bottom: 50px; right: 50px; z-index: 1000; background-color: white; padding: 10px; border: 2px solid gray; border-radius: 5px;">
        <p style="margin: 0;"><span style="color: green;">●</span> 起点A</p>
        <p style="margin: 0;"><span style="color: red;">●</span> 终点B</p>
        <p style="margin: 0;"><span style="color: yellow;">━</span> 规划航线</p>
        <p style="margin: 0;"><span style="color: red; background-color: rgba(255,0,0,0.4);">●</span> 障碍物</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

# ---------------------------- 页面导航 ----------------------------
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# ============================ 航线规划页面 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("规划无人机飞行路线，设置起点/终点及飞行高度，地图显示障碍物并支持圈选")
    
    # 坐标系设置区域
    st.sidebar.markdown("---")
    st.sidebar.subheader("坐标系设置")
    coord_sys = st.sidebar.selectbox(
        "输入坐标系", 
        ["WGS-84", "GCJ-02(高德/百度)"],
        index=0 if st.session_state.coord_system == "WGS-84" else 1
    )
    st.session_state.coord_system = coord_sys.split("(")[0]
    
    # 主控制面板
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("控制面板")
        
        # 起点A输入
        st.write("#### 起点A")
        a_lat = st.number_input(
            "纬度", 
            value=st.session_state.point_A["lat"], 
            format="%.6f", 
            key="a_lat_input"
        )
        a_lng = st.number_input(
            "经度", 
            value=st.session_state.point_A["lng"], 
            format="%.6f", 
            key="a_lng_input"
        )
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.success("✅ 起点A已设置")
        
        # 终点B输入
        st.write("#### 终点B")
        b_lat = st.number_input(
            "纬度", 
            value=st.session_state.point_B["lat"], 
            format="%.6f", 
            key="b_lat_input"
        )
        b_lng = st.number_input(
            "经度", 
            value=st.session_state.point_B["lng"], 
            format="%.6f", 
            key="b_lng_input"
        )
        if st.button("🎯 设置B点", use_container_width=True):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.success("✅ 终点B已设置")
        
        # 飞行参数
        st.write("#### 飞行参数")
        height = st.number_input(
            "设定飞行高度 (m)", 
            value=st.session_state.flight_height, 
            step=5.0,
            key="height_input"
        )
        st.session_state.flight_height = height
        
        # 障碍物管理
        st.write("#### 障碍物管理")
        if st.button("➕ 添加新障碍物", use_container_width=True):
            st.session_state.show_add_obstacle = True
        
        if "show_add_obstacle" in st.session_state and st.session_state.show_add_obstacle:
            with st.expander("添加障碍物", expanded=True):
                obs_name = st.text_input("障碍物名称", "新障碍物")
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f")
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f")
                obs_radius = st.number_input("半径 (m)", value=25, step=5)
                if st.button("确认添加"):
                    st.session_state.obstacles.append({
                        "lat": obs_lat,
                        "lng": obs_lng,
                        "radius": obs_radius,
                        "name": obs_name
                    })
                    st.session_state.show_add_obstacle = False
                    st.success(f"已添加障碍物: {obs_name}")
                    st.rerun()
    
    with col2:
        st.subheader("系统状态")
        a_status = "✅ A点已设" if st.session_state.point_A["set"] else "❌ A点未设"
        b_status = "✅ B点已设" if st.session_state.point_B["set"] else "❌ B点未设"
        
        # 状态卡片
        st.info(f"**{a_status}**")
        st.info(f"**{b_status}**")
        st.info(f"**✈️ 飞行高度: {st.session_state.flight_height} m**")
        st.info(f"**🗺️ 当前坐标系: {st.session_state.coord_system}**")
        st.info(f"**🚧 障碍物数量: {len(st.session_state.obstacles)}**")
        
        # 显示障碍物列表
        if st.session_state.obstacles:
            with st.expander("障碍物列表"):
                for i, obs in enumerate(st.session_state.obstacles):
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.write(f"{i+1}. {obs['name']} (半径:{obs['radius']}m)")
                    with col_b:
                        if st.button("删除", key=f"del_{i}"):
                            st.session_state.obstacles.pop(i)
                            st.rerun()
    
    # 地图显示区域（可交互）
    st.subheader("🗺️ 地图（支持缩放、圈选障碍物）")
    st.markdown("💡 **提示**：地图支持鼠标滚轮缩放、拖拽平移。右侧工具栏可进行测量和圈选。")
    
    # 创建并显示地图
    m = create_map()
    folium_static(m, width=1000, height=600)
    
    # 使用说明
    with st.expander("📖 使用说明"):
        st.markdown("""
        ### 功能说明：
        1. **设置起点/终点**：在左侧控制面板输入经纬度坐标，点击按钮设置
        2. **坐标系选择**：在侧边栏选择输入坐标系（WGS-84 或 GCJ-02/高德）
        3. **地图操作**：
           - 鼠标滚轮：缩放地图
           - 鼠标拖拽：平移地图
           - 右上角全屏按钮：全屏显示
           - 右侧测量工具：测量距离和面积
        4. **障碍物**：
           - 红色半透明圆圈代表障碍物
           - 可以添加新的障碍物或删除现有障碍物
           - 障碍物默认位于校园内，AB点之间
        5. **航线规划**：黄色线连接A点和B点，显示规划航线
        """)

# ============================ 飞行监控页面 ============================
else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测并绘制折线图，3秒未收到自动报警")
    
    # 自动刷新（使用HTML meta标签）
    if st.session_state.running:
        st.markdown('<meta http-equiv="refresh" content="1">', unsafe_allow_html=True)
    
    # 控制按钮
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 启动模拟", use_container_width=True):
            reset_monitor()
            st.session_state.running = True
            add_heartbeat(1, time.time())
    with col2:
        if st.button("⏸️ 暂停/恢复", use_container_width=True):
            st.session_state.running = not st.session_state.running
    with col3:
        if st.button("🛑 停止模拟", use_container_width=True):
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
                n = min(int(diff), 5)  # 补偿最多5个心跳
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
        st.write(f"**无人机状态：{status_text}**")
    
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
        st.line_chart(df.set_index("时间")["序号"], use_container_width=True)
    else:
        st.info("📭 尚未收到任何心跳包，请点击「启动模拟」")
    
    # 表格显示
    if st.session_state.records:
        df_table = pd.DataFrame(st.session_state.records, columns=["心跳序号", "时间戳"])
        df_table["接收时间"] = df_table["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        df_table = df_table[["心跳序号", "接收时间"]]
        st.subheader("📋 心跳包记录（最近20条）")
        st.dataframe(df_table, use_container_width=True, height=400)
    else:
        st.info("📋 暂无记录")
