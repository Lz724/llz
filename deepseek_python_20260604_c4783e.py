import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import folium
from streamlit_folium import folium_static
from branca.element import Figure
import json

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
    """创建交互式地图使用Folium"""
    
    # 确定地图中心点
    if st.session_state.point_A["set"]:
        center_lat = st.session_state.point_A["lat"]
        center_lng = st.session_state.point_A["lng"]
    elif st.session_state.point_B["set"]:
        center_lat = st.session_state.point_B["lat"]
        center_lng = st.session_state.point_B["lng"]
    else:
        center_lat = 32.2332
        center_lng = 118.7492
    
    # 创建地图（使用多种瓦片服务确保显示）
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles='OpenStreetMap'
    )
    
    # 添加备用瓦片（可选择）
    folium.TileLayer('CartoDB positron', name='浅色地图').add_to(m)
    folium.TileLayer('CartoDB dark_matter', name='深色地图').add_to(m)
    
    # 添加全屏按钮
    folium.plugins.Fullscreen(position='topright').add_to(m)
    
    # 添加测量工具
    folium.plugins.MeasureControl(
        position='topleft',
        primary_length_unit='meters',
        secondary_length_unit='kilometers',
        primary_area_unit='sqmeters'
    ).add_to(m)
    
    # 添加绘图工具（用于圈选障碍物）
    draw = folium.plugins.Draw(
        export=True,
        position='topleft',
        draw_options={
            'polyline': True,
            'polygon': True,
            'circle': True,
            'rectangle': True,
            'marker': True,
            'circlemarker': True
        }
    )
    draw.add_to(m)
    
    # 添加A点（绿色）
    if st.session_state.point_A["set"]:
        # 获取显示坐标（用户选择的坐标系）
        display_lng, display_lat = st.session_state.point_A["lng"], st.session_state.point_A["lat"]
        
        # 添加标记
        folium.Marker(
            location=[display_lat, display_lng],
            popup=f"""
            <div style="min-width: 150px;">
                <h4>起点A</h4>
                <p><b>纬度:</b> {display_lat:.6f}<br>
                <b>经度:</b> {display_lng:.6f}<br>
                <b>坐标系:</b> {st.session_state.coord_system}</p>
            </div>
            """,
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
            tooltip="起点A"
        ).add_to(m)
        
        # 添加圆形高亮
        folium.Circle(
            radius=20,
            location=[display_lat, display_lng],
            color="green",
            fill=True,
            fill_opacity=0.2,
            weight=3
        ).add_to(m)
        
        # 添加信息框
        folium.map.Marker(
            [display_lat, display_lng],
            icon=folium.DivIcon(
                html=f'<div style="font-size: 12pt; color: green; font-weight: bold;">A</div>'
            )
        ).add_to(m)
    
    # 添加B点（红色）
    if st.session_state.point_B["set"]:
        display_lng, display_lat = st.session_state.point_B["lng"], st.session_state.point_B["lat"]
        
        folium.Marker(
            location=[display_lat, display_lng],
            popup=f"""
            <div style="min-width: 150px;">
                <h4>终点B</h4>
                <p><b>纬度:</b> {display_lat:.6f}<br>
                <b>经度:</b> {display_lng:.6f}<br>
                <b>坐标系:</b> {st.session_state.coord_system}</p>
            </div>
            """,
            icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
            tooltip="终点B"
        ).add_to(m)
        
        folium.Circle(
            radius=20,
            location=[display_lat, display_lng],
            color="red",
            fill=True,
            fill_opacity=0.2,
            weight=3
        ).add_to(m)
        
        folium.map.Marker(
            [display_lat, display_lng],
            icon=folium.DivIcon(
                html='<div style="font-size: 12pt; color: red; font-weight: bold;">B</div>'
            )
        ).add_to(m)
    
    # 添加AB航线
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        a_lng, a_lat = st.session_state.point_A["lng"], st.session_state.point_A["lat"]
        b_lng, b_lat = st.session_state.point_B["lng"], st.session_state.point_B["lat"]
        
        points = [[a_lat, a_lng], [b_lat, b_lng]]
        
        # 航线
        folium.PolyLine(
            points,
            color="yellow",
            weight=5,
            opacity=0.8,
            popup=f"规划航线 (高度: {st.session_state.flight_height}m)",
            tooltip=f"航线高度: {st.session_state.flight_height}m"
        ).add_to(m)
        
        # 添加方向箭头（中点位置）
        mid_lat = (a_lat + b_lat) / 2
        mid_lng = (a_lng + b_lng) / 2
        
        # 添加距离标注
        from geopy.distance import geodesic
        distance = geodesic((a_lat, a_lng), (b_lat, b_lng)).meters
        folium.map.Marker(
            [mid_lat, mid_lng],
            icon=folium.DivIcon(
                html=f'<div style="background-color: white; padding: 2px 5px; border-radius: 5px; border: 1px solid yellow;">{distance:.0f}m</div>'
            )
        ).add_to(m)
    
    # 添加障碍物（红色半透明圆）
    for obs in st.session_state.obstacles:
        # 障碍物坐标转换到当前用户坐标系
        obs_lng_display, obs_lat_display = convert_coords(
            obs["lat"], obs["lng"], 
            from_system="WGS-84", 
            to_system=st.session_state.coord_system
        )
        
        # 绘制障碍物圆形区域
        folium.Circle(
            radius=obs["radius"],
            location=[obs_lat_display, obs_lng_display],
            color="red",
            fill=True,
            fill_opacity=0.4,
            weight=2,
            popup=f"""
            <div>
                <b>⚠️ {obs['name']}</b><br>
                半径: {obs['radius']}m<br>
                纬度: {obs_lat_display:.6f}<br>
                经度: {obs_lng_display:.6f}
            </div>
            """,
            tooltip=f"{obs['name']} (半径: {obs['radius']}m)"
        ).add_to(m)
        
        # 添加障碍物中心标记
        folium.RegularPolygonMarker(
            location=[obs_lat_display, obs_lng_display],
            popup=obs['name'],
            color='red',
            fill_color='red',
            number_of_sides=4,
            radius=8
        ).add_to(m)
    
    # 添加图例控制
    legend_html = '''
    <div style="position: fixed; bottom: 50px; right: 50px; z-index: 1000; background-color: white; padding: 10px; border: 2px solid #333; border-radius: 5px; font-size: 12px;">
        <p style="margin: 0; font-weight: bold;">图例</p>
        <p style="margin: 0;"><span style="color: green;">●</span> 起点A</p>
        <p style="margin: 0;"><span style="color: red;">●</span> 终点B</p>
        <p style="margin: 0;"><span style="color: yellow;">━</span> 规划航线</p>
        <p style="margin: 0;"><span style="color: red; background-color: rgba(255,0,0,0.4);">●</span> 障碍物</p>
        <p style="margin: 0;"><span style="color: blue;">📏</span> 测量工具</p>
        <p style="margin: 0;"><span style="color: purple;">✏️</span> 绘图工具</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # 添加坐标显示控件
    folium.plugins.MousePosition().add_to(m)
    
    return m

# ---------------------------- 页面导航 ----------------------------
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# ============================ 航线规划页面 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("规划无人机飞行路线，设置起点/终点及飞行高度，地图显示障碍物并支持圈选")
    
    # 侧边栏设置
    st.sidebar.markdown("---")
    st.sidebar.subheader("坐标系设置")
    coord_sys = st.sidebar.selectbox(
        "输入坐标系", 
        ["WGS-84", "GCJ-02(高德/百度)"],
        index=0 if st.session_state.coord_system == "WGS-84" else 1
    )
    st.session_state.coord_system = coord_sys.split("(")[0]
    
    st.sidebar.subheader("地图控制")
    zoom = st.sidebar.slider("地图缩放级别", 10, 20, st.session_state.map_zoom, 1)
    st.session_state.map_zoom = zoom
    
    st.sidebar.info("💡 **地图工具说明**:\n\n• 右上角: 全屏按钮\n• 左上角: 测量距离/面积\n• 左上角: 绘图工具(圈选障碍物)\n• 右下角: 图层切换")
    
    # 主控制面板
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("控制面板")
        
        # 起点A
        st.write("#### 起点A")
        a_lat = st.number_input(
            "纬度", 
            value=st.session_state.point_A["lat"], 
            format="%.6f", 
            key="a_lat"
        )
        a_lng = st.number_input(
            "经度", 
            value=st.session_state.point_A["lng"], 
            format="%.6f", 
            key="a_lng"
        )
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📍 设置A点", use_container_width=True):
                st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
                st.success("✅ 起点A已设置")
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 清除A点", use_container_width=True):
                st.session_state.point_A["set"] = False
                st.rerun()
        
        # 终点B
        st.write("#### 终点B")
        b_lat = st.number_input(
            "纬度", 
            value=st.session_state.point_B["lat"], 
            format="%.6f", 
            key="b_lat"
        )
        b_lng = st.number_input(
            "经度", 
            value=st.session_state.point_B["lng"], 
            format="%.6f", 
            key="b_lng"
        )
        col_btn3, col_btn4 = st.columns(2)
        with col_btn3:
            if st.button("🎯 设置B点", use_container_width=True):
                st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
                st.success("✅ 终点B已设置")
                st.rerun()
        with col_btn4:
            if st.button("🗑️ 清除B点", use_container_width=True):
                st.session_state.point_B["set"] = False
                st.rerun()
        
        # 飞行高度
        st.write("#### 飞行参数")
        height = st.number_input(
            "设定飞行高度 (m)", 
            value=st.session_state.flight_height, 
            step=5.0,
            help="无人机飞行的高度，会影响航线显示"
        )
        st.session_state.flight_height = height
        
        # 添加障碍物
        st.write("#### 障碍物管理")
        with st.expander("➕ 添加新障碍物", expanded=False):
            obs_name = st.text_input("障碍物名称", "新障碍物")
            col_obs1, col_obs2 = st.columns(2)
            with col_obs1:
                obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            with col_obs2:
                obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径 (m)", value=25, step=5, key="obs_radius")
            if st.button("✅ 确认添加", key="add_obs"):
                st.session_state.obstacles.append({
                    "lat": obs_lat,
                    "lng": obs_lng,
                    "radius": obs_radius,
                    "name": obs_name
                })
                st.success(f"已添加障碍物: {obs_name}")
                st.rerun()
    
    with col2:
        st.subheader("系统状态")
        
        # 显示状态卡片
        if st.session_state.point_A["set"]:
            st.success(f"✅ **A点已设**\n\n📍 纬度: {st.session_state.point_A['lat']:.6f}\n📍 经度: {st.session_state.point_A['lng']:.6f}")
        else:
            st.warning("❌ **A点未设** - 请输入坐标并点击设置")
        
        if st.session_state.point_B["set"]:
            st.success(f"✅ **B点已设**\n\n📍 纬度: {st.session_state.point_B['lat']:.6f}\n📍 经度: {st.session_state.point_B['lng']:.6f}")
        else:
            st.warning("❌ **B点未设** - 请输入坐标并点击设置")
        
        st.info(f"✈️ **飞行高度**: {st.session_state.flight_height} m")
        st.info(f"🗺️ **当前坐标系**: {st.session_state.coord_system}")
        
        # 统计信息
        total_distance = 0
        if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
            try:
                from geopy.distance import geodesic
                a = (st.session_state.point_A["lat"], st.session_state.point_A["lng"])
                b = (st.session_state.point_B["lat"], st.session_state.point_B["lng"])
                total_distance = geodesic(a, b).meters
                st.info(f"📏 **航线距离**: {total_distance:.1f} m")
            except:
                pass
        
        # 障碍物列表
        if st.session_state.obstacles:
            st.write("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} (半径:{obs['radius']}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 地图显示区域
    st.subheader("🗺️ 交互式地图（支持缩放、圈选障碍物）")
    st.markdown("💡 **操作提示**：")
    st.markdown("- 🔍 鼠标滚轮缩放 | 🖱️ 鼠标拖拽平移 | 🎯 点击标记查看详情")
    st.markdown("- 📏 左上角测量工具：可测量距离和面积（用于圈选障碍物范围）")
    st.markdown("- ✏️ 左上角绘图工具：可绘制多边形圈选障碍物区域")
    st.markdown("- 🗺️ 右下角可切换地图样式（浅色/深色）")
    
    # 创建并显示地图
    try:
        m = create_folium_map()
        folium_static(m, width=1000, height=600)
    except Exception as e:
        st.error(f"地图加载出错: {str(e)}")
        st.info("请刷新页面重试，或检查网络连接")
    
    # 使用说明
    with st.expander("📖 详细使用说明", expanded=False):
        st.markdown("""
        ### 🎯 功能说明
        
        **1. 设置起点/终点**
        - 在左侧控制面板输入经纬度坐标
        - 点击"设置A点"或"设置B点"按钮
        - 支持 WGS-84 和 GCJ-02 两种坐标系
        - 可随时清除已设置的点
        
        **2. 飞行参数**
        - 设置飞行高度（单位：米）
        - 航线会自动更新显示
        
        **3. 障碍物管理**
        - 系统预设了校园内的障碍物（教学楼、图书馆、实验楼、食堂、体育馆）
        - 可以添加新的障碍物（需要输入名称、经纬度、半径）
        - 可以删除现有障碍物
        
        **4. 地图工具使用**
        - **全屏按钮**（右上角）：全屏显示地图
        - **测量工具**（左上角尺子图标）：点击后在地图上点击两点测量距离，点击三点以上测量面积
        - **绘图工具**（左上角铅笔图标）：可以绘制多边形、圆形等来圈选障碍物区域
        - **图层切换**（右下角）：可切换浅色/深色地图样式
        
        **5. 坐标系转换**
        - **WGS-84**：国际标准坐标系（GPS使用）
        - **GCJ-02**：高德/百度地图使用的坐标系（火星坐标系）
        - 系统会自动处理坐标转换，确保地图显示准确
        
        **6. 地图元素说明**
        - 🟢 **绿色标记**：起点A
        - 🔴 **红色标记**：终点B
        - 🟡 **黄色线**：规划航线
        - 🔴 **红色半透明圆**：障碍物（显示名称和半径）
        - 📏 **蓝色标记**：测量结果
        """)

# ============================ 飞行监控页面 ============================
else:
    st.title("🛸 无人机心跳监测系统")
    st.markdown("模拟无人机每秒发送心跳包，地面站实时监测并绘制折线图，3秒未收到自动报警")
    
    # 自动刷新
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
                n = min(int(diff), 5)
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
    
    # 实时心跳指示器
    if st.session_state.running and st.session_state.last_ts:
        time_since_last = time.time() - st.session_state.last_ts
        if time_since_last < 1:
            st.success(f"💓 最后心跳: {time_since_last:.1f}秒前")
        elif time_since_last < 3:
            st.warning(f"💓 最后心跳: {time_since_last:.1f}秒前")
        else:
            st.error(f"💔 最后心跳: {time_since_last:.1f}秒前")
    
    # 折线图
    if st.session_state.records:
        df = pd.DataFrame(st.session_state.records, columns=["序号", "时间戳"])
        df["时间"] = pd.to_datetime(df["时间戳"], unit="s")
        df = df.sort_values("时间")
        st.subheader("📈 心跳序号变化趋势")
        st.line_chart(df.set_index("时间")["序号"], use_container_width=True)
    else:
        st.info("📭 尚未收到任何心跳包，请点击「启动模拟」")
    
    # 表格
    if st.session_state.records:
        df_table = pd.DataFrame(st.session_state.records, columns=["心跳序号", "时间戳"])
        df_table["接收时间"] = df_table["时间戳"].apply(lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S"))
        df_table["延迟(ms)"] = df_table["时间戳"].diff().fillna(0) * 1000
        df_table = df_table[["心跳序号", "接收时间", "延迟(ms)"]]
        st.subheader("📋 心跳包记录（最近20条）")
        st.dataframe(df_table, use_container_width=True, height=400)
    else:
        st.info("📋 暂无记录")

# 底部信息
st.markdown("---")
st.markdown("© 2024 无人机地面站系统 | 支持坐标系转换 | 实时心跳监测")
