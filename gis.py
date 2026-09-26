import json
import os
import webbrowser
import folium
import geopandas as gpd
import pandas as pd
import requests
from folium.plugins import Search

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
def fetch_iqair_air_quality(api_key):
  locations = [
      {
          "id": "stn_1",
          "stasiun": "Tegal Barat",
          "lat": -6.8642,
          "lon": 109.1251,
          "city": "Tegal",
          "state": "Central Java",
          "country": "Indonesia",
      },
      {
          "id": "stn_2",
          "stasiun": "Tegal Timur",
          "lat": -6.8689,
          "lon": 109.1438,
          "city": "Tegal",
          "state": "Central Java",
          "country": "Indonesia",
      },
      {
          "id": "stn_3",
          "stasiun": "Tegal Selatan",
          "lat": -6.8872,
          "lon": 109.1302,
          "city": "Tegal",
          "state": "Central Java",
          "country": "Indonesia",
      },
      {
          "id": "stn_4",
          "stasiun": "Margadana",
          "lat": -6.8580,
          "lon": 109.1025,
          "city": "Tegal",
          "state": "Central Java",
          "country": "Indonesia",
      },
  ]

  data_list = []
  iqair_cache = {}
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

  global_online = True
  try:
    requests.get("https://1.1.1.1", timeout=3)
  except Exception:
    print("[INFO] Mode Offline Terdeteksi (Tidak Ada Koneksi Internet).")
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
            res_data = (
                resp_city.json() if resp_city.status_code == 200 else None
            )

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
            if (
                isinstance(pollution["o3"], dict)
                and "conc" in pollution["o3"]
            ):
              o3_val = round(float(pollution["o3"]["conc"]), 1)
            elif isinstance(pollution["o3"], (int, float)):
              o3_val = round(float(pollution["o3"]), 1)

      except Exception as e:
        print(f"[INFO] Gagal tarik data IQAir ({item['stasiun']}): {e}")

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
          if (
              "weather_code" in daily_om
              and len(daily_om["weather_code"]) > 1
          ):
            code_tom = daily_om["weather_code"][1]
            t_max = daily_om["temperature_2m_max"][1]
            t_min = daily_om["temperature_2m_min"][1]
            rain_prob = daily_om.get("precipitation_probability_max", [0, 0])[
                1
            ]
            forecast_tomorrow = f"{get_wmo_description(code_tom)} ({t_min}°C - {t_max}°C, Hujan: {rain_prob}%)"
      except Exception as e:
        print(
            f"[INFO] Gagal tarik data Open-Meteo Weather ({item['stasiun']}):"
            f" {e}"
        )

      if pm25_val is None or o3_val is None:
        try:
          om_aq_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={item['lat']}&longitude={item['lon']}&current=pm2_5,ozone"
          resp_aq = requests.get(om_aq_url, timeout=10)
          if resp_aq.status_code == 200:
            stasiun_online = True
            curr_aq = resp_aq.json().get("current", {})
            if (
                pm25_val is None
                and "pm2_5" in curr_aq
                and curr_aq["pm2_5"] is not None
            ):
              pm25_val = round(float(curr_aq["pm2_5"]), 1)
            if (
                o3_val is None
                and "ozone" in curr_aq
                and curr_aq["ozone"] is not None
            ):
              o3_val = round(float(curr_aq["ozone"]), 1)
        except Exception as e:
          print(
              f"[INFO] Gagal tarik data Open-Meteo AQ ({item['stasiun']}): {e}"
          )

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
  has_online_station = (
      any(df["status_stasiun"] == "ONLINE") if not df.empty else False
  )
  return df, has_online_station


# 2. MEMUAT DATA PETA OFFLINE DARI "kota_tegal.geojson"
path_peta_qgis = "kota_tegal.geojson"

gdf_kota_tegal = None
if os.path.exists(path_peta_qgis):
  try:
    gdf_kota_tegal = gpd.read_file(path_peta_qgis)
    print(f"[INFO] Berhasil membaca file offline '{path_peta_qgis}'.")
  except Exception as e:
    print(f"[ERROR] Gagal membaca file GeoJSON ({path_peta_qgis}): {e}")
else:
  print(
      f"[PERINGATAN] File '{path_peta_qgis}' tidak ditemukan di folder yang"
      " sama!"
  )

# 3. AMBIL DATA REAL-TIME DARI API
df_udara, is_live_data = fetch_iqair_air_quality(IQAIR_API_KEY)

# 4. BUAT PETA OFFLINE (Diset zoom_control=False agar tombol + / - hilang)
peta = folium.Map(
    location=[-6.8671, 109.1372], zoom_start=12, zoom_control=False, tiles=None
)

# Plot GeoJSON jika file berhasil dibaca
if gdf_kota_tegal is not None:
  kolom_kemungkinan = [
      "NAMOBJ",
      "WADMKK",
      "WADMKC",
      "KECAMATAN",
      "nama",
      "Name",
      "NAMA_KOT",
  ]
  kolom_pencarian = None

  for col in kolom_kemungkinan:
    if col in gdf_kota_tegal.columns:
      kolom_pencarian = col
      break

  if not kolom_pencarian:
    cols_text = gdf_kota_tegal.select_dtypes(include=["object"]).columns
    kolom_pencarian = (
        cols_text[0] if len(cols_text) > 0 else gdf_kota_tegal.columns[0]
    )

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
          style=(
              "font-family: Arial, sans-serif; font-size: 13px; padding: 6px"
              " 12px; border-radius: 8px;"
          ),
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

# 4b. Plot Marker Sensor & List Item UI
panel_items_html = ""

if not df_udara.empty:
  for _, row in df_udara.iterrows():
    status_badge_color = (
        "#03AC0E" if row["status_stasiun"] == "ONLINE" else "#757575"
    )
    status_badge_bg = (
        "#E8F5E9" if row["status_stasiun"] == "ONLINE" else "#EEEEEE"
    )

    popup_html = f"""
        <div class="popup-card" style="font-family: Arial, sans-serif; min-width: 200px; max-width: 240px; padding: 2px;">

            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 10px; font-weight: 700; background-color: {status_badge_bg}; color: {status_badge_color}; padding: 2px 6px; border-radius: 4px;">
                    ● {row['status_stasiun']}
                </span>
                <span style="background-color: {row['bg_badge']}; color: {row['color']}; font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 6px;">
                    {row['kategori']}
                </span>
            </div>

            <div class="theme-text-main" style="font-size: 14px; font-weight: 700; margin-bottom: 6px;">{row['stasiun']}</div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; text-align: center; margin-bottom: 8px;">
                <div class="theme-bg-sub" style="border-radius: 8px; padding: 6px 2px;">
                    <div class="theme-text-sub" style="font-size: 9px;">PM2.5</div>
                    <div style="font-size: 11px; font-weight: 800; color: #03AC0E;">{row['pm25']} <span style="font-size: 7px;">µg/m³</span></div>
                </div>
                <div class="theme-bg-sub" style="border-radius: 8px; padding: 6px 2px;">
                    <div class="theme-text-sub" style="font-size: 9px;">O3 (Ozon)</div>
                    <div style="font-size: 11px; font-weight: 800; color: #0288D1;">{row['o3']} <span style="font-size: 7px;">µg/m³</span></div>
                </div>
                <div class="theme-bg-sub" style="border-radius: 8px; padding: 6px 2px;">
                    <div class="theme-text-sub" style="font-size: 9px;">Suhu</div>
                    <div style="font-size: 11px; font-weight: 800; color: #E65100;">{row['temp']} <span style="font-size: 7px;">°C</span></div>
                </div>
            </div>

            <div class="weather-box" style="border-radius: 8px; padding: 8px; font-size: 11px;">
                <div style="font-weight: 700; margin-bottom: 2px;">⛅ {row['cuaca_sekarang']}</div>
                <div>Lembap: {row['kelembapan']} | Angin: {row['kecepatan_angin']}</div>
                <div style="margin-top: 4px; padding-top: 4px; border-top: 1px dashed rgba(144, 202, 249, 0.5);">
                    <b>Ramalan Besok:</b><br>{row['ramalan_besok']}
                </div>
            </div>
        </div>
        """

    custom_icon = folium.DivIcon(
        html=f"""
            <div style="position: relative; width: 32px; height: 32px;">
                <div style="
                    background-color: {row['color']};
                    width: 28px;
                    height: 28px;
                    border-radius: 50% 50% 50% 0;
                    transform: rotate(-45deg);
                    border: 2px solid #FFFFFF;
                    box-shadow: 0 4px 10px rgba(49, 53, 59, 0.22);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                ">
                    <div style="
                        width: 8px;
                        height: 8px;
                        background-color: #FFFFFF;
                        border-radius: 50%;
                        transform: rotate(45deg);
                    "></div>
                </div>
            </div>
            """,
        icon_size=(32, 32),
        icon_anchor=(16, 32),
    )

    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=(
            f"<b>{row['stasiun']}</b> [{row['status_stasiun']}]:"
            f" {row['cuaca_sekarang']}"
        ),
        icon=custom_icon,
    ).add_to(peta)

    panel_items_html += f"""
        <div class="station-card" onclick="focusStation({row['lat']}, {row['lon']})" 
             style="padding: 10px; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s ease;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span class="theme-text-main" style="font-size: 13px; font-weight: 700;">{row['stasiun']}</span>
                <div>
                    <span style="font-size: 9px; font-weight: 700; background-color: {status_badge_bg}; color: {status_badge_color}; padding: 2px 4px; border-radius: 4px; margin-right: 4px;">
                        {row['status_stasiun']}
                    </span>
                    <span style="background-color: {row['bg_badge']}; color: {row['color']}; font-weight: 700; font-size: 10px; padding: 2px 6px; border-radius: 4px;">
                        {row['kategori']}
                    </span>
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                <span class="theme-text-sub">PM2.5: <b class="theme-text-main">{row['pm25']} µg/m³</b></span>
                <span class="theme-text-sub">O3: <b style="color: #0288D1;">{row['o3']} µg/m³</b></span>
                <span class="theme-text-sub">Suhu: <b style="color: #E65100;">{row['temp']} °C</b></span>
            </div>
            <div style="font-size: 11px; color: #1976D2; font-weight: 600;">
                🌤️ {row['cuaca_sekarang']}
            </div>
            <div class="theme-text-sub" style="font-size: 10px; margin-top: 2px;">
                Esok: {row['ramalan_besok']}
            </div>
        </div>
        """

# 4c. Ringkasan & UI Elements
df_online = (
    df_udara[df_udara["status_stasiun"] == "ONLINE"]
    if not df_udara.empty
    else pd.DataFrame()
)
valid_pm = (
    df_online[(df_online["pm25"] != "-") & (df_online["pm25"].notna())]["pm25"]
    if not df_online.empty
    else pd.Series()
)
valid_o3 = (
    df_online[(df_online["o3"] != "-") & (df_online["o3"].notna())]["o3"]
    if not df_online.empty
    else pd.Series()
)
valid_temp = (
    df_online[(df_online["temp"] != "-") & (df_online["temp"].notna())]["temp"]
    if not df_online.empty
    else pd.Series()
)

avg_pm25 = (
    round(valid_pm.astype(float).mean(), 1) if not valid_pm.empty else "-"
)
avg_o3 = round(valid_o3.astype(float).mean(), 1) if not valid_o3.empty else "-"
avg_temp = (
    round(valid_temp.astype(float).mean(), 1) if not valid_temp.empty else "-"
)

status_label = "ONLINE" if is_live_data else "OFFLINE"
status_color = "#03AC0E" if is_live_data else "#EF144A"

dashboard_ui = f"""
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<style>
    body {{ 
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
        margin: 0; 
        padding: 0; 
        background-color: #87CEEB; 
    }}
    
    .leaflet-container {{ background-color: #87CEEB !important; }}
    
    /* Sembunyikan Kontrol Zoom + dan - Leaflet */
    .leaflet-control-zoom {{
        display: none !important;
    }}
    
    #splash-screen {{
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        z-index: 99999; display: flex; flex-direction: column; justify-content: center; align-items: center; color: #FFFFFF;
        transition: opacity 0.8s ease, visibility 0.8s ease;
    }}
    .splash-logo-box {{
        width: 72px; height: 72px; background: rgba(3, 172, 14, 0.15); border: 2px solid #03AC0E;
        border-radius: 20px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px;
    }}
    .progress-container {{ width: 280px; background: rgba(255, 255, 255, 0.1); border-radius: 12px; height: 8px; overflow: hidden; margin-bottom: 12px; }}
    .progress-bar {{ width: 0%; height: 100%; background: linear-gradient(90deg, #03AC0E, #20E070); transition: width 0.1s linear; }}
    
    /* DESKTOP STYLES (DEFAULT) */
    .ui-header {{ position: fixed; top: 70px; left: 12px; z-index: 999; background: #FFFFFF; padding: 12px 16px; border-radius: 10px; border: 1px solid #E5E7E9; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 270px; }}
    .ui-panel {{ position: fixed; top: 16px; right: 16px; z-index: 999; background: #FFFFFF; width: 310px; max-height: calc(100vh - 32px); border-radius: 12px; border: 1px solid #E5E7E9; box-shadow: 0 6px 16px rgba(0,0,0,0.1); display: flex; flex-direction: column; transition: all 0.3s ease; }}
    .ui-legend {{ position: fixed; bottom: 16px; left: 16px; z-index: 999; background: #FFFFFF; padding: 12px 14px; border-radius: 10px; border: 1px solid #E5E7E9; box-shadow: 0 4px 12px rgba(0,0,0,0.1); font-size: 11px; width: 200px; }}
    .btn-toggle-theme {{ position: fixed; top: 12px; right: 60px; z-index: 1001; padding: 6px 10px; border-radius: 8px; border: 1px solid #E5E7E9; background: #FFFFFF; font-size: 11px; font-weight: 700; cursor: pointer; color: #212121; }}
    .panel-toggle-btn {{ display: none; }}

    /* WARNA MODE TERANG (DEFAULT) */
    .theme-text-main {{ color: #212121 !important; }}
    .theme-text-sub {{ color: #6C727C !important; }}
    .theme-bg-sub {{ background-color: #F3F4F5 !important; }}
    .station-card {{ background: #FFFFFF; border: 1px solid #E5E7E9; }}
    .weather-box {{ background: #E3F2FD; color: #0D47A1; }}
    
    .leaflet-popup-content-wrapper, .leaflet-popup-tip {{
        background: #FFFFFF !important;
        color: #212121 !important;
    }}

    /* RESPONSIVE MOBILE STYLES (HP) */
    @media (max-width: 768px) {{
        .ui-header {{
            top: 12px;
            left: 12px;
            right: 12px;
            width: auto;
            max-width: none;
            padding: 10px 14px;
        }}

        .btn-toggle-theme {{
            top: 12px;
            right: 12px;
            padding: 4px 8px;
            font-size: 10px;
        }}

        /* Ubah Panel Samping menjadi Bottom Drawer */
        .ui-panel {{
            top: auto;
            bottom: 0;
            left: 0;
            right: 0;
            width: 100%;
            max-height: 50vh;
            border-radius: 16px 16px 0 0;
            box-shadow: 0 -4px 16px rgba(0,0,0,0.15);
            transform: translateY(calc(100% - 42px));
            z-index: 1000;
        }}

        .ui-panel.open {{
            transform: translateY(0);
        }}

        .panel-toggle-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 6px 0;
            cursor: pointer;
        }}

        .panel-drag-handle {{
            width: 40px;
            height: 4px;
            background-color: #CBD5E1;
            border-radius: 2px;
        }}

        .ui-legend {{
            bottom: 50px;
            left: 12px;
            padding: 8px 10px;
            font-size: 10px;
            width: auto;
            max-width: 160px;
        }}

        /* Penyesuaian Kontrol Leaflet di HP */
        .leaflet-top.leaflet-left {{
            top: 100px !important;
        }}
    }}

    /* WARNA MODE GELAP (DARK MODE) */
    body.dark-mode .leaflet-container {{ background-color: #111827 !important; }}
    
    body.dark-mode .theme-card, 
    body.dark-mode .ui-header, 
    body.dark-mode .ui-panel, 
    body.dark-mode .ui-legend {{ 
        background-color: #1E293B !important; 
        color: #F8FAFC !important; 
        border-color: #334155 !important; 
    }}
    
    body.dark-mode .theme-text-main {{ color: #F8FAFC !important; }}
    body.dark-mode .theme-text-sub {{ color: #94A3B8 !important; }}
    body.dark-mode .theme-bg-sub {{ background-color: #0F172A !important; }}
    
    body.dark-mode .station-card {{ 
        background-color: #0F172A !important; 
        border-color: #334155 !important; 
    }}
    
    body.dark-mode .weather-box {{ 
        background: #1E3A8A !important; 
        color: #BFDBFE !important; 
    }}

    body.dark-mode .btn-toggle-theme {{ 
        background-color: #1E293B !important; 
        color: #F8FAFC !important; 
        border-color: #334155 !important; 
    }}

    body.dark-mode .leaflet-popup-content-wrapper, 
    body.dark-mode .leaflet-popup-tip {{
        background: #1E293B !important;
        color: #F8FAFC !important;
    }}
</style>

<div id="splash-screen">
    <div class="splash-logo-box">🍃</div>
    <div style="font-size: 22px; font-weight: 700; margin-bottom: 6px;">Sistem Monitoring Udara</div>
    <div style="font-size: 13px; color: #94A3B8; margin-bottom: 28px;">Kecamatan Kota Tegal</div>
    <div class="progress-container"><div id="splash-progress" class="progress-bar"></div></div>
    <div style="display: flex; justify-content: space-between; width: 280px; font-size: 11px; color: #64748B;">
        <span id="splash-status-text">Menginisialisasi peta...</span>
        <span id="splash-percentage">0%</span>
    </div>
</div>

<button id="themeToggleBtn" class="btn-toggle-theme" onclick="toggleTheme()">🌙 Dark Mode</button>

<div class="ui-header theme-card">
    <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 4px;">
        <span style="height: 6px; width: 6px; border-radius: 50%; background-color: {status_color};"></span>
        <span class="theme-text-sub" style="font-size: 9px; font-weight: 700;">{status_label}</span>
    </div>
    <div class="theme-text-main" style="font-size: 13px; font-weight: 700; margin-bottom: 8px;">Monitoring Udara Kota Tegal</div>
    <div style="display: flex; gap: 12px;">
        <div>
            <div class="theme-text-sub" style="font-size: 9px;">PM2.5 Avg</div>
            <div style="font-size: 11px; font-weight: 700; color: #03AC0E;">{avg_pm25} µg/m³</div>
        </div>
        <div>
            <div class="theme-text-sub" style="font-size: 9px;">O3 Avg</div>
            <div style="font-size: 11px; font-weight: 700; color: #0288D1;">{avg_o3} µg/m³</div>
        </div>
        <div>
            <div class="theme-text-sub" style="font-size: 9px;">Suhu Avg</div>
            <div style="font-size: 11px; font-weight: 700; color: #E65100;">{avg_temp} °C</div>
        </div>
    </div>
</div>

<div id="stationPanel" class="ui-panel theme-card">
    <div class="panel-toggle-btn" onclick="togglePanel()">
        <div class="panel-drag-handle"></div>
    </div>
    <div style="padding: 6px 14px 10px 14px; border-bottom: 1px solid #E5E7E9; display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div class="theme-text-main" style="font-size: 13px; font-weight: 700;">Daftar Stasiun & Forecast</div>
            <div class="theme-text-sub" style="font-size: 10px;">Klik wilayah untuk memperbesar</div>
        </div>
    </div>
    <div style="padding: 10px; overflow-y: auto; flex-grow: 1;">
        {panel_items_html}
    </div>
</div>

<div class="ui-legend theme-card">
    <div class="theme-text-main" style="font-weight: 700; margin-bottom: 6px; font-size: 11px;">Indeks Udara (PM2.5)</div>
    <div class="theme-text-sub" style="display: flex; justify-content: space-between; margin-bottom: 4px; gap: 8px;"><span><span style="background:#03AC0E; width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px;"></span>Baik</span><span>0 - 15.5</span></div>
    <div class="theme-text-sub" style="display: flex; justify-content: space-between; margin-bottom: 4px; gap: 8px;"><span><span style="background:#FF9800; width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px;"></span>Sedang</span><span>15.6 - 55.4</span></div>
    <div class="theme-text-sub" style="display: flex; justify-content: space-between; margin-bottom: 4px; gap: 8px;"><span><span style="background:#EF144A; width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px;"></span>Tidak Sehat</span><span>> 55.5</span></div>
    <div class="theme-text-sub" style="display: flex; justify-content: space-between; gap: 8px;"><span><span style="background:#757575; width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px;"></span>Offline</span><span>-</span></div>
</div>

<script>
    document.addEventListener("DOMContentLoaded", function() {{
        var progressBar = document.getElementById('splash-progress');
        var percentageText = document.getElementById('splash-percentage');
        var splashScreen = document.getElementById('splash-screen');

        var totalTimeMs = 2000;
        var intervalMs = 50;
        var elapsed = 0;

        var timer = setInterval(function() {{
            elapsed += intervalMs;
            var progress = Math.min((elapsed / totalTimeMs) * 100, 100);

            if (progressBar && percentageText) {{
                progressBar.style.width = progress + '%';
                percentageText.innerText = Math.floor(progress) + '%';
            }}

            if (progress >= 100) {{
                clearInterval(timer);
                setTimeout(function() {{
                    if (splashScreen) {{
                        splashScreen.style.opacity = '0';
                        splashScreen.style.visibility = 'hidden';
                        setTimeout(function() {{ splashScreen.style.display = 'none'; }}, 800);
                    }}
                }}, 200);
            }}
        }}, intervalMs);
    }});

    function toggleTheme() {{
        var body = document.body;
        var btn = document.getElementById('themeToggleBtn');
        body.classList.toggle('dark-mode');
        btn.innerHTML = body.classList.contains('dark-mode') ? '☀️ Light Mode' : '🌙 Dark Mode';
    }}

    function togglePanel() {{
        var panel = document.getElementById('stationPanel');
        panel.classList.toggle('open');
    }}

    function focusStation(lat, lon) {{
        var mapObj = null;
        for (var key in window) {{
            if (key.startsWith('map_') && window[key] instanceof L.Map) {{
                mapObj = window[key];
                break;
            }}
        }}
        if (mapObj) {{
            mapObj.setView([lat, lon], 14, {{ animate: true }});
            // Tutup panel di mobile saat stasiun diklik
            if (window.innerWidth <= 768) {{
                var panel = document.getElementById('stationPanel');
                panel.classList.remove('open');
            }}
        }}
    }}
</script>
"""

peta.get_root().html.add_child(folium.Element(dashboard_ui))

# 5. SIMPAN DAN BUKA PETA OTOMATIS
output_file = "peta_tegal.html"
peta.save(output_file)
print(
    "[SUCCESS] Peta dengan Dark Mode dan Pengukuran Ozon berhasil dibuat:"
    f" {output_file}"
)

webbrowser.open(os.path.abspath(output_file))
