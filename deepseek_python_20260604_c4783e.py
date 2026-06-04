import streamlit as st
import pandas as pd
import time
import math
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
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
            {"lat": 32.2328, "lng": 118.7485, "radius": 30, "name": "教学楼", "height": 20},
            {"lat": 32.2335, "lng": 118.7492, "radius": 35, "name": "图书馆", "height": 25},
            {"lat": 32.2330, "lng": 118.7500, "radius": 28, "name": "实验楼", "height": 22},
            {"lat": 32.2325, "lng": 118.7495, "radius": 25, "name": "食堂", "height": 15},
            {"lat": 32.2320, "lng": 118.7480, "radius": 20, "name": "体育馆", "height": 18},
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

def create_3d_map():
    """创建交互式3D地图使用Plotly"""
    
    fig = go.Figure()
    
    # 获取A、B点的WGS-84坐标
    a_wgs_lng, a_wgs_lat = None, None
    b_wgs_lng, b_wgs_lat = None, None
    
    # 添加A点（绿色）
    if st.session_state.point_A["set"]:
        a_wgs_lng, a_wgs_lat = convert_coords(
            st.session_state.point_A["lat"], 
            st.session_state.point_A["lng"], 
            st.session_state.coord_system, 
            "WGS-84"
        )
        fig.add_trace(go.Scatter3d(
            x=[a_wgs_lng],
            y=[a_wgs_lat],
            z=[0],
            mode='markers+text',
            marker=dict(size=10, color='green', symbol='circle'),
            text=['起点A'],
            textposition='top center',
            name='起点A',
            hovertemplate='起点A<br>经度: %{x:.6f}<br>纬度: %{y:.6f}<extra></extra>'
        ))
        
        # 添加A点柱状指示
        fig.add_trace(go.Scatter3d(
            x=[a_wgs_lng, a_wgs_lng],
            y=[a_wgs_lat, a_wgs_lat],
            z=[0, 50],
            mode='lines',
            line=dict(color='green', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 添加B点（红色）
    if st.session_state.point_B["set"]:
        b_wgs_lng, b_wgs_lat = convert_coords(
            st.session_state.point_B["lat"], 
            st.session_state.point_B["lng"], 
            st.session_state.coord_system, 
            "WGS-84"
        )
        fig.add_trace(go.Scatter3d(
            x=[b_wgs_lng],
            y=[b_wgs_lat],
            z=[0],
            mode='markers+text',
            marker=dict(size=10, color='red', symbol='circle'),
            text=['终点B'],
            textposition='top center',
            name='终点B',
            hovertemplate='终点B<br>经度: %{x:.6f}<br>纬度: %{y:.6f}<extra></extra>'
        ))
        
        # 添加B点柱状指示
        fig.add_trace(go.Scatter3d(
            x=[b_wgs_lng, b_wgs_lng],
            y=[b_wgs_lat, b_wgs_lat],
            z=[0, 50],
            mode='lines',
            line=dict(color='red', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 添加航线（AB连线，带飞行高度）
    if st.session_state.point_A["set"] and st.session_state.point_B["set"]:
        # 地面投影线
        fig.add_trace(go.Scatter3d(
            x=[a_wgs_lng, b_wgs_lng],
            y=[a_wgs_lat, b_wgs_lat],
            z=[0, 0],
            mode='lines',
            line=dict(color='gray', width=2, dash='dash'),
            name='地面投影',
            hovertinfo='skip'
        ))
        
        # 空中航线
        fig.add_trace(go.Scatter3d(
            x=[a_wgs_lng, b_wgs_lng],
            y=[a_wgs_lat, b_wgs_lat],
            z=[st.session_state.flight_height, st.session_state.flight_height],
            mode='lines+markers',
            line=dict(color='yellow', width=5),
            marker=dict(size=5, color='yellow'),
            name=f'航线 (高度: {st.session_state.flight_height}m)',
            hovertemplate='航线<br>高度: %{z}m<extra></extra>'
        ))
        
        # 添加垂直连接线
        fig.add_trace(go.Scatter3d(
            x=[a_wgs_lng, a_wgs_lng],
            y=[a_wgs_lat, a_wgs_lat],
            z=[0, st.session_state.flight_height],
            mode='lines',
            line=dict(color='lightgreen', width=2, dash='dot'),
            showlegend=False,
            hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter3d(
            x=[b_wgs_lng, b_wgs_lng],
            y=[b_wgs_lat, b_wgs_lat],
            z=[0, st.session_state.flight_height],
            mode='lines',
            line=dict(color='lightcoral', width=2, dash='dot'),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 添加障碍物（圆柱体表示）
    for obs in st.session_state.obstacles:
        obs_wgs_lng, obs_wgs_lat = convert_coords(obs["lat"], obs["lng"], "WGS-84", "WGS-84")
        
        # 创建圆柱体表示障碍物
        theta = np.linspace(0, 2*np.pi, 50)
        r = obs["radius"] / 111000  # 转换为度（近似）
        x_cylinder = obs_wgs_lng + r * np.cos(theta)
        y_cylinder = obs_wgs_lat + r * np.sin(theta)
        z_cylinder = np.full_like(theta, obs.get("height", 20))
        
        # 圆柱体底部
        fig.add_trace(go.Scatter3d(
            x=x_cylinder,
            y=y_cylinder,
            z=np.zeros_like(theta),
            mode='lines',
            line=dict(color='red', width=2),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # 圆柱体顶部
        fig.add_trace(go.Scatter3d(
            x=x_cylinder,
            y=y_cylinder,
            z=z_cylinder,
            mode='lines',
            line=dict(color='red', width=2),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # 圆柱体侧面线条
        for i in range(0, len(theta), 10):
            fig.add_trace(go.Scatter3d(
                x=[x_cylinder[i], x_cylinder[i]],
                y=[y_cylinder[i], y_cylinder[i]],
                z=[0, z_cylinder[i]],
                mode='lines',
                line=dict(color='red', width=1),
                showlegend=False,
                hoverinfo='skip'
            ))
        
        # 障碍物中心标记
        fig.add_trace(go.Scatter3d(
            x=[obs_wgs_lng],
            y=[obs_wgs_lat],
            z=[obs.get("height", 20)],
            mode='markers+text',
            marker=dict(size=8, color='red', symbol='x'),
            text=[obs['name']],
            textposition='top center',
            name=obs['name'],
            hovertemplate=f'{obs["name"]}<br>高度: {obs.get("height", 20)}m<br>半径: {obs["radius"]}m<extra></extra>'
        ))
    
    # 设置地图布局
    # 确定地图中心
    if st.session_state.point_A["set"]:
        center_lng, center_lat = a_wgs_lng, a_wgs_lat
    elif st.session_state.point_B["set"]:
        center_lng, center_lat = b_wgs_lng, b_wgs_lat
    else:
        center_lng, center_lat = 118.7492, 32.2332
    
    # 计算地图范围
    lng_range = 0.005
    lat_range = 0.005
    
    fig.update_layout(
        title=dict(
            text="3D 航线规划地图",
            x=0.5,
            xanchor='center',
            font=dict(size=20)
        ),
        scene=dict(
            xaxis=dict(
                title="经度",
                range=[center_lng - lng_range, center_lng + lng_range],
                tickformat=".6f"
            ),
            yaxis=dict(
                title="纬度",
                range=[center_lat - lat_range, center_lat + lat_range],
                tickformat=".6f"
            ),
            zaxis=dict(
                title="高度 (m)",
                range=[0, max(100, st.session_state.flight_height + 50)],
            ),
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5),
                center=dict(x=0, y=0, z=0),
                up=dict(x=0, y=0, z=1)
            ),
            aspectmode='manual',
            aspectratio=dict(x=1.2, y=1.2, z=0.5)
        ),
        showlegend=True,
        legend=dict(
            x=0.8,
            y=0.9,
            bgcolor='rgba(255, 255, 255, 0.8)',
            bordercolor='black',
            borderwidth=1
        ),
        height=600,
        margin=dict(l=0, r=0, t=50, b=0)
    )
    
    # 添加地形背景（使用散点图模拟地形）
    # 创建网格点
    lng_grid = np.linspace(center_lng - lng_range, center_lng + lng_range, 20)
    lat_grid = np.linspace(center_lat - lat_range, center_lat + lat_range, 20)
    Lng, Lat = np.meshgrid(lng_grid, lat_grid)
    # 模拟地形高度（简单起伏）
    Z = 10 * np.sin((Lng - center_lng) * 1000) * np.cos((Lat - center_lat) * 1000) + 5
    
    fig.add_trace(go.Surface(
        x=Lng,
        y=Lat,
        z=Z,
        colorscale='Viridis',
        opacity=0.3,
        showscale=False,
        name='地形',
        hovertemplate='地面高度: %{z:.1f}m<extra></extra>'
    ))
    
    return fig

# ---------------------------- 页面导航 ----------------------------
st.sidebar.title("导航")
page = st.sidebar.radio("功能页面", ["航线规划", "飞行监控"])

# ============================ 航线规划页面 ============================
if page == "航线规划":
    st.title("🗺️ 航线规划")
    st.markdown("规划无人机飞行路线，设置起点/终点及飞行高度，3D地图显示障碍物")
    
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
    st.sidebar.info("💡 3D地图操作提示:\n• 鼠标拖拽旋转视角\n• 右键拖拽平移\n• 滚轮缩放")
    
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
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_A = {"lat": a_lat, "lng": a_lng, "set": True}
            st.success("✅ 起点A已设置")
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
        if st.button("🎯 设置B点", use_container_width=True):
            st.session_state.point_B = {"lat": b_lat, "lng": b_lng, "set": True}
            st.success("✅ 终点B已设置")
            st.rerun()
        
        # 飞行高度
        st.write("#### 飞行参数")
        height = st.number_input(
            "设定飞行高度 (m)", 
            value=st.session_state.flight_height, 
            step=5.0
        )
        st.session_state.flight_height = height
        
        # 添加障碍物
        st.write("#### 障碍物管理")
        with st.expander("➕ 添加新障碍物"):
            obs_name = st.text_input("障碍物名称", "新障碍物")
            obs_lat = st.number_input("纬度", value=32.2330, format="%.6f", key="obs_lat")
            obs_lng = st.number_input("经度", value=118.7495, format="%.6f", key="obs_lng")
            obs_radius = st.number_input("半径 (m)", value=25, step=5, key="obs_radius")
            obs_height = st.number_input("高度 (m)", value=20, step=5, key="obs_height")
            if st.button("确认添加", key="add_obs"):
                st.session_state.obstacles.append({
                    "lat": obs_lat,
                    "lng": obs_lng,
                    "radius": obs_radius,
                    "name": obs_name,
                    "height": obs_height
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
        
        # 障碍物列表
        if st.session_state.obstacles:
            st.write("**🚧 障碍物列表**")
            for i, obs in enumerate(st.session_state.obstacles):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"{i+1}. {obs['name']} (半径:{obs['radius']}m, 高:{obs.get('height',20)}m)")
                with col_b:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.obstacles.pop(i)
                        st.rerun()
    
    # 3D地图显示
    st.subheader("🗺️ 交互式3D地图")
    st.markdown("💡 **操作提示**：鼠标拖拽旋转视角 | 右键拖拽平移 | 滚轮缩放 | 点击标记查看详情")
    
    # 创建并显示地图
    try:
        fig = create_3d_map()
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"地图加载出错: {str(e)}")
        st.info("请确保已设置A点和B点，或检查坐标是否正确")
    
    # 使用说明
    with st.expander("📖 详细使用说明"):
        st.markdown("""
        ### 🎯 功能说明
        
        **1. 设置起点/终点**
        - 在左侧控制面板输入经纬度坐标
        - 点击"设置A点"或"设置B点"按钮
        - 支持 WGS-84 和 GCJ-02 两种坐标系
        
        **2. 飞行参数**
        - 设置飞行高度（单位：米）
        - 航线会显示在对应高度上
        
        **3. 障碍物管理**
        - 系统预设了校园内的障碍物（教学楼、图书馆等）
        - 可以添加新的障碍物（需要输入经纬度、半径、高度）
        - 可以删除现有障碍物
        
        **4. 3D地图操作**
        - **鼠标左键拖拽**：旋转3D视角
        - **鼠标右键拖拽**：平移地图
        - **鼠标滚轮**：缩放地图
        - **点击标记**：查看详细信息
        
        **5. 坐标系转换**
        - **WGS-84**：国际标准坐标系（GPS使用）
        - **GCJ-02**：高德/百度地图使用的坐标系（火星坐标系）
        - 系统会自动转换坐标进行显示
        
        **6. 地图元素说明**
        - 🟢 **绿色点**：起点A
        - 🔴 **红色点**：终点B
        - 🟡 **黄色线**：规划航线（显示在设定高度）
        - 🔴 **红色圆柱**：障碍物（显示高度和半径）
        - 🌈 **彩色地形**：地形起伏示意
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
        df_table = df_table[["心跳序号", "接收时间"]]
        st.subheader("📋 心跳包记录（最近20条）")
        st.dataframe(df_table, use_container_width=True, height=400)
    else:
        st.info("📋 暂无记录")
