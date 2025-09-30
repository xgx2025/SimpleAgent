import json
import requests
from lazyllm import fc_register, LOG

# --- 1. 基础配置（Web API 核心信息）---
# ① 你的高德API Key
AMAP_API_KEY = "你的高德API Key"
# ② 高德Web服务API基础域名（固定不可改）
AMAP_WEB_BASE_URL = "https://restapi.amap.com/v3"


def send_web_api_request(api_path: str, params: dict = None, method: str = "GET"):
    """
    发送高德Web服务API请求（通用核心函数）
    :param api_path: API子路径（如"/weather/weatherInfo"）
    :param params: 请求参数（自动补充API Key）
    :param method: 请求方法（GET/POST，Web API以GET为主）
    :return: 接口返回结果（成功返回数据，失败返回错误信息）
    """
    if params is None:
        params = {}
    params["key"] = AMAP_API_KEY

    try:
        full_url = f"{AMAP_WEB_BASE_URL}{api_path}"
        
        # 发送请求
        if method.upper() == "GET":
            response = requests.get(full_url, params=params, timeout=10)
        else:
            response = requests.post(full_url, data=params, timeout=10)
        
        # 检查HTTP状态码（非2xx直接抛异常）
        response.raise_for_status()
        # 解析JSON响应（Web API返回格式统一为JSON）
        result = response.json()

        # 处理Web API业务错误（状态码status=0表示失败）
        if result.get("status") != "1":
            error_info = result.get("info", "未知错误")
            error_code = result.get("infocode", "未知错误码")
            LOG.error(f"[AMAP Web API] 业务错误 {error_code}: {error_info}")
            return f"Error: 高德API错误({error_code}) - {error_info}"

        # 返回业务数据（不同接口数据在不同字段，统一提取核心内容）
        return result

    # 捕获网络/解析等异常
    except requests.exceptions.RequestException as e:
        LOG.error(f"[AMAP Web API] 网络请求失败: {str(e)}")
        return f"Error: 网络请求失败 - {str(e)}"
    except json.JSONDecodeError:
        LOG.error(f"[AMAP Web API] 解析响应失败: 服务器返回非JSON内容 - {response.text[:100]}...")
        return f"Error: 服务器返回无效数据 - {response.text[:100]}..."


# --- 2. 工具函数实现 ---
@fc_register("tool")
def search_poi(keywords: str, city: str = "全国"):
    """
    POI关键字搜索（替代MCP的maps_text_search）
    :param keywords: 查询关键字（如"肯德基"）
    :param city: 查询城市（如"北京"，默认"全国"）
    :return: POI列表（含名称、地址、经纬度等信息）
    """
    params = {
        "keywords": keywords,
        "city": city,
        "pageSize": 10,  # 默认返回10条结果
        "extensions": "all"  # 返回详细信息（含经纬度、电话等）
    }
    return send_web_api_request("/place/text", params)


@fc_register("tool")
def plan_driving_route(origin: str, destination: str):
    """
    驾车路径规划（替代MCP的maps_direction_driving）
    :param origin: 起点经纬度（格式"经度,纬度"，如"116.481181,39.989792"）
    :param destination: 终点经纬度（格式同起点）
    :return: 驾车路线（含距离、时间、转向提示等）
    """
    params = {
        "origin": origin,
        "destination": destination,
        "strategy": 0,  # 0=最快路线，1=最短路线，2=避开高速
        "extensions": "all"  # 返回详细路线节点
    }
    return send_web_api_request("/direction/driving", params)


@fc_register("tool")
def get_weather(city: str):
    """
    城市天气查询（替代MCP的maps_weather）
    :param city: 城市名（如"北京"）或城市ADCode（如"110000"）
    :return: 实时天气+未来3天预报
    """
    params = {
        "city": city,
        "extensions": "all"  # "base"=仅实时天气，"all"=实时+预报
    }
    return send_web_api_request("/weather/weatherInfo", params)


@fc_register("tool")
def generate_private_map(org_name: str, line_list: list):
    """
    生成私人行程地图（替代MCP的maps_schema_personal_map）
    本地化实现：生成可跳转高德地图的行程链接，含所有景点标注
    :param org_name: 行程名称（如"我的北京一日游"）
    :param line_list: 行程列表（格式同原MCP）
    :return: 高德地图行程链接（点击可在App打开）
    """
    try:
        # 提取所有景点的经纬度和名称
        points = []
        for line in line_list:
            for point in line.get("pointInfoList", []):
                lon = point.get("lon")
                lat = point.get("lat")
                name = point.get("name", "未命名景点")
                if lon and lat:
                    # 格式：名称,经度,纬度
                    points.append(f"{name},{lon},{lat}")
        
        if not points:
            return "Error: 行程列表中无有效景点坐标"
        
        # 构造高德地图行程链接（支持多景点标注）
        points_str = "|".join(points)
        # 高德地图URL Scheme：支持在App中打开并显示多景点
        map_url = (
            f"amapuri://route/plan?sourceApplication=智能旅游规划助手"
            f"&dname={org_name}"
            f"&dlatlng={points[0].split(',')[2]},{points[0].split(',')[1]}"  # 默认终点为第一个景点
            f"&points={points_str}"  # 所有景点坐标
            f"&dev=0"  # 0=使用高德坐标系，1=使用GPS坐标系
        )
        return {
            "行程名称": org_name,
            "景点数量": len(points),
            "高德地图打开链接": map_url,
            "提示": "复制链接到浏览器或高德地图App打开，可查看完整行程"
        }
    except Exception as e:
        LOG.error(f"[generate_private_map] 生成行程地图失败: {str(e)}")
        return f"Error: 生成行程地图失败 - {str(e)}"


@fc_register("tool")
def navigate_to(lon: str, lat: str, name: str = "目的地"):
    """
    生成一键导航链接（替代MCP的maps_schema_navi）
    :param lon: 目的地经度
    :param lat: 目的地纬度
    :param name: 目的地名称
    :return: 高德地图导航链接（点击跳转App导航）
    """
    # 高德地图导航URL Scheme（支持直接唤起导航）
    navi_url = (
        f"amapuri://navi?sourceApplication=智能旅游规划助手"
        f"&lat={lat}"  # 纬度
        f"&lon={lon}"  # 经度
        f"&poiname={name}"  # 目的地名称
        f"&dev=0"  # 0=高德坐标系，1=GPS坐标系
        f"&style=2"  # 2=驾车导航，1=公交，3=步行
    )
    return {
        "目的地": name,
        "经纬度": f"{lon},{lat}",
        "一键导航链接": navi_url,
        "使用说明": "在手机上点击链接，或复制到高德地图App打开"
    }


@fc_register("tool")
def get_address_by_location(location: str):
    """
    逆地理编码（经纬度转地址，替代MCP的maps_regeocode）
    :param location: 经纬度（格式"经度,纬度"，如"116.481181,39.989792"）
    :return: 详细地址（含省、市、区、街道、门牌号）
    """
    params = {
        "location": location,
        "extensions": "all"  # 返回详细地址+周边POI（精简用"base"）
    }
    return send_web_api_request("/geocode/regeo", params)


@fc_register("tool")
def get_location_by_address(address: str, city: str = None):
    """
    地理编码（地址转经纬度，替代MCP的maps_geo）
    :param address: 详细地址（如"北京市朝阳区天安门广场"）
    :param city: 城市名（可选，提高编码准确性，如"北京"）
    :return: 经纬度+地址解析结果
    """
    params = {
        "address": address,
        "city": city  # 可选，限定城市范围
    }
    return send_web_api_request("/geocode/geo", params)