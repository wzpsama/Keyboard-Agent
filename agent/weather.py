"""天气传感器（Open-Meteo 免费无 key，尽力而为，防阻塞）。

后台线程每 FETCH_INTERVAL 秒拉一次当前天气 + 温度并缓存。get_weather() 立即返回
缓存（未抓到 / 无网络 / 失败 → None），天气交互据此自动静默，绝不阻塞主循环。

定位：默认**按公网 IP 自动定位**（无需配置）；想强制指定城市时，把 WEATHER_CITY
设为城市名（支持中文 / 日文 / 英文）。定位结果缓存一次，之后只按经纬度轮询天气。
仅用标准库，跨平台（Linux 单测也能 import）。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

WEATHER_CITY = ""               # 留空 = 按 IP 自动定位；填城市名 = 强制指定
FETCH_INTERVAL = 30 * 60        # 拉取间隔（秒）
_TIMEOUT = 8                    # 单次网络超时（秒）

# WMO 天气码 → (中文描述, 分类)
_WMO = {
    0: ("晴", "clear"), 1: ("晴", "clear"), 2: ("多云", "cloudy"), 3: ("阴", "cloudy"),
    45: ("雾", "fog"), 48: ("雾凇", "fog"),
    51: ("毛毛雨", "rain"), 53: ("小雨", "rain"), 55: ("中雨", "rain"),
    56: ("冻雨", "rain"), 57: ("冻雨", "rain"),
    61: ("小雨", "rain"), 63: ("中雨", "rain"), 65: ("大雨", "rain"),
    66: ("冻雨", "rain"), 67: ("冻雨", "rain"),
    71: ("小雪", "snow"), 73: ("中雪", "snow"), 75: ("大雪", "snow"), 77: ("雪粒", "snow"),
    80: ("阵雨", "rain"), 81: ("阵雨", "rain"), 82: ("强阵雨", "rain"),
    85: ("阵雪", "snow"), 86: ("阵雪", "snow"),
    95: ("雷雨", "thunder"), 96: ("雷雨", "thunder"), 99: ("雷雨冰雹", "thunder"),
}

_cache = None          # 天气 dict(code/desc/cat/temp) or None
_loc = None            # 已解析位置 dict(lat/lon/city) or None（缓存一次）
_enabled = True
_poller = None


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "vega-keyboard-agent/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _geocode_city(city: str) -> tuple:
    """城市名 → (lat, lon)。"""
    q = urllib.parse.quote(city)
    geo = _get(f"https://geocoding-api.open-meteo.com/v1/search"
               f"?name={q}&count=1&format=json&language=en")
    results = geo.get("results") or []
    if not results:
        raise RuntimeError(f"城市未找到：{city}")
    return float(results[0]["latitude"]), float(results[0]["longitude"])


def _ip_geolocate() -> tuple:
    """公网 IP → (lat, lon, city)。多个免费源依次尝试，都失败则抛异常。"""
    # 源 1：ipwho.is（HTTPS、无 key，字段 latitude/longitude/city）
    try:
        j = _get("https://ipwho.is/")
        lat, lon = j.get("latitude"), j.get("longitude")
        if j.get("success", True) and lat is not None and lon is not None:
            return float(lat), float(lon), j.get("city") or ""
    except Exception:
        pass
    # 源 2：ip-api.com（HTTP、无 key，字段 lat/lon/city，非常稳）
    j = _get("http://ip-api.com/json")
    if j.get("status") != "success":
        raise RuntimeError(f"IP 定位失败：{j.get('message', 'unknown')}")
    return float(j["lat"]), float(j["lon"]), j.get("city") or ""


def _resolve_location() -> dict:
    """解析位置（缓存一次）。城市名优先，否则按 IP 自动定位。"""
    global _loc
    if _loc is not None:
        return _loc
    if WEATHER_CITY:
        lat, lon = _geocode_city(WEATHER_CITY)
        _loc = {"lat": lat, "lon": lon, "city": WEATHER_CITY}
    else:
        lat, lon, city = _ip_geolocate()
        _loc = {"lat": lat, "lon": lon, "city": city}
    return _loc


def _fetch() -> dict:
    loc = _resolve_location()
    w = _get(f"https://api.open-meteo.com/v1/forecast"
             f"?latitude={loc['lat']}&longitude={loc['lon']}"
             f"&current=temperature_2m,weather_code&timezone=auto")
    cur = w.get("current") or {}
    code = int(cur.get("weather_code", 0))
    desc, cat = _WMO.get(code, ("未知", "cloudy"))
    return {"code": code, "desc": desc, "cat": cat,
            "temp": round(float(cur.get("temperature_2m", 0.0)))}


class _WeatherPoller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="weather-poller")

    def run(self):
        global _cache
        first = True
        while _enabled:
            try:
                _cache = _fetch()
                if first:
                    loc = _loc or {}
                    city = loc.get("city") or WEATHER_CITY or "自动定位"
                    print(f"[weather] 首次拉取成功（{city}）："
                          f"{_cache['desc']} {_cache['temp']}°C")
                    first = False
            except Exception as e:
                print(f"[weather] 拉取失败（{e}），稍后重试")
            time.sleep(FETCH_INTERVAL)


def start_poller() -> None:
    global _poller
    if _poller is None:
        _poller = _WeatherPoller()
        _poller.start()
        print(f"[weather] 天气轮询已启动"
              f"（{'城市=' + WEATHER_CITY if WEATHER_CITY else '按 IP 自动定位'}）")


def get_weather():
    """当前天气 dict(code/desc/cat/temp)，未抓到返回 None。立即返回，不阻塞。"""
    return _cache
