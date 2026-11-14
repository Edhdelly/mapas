import os
import re
import zipfile
import tempfile
from pathlib import Path

import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import Fullscreen, LocateControl
from streamlit_folium import st_folium

# Configuração da página otimizada para mobile (layout wide aproveita 100% da largura da tela)
st.set_page_config(
    page_title="Visualizador GIS Mobile",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Ajuste de CSS para melhorar visualização em telas de celular
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        iframe {
            width: 100% !important;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

st.subheader("🛰️ Visualizador de Mapas e Talhões (Shapefile / AgGPS)")

uploaded_file = st.file_uploader(
    "Selecione o arquivo .ZIP contendo as pastas e arquivos (.shp, .dbf, .shx, .pos)",
    type=["zip"]
)

def parse_pos_filename(filename: str):
    """Extrai coordenadas do padrão de nome AgGPS: -47.4446E-22.8526N.pos"""
    match = re.search(r"(-?\d+\.\d+)[EW](-?\d+\.\d+)[NS]", filename, re.IGNORECASE)
    if match:
        lon = float(match.group(1))
        lat = float(match.group(2))
        return lat, lon
    return None

if uploaded_file is not None:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "dados.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)
        except zipfile.BadZipFile:
            st.error("O arquivo enviado não é um .ZIP válido. Se estiver em .RAR, recrie como .ZIP.")
            st.stop()

        # Busca recursiva por todos os arquivos .shp e .pos nas subpastas
        base_path = Path(tmpdir)
        shp_files = sorted(list(base_path.rglob("*.shp")))
        pos_files = sorted(list(base_path.rglob("*.pos")))

        if not shp_files:
            st.warning("Nenhum arquivo .shp foi encontrado dentro do arquivo .zip.")
            st.stop()

        # Cria rótulos amigáveis mostrando a pasta/bloco (ex: 8037_004_R / BLOCO_1 / LineFeature.shp)
        shp_options = {}
        for shp in shp_files:
            rel_parts = shp.relative_to(base_path).parts
            label = " / ".join(rel_parts[-3:]) if len(rel_parts) >= 3 else str(shp.relative_to(base_path))
            # Garante unicidade caso existam caminhos parecidos
            if label in shp_options:
                label = str(shp.relative_to(base_path))
            shp_options[label] = shp

        # Controles no topo da página (muito mais prático no celular que barra lateral)
        col1, col2 = st.columns([3, 1])
        with col1:
            selecionados = st.multiselect(
                "📂 Selecione as camadas / blocos para exibir no mapa:",
                options=list(shp_options.keys()),
                default=[list(shp_options.keys())[0]]
            )
        with col2:
            cor_linha = st.color_picker("🎨 Cor do traçado", "#00FFAA")

        if selecionados:
            # Inicializa o mapa com Google Satélite Híbrido (Satélite + Nomes/Estradas)
            m = folium.Map(
                location=[-22.8526, -47.4446],
                zoom_start=15,
                tiles=None,
                control_scale=True
            )

            # Camada 1: Google Satélite Híbrido (Padrão)
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                attr="Google Satellite Hybrid",
                name="Satélite + Rótulos (Google)",
                max_zoom=21,
                overlay=False,
                control=True
            ).add_to(m)

            # Camada 2: Google Satélite Puro
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google Satellite",
                name="Satélite Puro (Google)",
                max_zoom=21,
                overlay=False,
                control=True
            ).add_to(m)

            # Camada 3: Mapa de Ruas (OpenStreetMap)
            folium.TileLayer(
                tiles="OpenStreetMap",
                name="Mapa de Ruas (OSM)",
                overlay=False,
                control=True
            ).add_to(m)

            bounds = []
            tabelas_atributos = {}

            for label in selecionados:
                shp_path = shp_options[label]
                try:
                    gdf = gpd.read_file(shp_path)

                    # Reprojeta para WGS84 (Lat/Lon) caso tenha .prj em UTM ou outro sistema
                    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                        gdf = gdf.to_crs(epsg=4326)
                    elif gdf.crs is None:
                        gdf.set_crs(epsg=4326, inplace=True)

                    # Remove geometrias nulas/vazias
                    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]

                    if not gdf.empty:
                        # Armazena limites para centralizar o zoom automaticamente
                        minx, miny, maxx, maxy = gdf.total_bounds
                        bounds.append([miny, minx])
                        bounds.append([maxy, maxx])

                        # Colunas da tabela .dbf para exibir ao tocar na linha/polígono
                        colunas_attr = [c for c in gdf.columns if c != "geometry"]
                        tabelas_atributos[label] = gdf[colunas_attr]

                        tooltip = folium.GeoJsonTooltip(fields=colunas_attr) if colunas_attr else None
                        popup = folium.GeoJsonPopup(fields=colunas_attr) if colunas_attr else None

                        folium.GeoJson(
                            gdf,
                            name=label,
                            style_function=lambda x, cor=cor_linha: {
                                "color": cor,
                                "weight": 3,
                                "opacity": 0.9,
                                "fillColor": cor,
                                "fillOpacity": 0.25
                            },
                            tooltip=tooltip,
                            popup=popup
                        ).add_to(m)

                except Exception as e:
                    st.error(f"Erro ao carregar {label}: {e}")

            # Adiciona marcadores dos arquivos .pos encontrados nas pastas selecionadas
            for pos in pos_files:
                coords = parse_pos_filename(pos.name)
                if coords:
                    folium.Marker(
                        location=[coords[0], coords[1]],
                        popup=f"<b>Arquivo POS:</b> {pos.name}<br>Lat: {coords[0]}<br>Lon: {coords[1]}",
                        tooltip=f"Ponto Base ({pos.name})",
                        icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")
                    ).add_to(m)

            # Ajusta o zoom automaticamente para enquadrar os blocos selecionados
            if bounds:
                m.fit_bounds(bounds)

            # Botões úteis para celular: Tela Cheia e GPS em tempo real
            Fullscreen(position="topleft", title="Tela Cheia", title_cancel="Sair").add_to(m)
            LocateControl(auto_start=False, strings={"title": "Mostrar minha localização GPS"}).add_to(m)
            folium.LayerControl(position="topright", collapsed=True).add_to(m)

            # Renderiza o mapa responsivo
            st_folium(m, use_container_width=True, height=520, returned_objects=[])

            # Aba expansível para consultar a tabela .dbf no celular sem poluir a tela
            with st.expander("📋 Ver Tabela de Atributos (.dbf) dos itens selecionados"):
                for label, df_attr in tabelas_atributos.items():
                    st.markdown(f"**{label}** ({len(df_attr)} registros)")
                    st.dataframe(df_attr, use_container_width=True)
        else:
            st.info("Selecione pelo menos um arquivo na lista acima para visualizar no mapa.")