import json
import os
import folium
import geopandas as gpd
import pandas as pd
import requests
from folium.plugins import Search
import streamlit as st
from streamlit_folium import st_folium

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="Sistem Monitoring Udara Kota Tegal",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# API Key IQAir
IQAIR_API_KEY = "a5b7cffb-5b98-49ef-ace5-7dbf6a0bb782"

# Helper Konversi Kode Cuaca WMO ke Teks
WMO_WEATHER_CODES = {
    0: "Cerah",
    1: "Cerah Berawan",
    2: "Berawan Sebagian",
    3: "Berawan",
    45: "Kabut",
    48: "Kabut Rime",
    51: "Gerimis Ringan",
    53: "Gerimis Sedang",
    55: "Gerimis Lebat",
    61: "Hujan Ringan",
    63: "Hujan Sedang",
    65: "Hujan Lebat",
    80: "Hujan Showers Ringan",
    81: "Hujan Showers Sedang",
    82: "Hujan Showers Lebat",
    95: "Badai Petir",
}

def get_wmo_description(code):
    return WMO_WEATHER_CODES.get(code, "Cuaca Tidak Terdefinisi")

def aqi_to_pm25_conc(aqi):
    if aqi <= 50:
        return round((aqi / 50) * 12.0, 1)
    elif aqi <= 100:
        return round(12.1 + ((aqi - 51) / 49) * (35.4 - 12.1), 1)
    elif aqi <= 150:
        return round(35.5 + ((aqi - 101) / 49) * (55.4 - 35.5), 1)
    elif aqi <= 200:
        return round(55.5 + ((aqi - 151) / 49) * (55.4 - 55.5), 1)
    else:
        return round(150.5 + ((aqi - 201) / 99) * (250.4 - 150.5), 1)

# 1. AMBIL DATA KUALITAS UDARA (PM2.5, OZON), SUHU & PRAKIRAAN CUACA
@st.cache_data(ttl=600)
def fetch_iqair_air_quality(api_key):
    locations = [
        {"id": "stn_1", "stasiun": "Tegal Barat", "lat": -6.8642, "lon": 109.1251, "city": "Tegal", "state": "Central Java", "country": "Indonesia"},
        {"id": "stn_2", "stasiun": "Tegal Timur", "lat": -6.8689, "lon": 109.1438, "city": "Tegal", "state": "Central Java", "country": "Indonesia"},
        {"id": "stn_3", "stasiun": "Tegal Selatan", "lat": -6.8872, "lon": 109.1302, "city": "Tegal", "state": "Central Java", "country": "Indonesia"},
        {"id": "stn_4", "stasiun": "Margadana", "lat": -6.8580, "lon": 109.1025, "city": "Tegal", "state": "Central Java", "country": "Indonesia"},
    ]

    data_list = []
    iqair_cache = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    global_online = True
    try:
        requests.get("https://1.1.1.1", timeout=3)
    except Exception:
        global_online = False

    for item in locations:
        pm25_val = None
        o3_val = None
        temp_val = None
        weather_desc = "Tidak diketahui"
        forecast_tomorrow = "Tidak tersedia"
        humidity_val = "-"
        wind_speed_val = "-"
        stasiun_online = False

        if global_online:
            try:
                coord_key = f"{round(item['lat'], 2)},{round(item['lon'], 2)}"
                if coord_key in iqair_cache:
                    res_data = iqair_cache[coord_key]
                else:
                    iqair_url = f"https://api.airvisual.com/v2/nearest_city?lat={item['lat']}&lon={item['lon']}&key={api_key}"
                    resp = requests.get(iqair_url, headers=headers, timeout=8)
                    if resp.status_code == 200:
                        res_data = resp.json()
                        iqair_cache[coord_key] = res_data
                    else:
                        city_url = f"https://api.airvisual.com/v2/city?city={item['city']}&state={item['state']}&country={item['country']}&key={api_key}"
                        resp_city = requests.get(city_url, headers=headers, timeout=8)
                        res_data = resp_city.json() if resp_city.status_code == 200 else None

                if res_data and res_data.get("status") == "success":
                    stasiun_online = True
                    current_data = res_data["data"]["current"]
                    pollution = current_data.get("pollution", {})
                    weather = current_data.get("weather", {})

                    if "tp" in weather:
                        temp_val = round(float(weather["tp"]), 1)
                    if "hu" in weather:
                        humidity_val = f"{weather['hu']}%"
                    if "ws" in weather:
                        wind_speed_val = f"{weather['ws']} m/s"

                    if "conc" in pollution and pollution["conc"] is not None:
                        pm25_val = round(float(pollution["conc"]), 1)
                    elif "p2" in pollution and "conc" in pollution["p2"]:
                        pm25_val = round(float(pollution["p2"]["conc"]), 1)
                    elif "aqius" in pollution:
                        pm25_val = aqi_to_pm25_conc(pollution["aqius"])

                    if "o3" in pollution:
                        if isinstance(pollution["o3"], dict) and "conc" in pollution["o3"]:
                            o3_val = round(float(pollution["o3"]["conc"]), 1)
                        elif isinstance(pollution["o3"], (int, float)):
                            o3_val = round(float(pollution["o3"]), 1)
            except Exception:
                pass

            try:
                om_url = f"https://api.open-meteo.com/v1/forecast?latitude={item['lat']}&longitude={item['lon']}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto"
                resp_om = requests.get(om_url, timeout=10)
                if resp_om.status_code == 200:
                    stasiun_online = True
                    om_data = resp_om.json()
                    curr_om = om_data.get("current", {})
                    daily_om = om_data.get("daily", {})

                    if temp_val is None and "temperature_2m" in curr_om:
                        temp_val = round(float(curr_om["temperature_2m"]), 1)
                    if "weather_code" in curr_om:
                        weather_desc = get_wmo_description(curr_om["weather_code"])
                    if humidity_val == "-" and "relative_humidity_2m" in curr_om:
                        humidity_val = f"{curr_om['relative_humidity_2m']}%"
                    if wind_speed_val == "-" and "wind_speed_10m" in curr_om:
                        wind_speed_val = f"{curr_om['wind_speed_10m']} km/h"
                    if "weather_code" in daily_om and len(daily_om["weather_code"]) > 1:
                        code_tom = daily_om["weather_code"][1]
                        t_max = daily_om["temperature_2m_max"][1]
                        t_min = daily_om["temperature_2m_min"][1]
                        rain_prob = daily_om.get("precipitation_probability_max", [0, 0])[1]
                        forecast_tomorrow = f"{get_wmo_description(code_tom)} ({t_min}°C - {t_max}°C, Hujan: {rain_prob}%)"
            except Exception:
                pass

            if pm25_val is None or o3_val is None:
                try:
                    om_aq_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={item['lat']}&longitude={item['lon']}&current=pm2_5,ozone"
                    resp_aq = requests.get(om_aq_url, timeout=10)
                    if resp_aq.status_code == 200:
                        stasiun_online = True
                        curr_aq = resp_aq.json().get("current", {})
                        if pm25_val is None and "pm2_5" in curr_aq and curr_aq["pm2_5"] is not None:
                            pm25_val = round(float(curr_aq["pm2_5"]), 1)
                        if o3_val is None and "ozone" in curr_aq and curr_aq["ozone"] is not None:
                            o3_val = round(float(curr_aq["ozone"]), 1)
                except Exception:
                    pass

        st_data = {
            "id": item["id"],
            "stasiun": item["stasiun"],
            "lat": item["lat"],
            "lon": item["lon"],
            "status_stasiun": "ONLINE" if stasiun_online else "OFFLINE",
            "pm25": pm25_val if pm25_val is not None else "-",
            "o3": o3_val if o3_val is not None else "-",
            "temp": temp_val if temp_val is not None else "-",
            "cuaca_sekarang": weather_desc,
            "ramalan_besok": forecast_tomorrow,
            "kelembapan": humidity_val,
            "kecepatan_angin": wind_speed_val,
        }

        if not stasiun_online or pm25_val is None:
            st_data["kategori"] = "Offline"
            st_data["color"] = "#757575"
            st_data["bg_badge"] = "#EEEEEE"
        else:
            pm = float(pm25_val)
            if pm <= 15.5:
                st_data["kategori"] = "Baik"
                st_data["color"] = "#03AC0E"
                st_data["bg_badge"] = "#E8F5E9"
            elif pm <= 55.4:
                st_data["kategori"] = "Sedang"
                st_data["color"] = "#FF9800"
                st_data["bg_badge"] = "#FFF3E0"
            elif pm <= 150.4:
                st_data["kategori"] = "Tidak Sehat"
                st_data["color"] = "#EF144A"
                st_data["bg_badge"] = "#FFEBEE"
            else:
                st_data["kategori"] = "Sangat Tidak Sehat"
                st_data["color"] = "#6A1B9A"
                st_data["bg_badge"] = "#F3E5F5"

        data_list.append(st_data)

    df = pd.DataFrame(data_list)
    has_online_station = any(df["status_stasiun"] == "ONLINE") if not df.empty else False
    return df, has_online_station

# 2. MEMUAT DATA PETA OFFLINE DARI "kota_tegal.geojson"
path_peta_qgis = "kota_tegal.geojson"
gdf_kota_tegal = None
if os.path.exists(path_peta_qgis):
    try:
        gdf_kota_tegal = gpd.read_file(path_peta_qgis)
    except Exception:
        pass

# 3. AMBIL DATA REAL-TIME DARI API
df_udara, is_live_data = fetch_iqair_air_quality(IQAIR_API_KEY)

# 4. BUAT PETA FOLIUM
peta = folium.Map(
    location=[-6.8671, 109.1372], zoom_start=12, zoom_control=False, tiles=None
)

if gdf_kota_tegal is not None:
    kolom_kemungkinan = ["NAMOBJ", "WADMKK", "WADMKC", "KECAMATAN", "nama", "Name", "NAMA_KOT"]
    kolom_pencarian = None
    for col in kolom_kemungkinan:
        if col in gdf_kota_tegal.columns:
            kolom_pencarian = col
            break

    if not kolom_pencarian:
        cols_text = gdf_kota_tegal.select_dtypes(include=["object"]).columns
        kolom_pencarian = cols_text[0] if len(cols_text) > 0 else gdf_kota_tegal.columns[0]

    geojson_layer = folium.GeoJson(
        gdf_kota_tegal,
        name="Batas Administrasi Kota Tegal",
        style_function=lambda feature: {
            "fillColor": "#E8F5E9",
            "color": "#03AC0E",
            "weight": 1.5,
            "fillOpacity": 0.6,
        },
        highlight_function=lambda feature: {
            "fillColor": "#03AC0E",
            "color": "#02880B",
            "weight": 2.5,
            "fillOpacity": 0.8,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[kolom_pencarian],
            aliases=["Wilayah:"],
            style="font-family: Arial, sans-serif; font-size: 13px; padding: 6px 12px; border-radius: 8px;",
        ),
    ).add_to(peta)

    peta.fit_bounds(geojson_layer.get_bounds())

    Search(
        layer=geojson_layer,
        geom_type="Polygon",
        placeholder="Cari kecamatan...",
        collapsed=False,
        search_label=kolom_pencarian,
        weight=4,
        color="#EF144A",
        fillColor="#EF144A",
        fillOpacity=0.4,
        zoom_on_click=True,
        position="topleft",
    ).add_to(peta)

# Plot Marker Sensor & List Item UI
panel_items_html = ""
if not df_udara.empty:
    for _, row in df_udara.iterrows():
        status_badge_color = "#03AC0E" if row["status_stasiun"] == "ONLINE" else "#757575"
        status_badge_bg = "#E8F5E9" if row["status_stasiun"] == "ONLINE" else "#EEEEEE"

        popup_html = f"""
