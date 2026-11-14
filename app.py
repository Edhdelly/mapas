import os
import zipfile
import tempfile
from pathlib import Path

import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import Fullscreen, LocateControl
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Mapa Colhedora e Transbordo",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS otimizado para uso em celular
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.5rem;
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        
        /* Checkboxes grandes e espaçados para facilitar o toque */
        div[data-testid="stCheckbox"] label {
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            padding: 8px 4px !important;
            line-height: 1.4 !important;
        }
        
        /* Botões de ação maiores */
        div.stButton > button {
            width: 100%;
            min-height: 48px;
            font-size: 1.05rem !important;
            font-weight: bold !important;
            border-radius: 8px;
        }
        
        /* Botão do Google Maps */
        .btn-maps {
            display: block;
            width: 100%;
            background-color: #2E7D32;
            color: white !important;
            text-align: center;
            padding: 14px 10px;
            font-size: 1.1rem;
            font-weight: bold;
            border-radius: 10px;
            text-decoration: none !important;
            margin-top: 6px;
            margin-bottom: 10px;
            box-shadow: 0 3px 6px rgba(0,0,0,0.25);
        }
        
        /* Legenda de cores */
        .legenda-item {
            display: inline-block;
            padding: 6px 10px;
            margin: 3px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 0.9rem;
            color: #000;
            border: 2px solid #222;
        }
        
        iframe {
            width: 100% !important;
            border-radius: 12px;
            border: 2px solid #444;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("### 🚜 Visualizador de Mapas e Telemetria")

# Cores vibrantes para diferenciar cada bloco selecionado sobre o satélite
CORES_BLOCOS = [
    "#FFEA00",  # Amarelo
    "#00E5FF",  # Azul Ciano
    "#FF3D00",  # Laranja/Vermelho
    "#76FF03",  # Verde Limão
    "#FF4081",  # Rosa Claro
    "#E040FB",  # Lilás
    "#FFFFFF",  # Branco
    "#FFD740",  # Ouro
]

# Oculta APENAS subpastas internas genéricas de sistema, mantendo todos os equipamentos
PASTAS_SISTEMA_IGNORADAS = {"aggps", "data", "__macosx"}

# Termos conhecidos para destacar automaticamente o equipamento de telemetria
TERMOS_EQUIPAMENTOS = [
    "CASE", "PRO700", "PRO_700", "TRIMBLE", "TRIMVLE", "GFX", 
    "2GUIDANCE", "GS3", "GEN4", "SOLINFTEC", "HEXAGON", "STARA", "JD"
]

def extrair_metadados_caminho(shp_path: Path, base_path: Path) -> dict:
    """
    Identifica Operação (COLHEDORA/TRANSBORDO), Equipamento (Case_PRO700, TRIMBLE_GFX, etc.)
    e mantém todas as pastas úteis visíveis no nome.
    """
    partes_brutas = list(shp_path.relative_to(base_path).parts)
    partes_pastas = [p for p in partes_brutas[:-1] if p.lower() not in PASTAS_SISTEMA_IGNORADAS]
    nome_arquivo = shp_path.stem

    # 1. Identifica Operação (Colhedora ou Transbordo)
    operacao = "OUTROS"
    icone_op = "📍"
    idx_operacao = -1

    for i, pasta in enumerate(partes_pastas):
        p_upper = pasta.upper()
        if "COLHEDORA" in p_upper:
            operacao = "COLHEDORA"
            icone_op = "🚜"
            idx_operacao = i
            break
        elif "TRANSBORDO" in p_upper:
            operacao = "TRANSBORDO"
            icone_op = "🚛"
            idx_operacao = i
            break

    # 2. Identifica o Equipamento de Telemetria (ex: Case_PRO700, TRIMBLE_GFX, 2Guidance)
    equipamento = "Não especificado"
    
    # Primeiro procura pela pasta logo após COLHEDORA/TRANSBORDO
    if idx_operacao != -1 and (idx_operacao + 1) < len(partes_pastas):
        candidato = partes_pastas[idx_operacao + 1]
        if not candidato.upper().startswith(("RAIZEN", "BLOCO")):
            equipamento = candidato

    # Se não achou pela posição, procura por palavras-chave de equipamentos em qualquer pasta
    if equipamento == "Não especificado":
        for pasta in partes_pastas:
            p_upper = pasta.upper()
            if any(termo in p_upper for termo in TERMOS_EQUIPAMENTOS):
                equipamento = pasta
                break

    # 3. Monta o texto completo destacando Operação, Equipamento e Bloco
    partes_formatadas = []
    for pasta in partes_pastas:
        if pasta == equipamento:
            partes_formatadas.append(f"📡 {pasta}")
        else:
            partes_formatadas.append(pasta)

    caminho_limpo = " / ".join(partes_formatadas) if partes_formatadas else nome_arquivo
    if nome_arquivo.lower() not in ["linefeature", "boundary", "coverage"]:
        caminho_limpo = f"{caminho_limpo} ({nome_arquivo})"

    label_exibicao = f"{icone_op} {caminho_limpo}"

    return {
        "label": label_exibicao,
        "operacao": operacao,
        "equipamento": equipamento,
        "path": shp_path
    }

def listar_shapefiles(diretorio: Path) -> list:
    shp_files = sorted(list(diretorio.rglob("*.shp")))
    itens = []
    labels_vistos = set()

    for idx, shp in enumerate(shp_files):
        meta = extrair_metadados_caminho(shp, diretorio)
        label_original = meta["label"]
        contador = 2
        while meta["label"] in labels_vistos:
            meta["label"] = f"{label_original} ({contador})"
            contador += 1
        labels_vistos.add(meta["label"])
        # Chave única para o session_state do Streamlit
        meta["key"] = f"chk_item_{idx}_{meta['label']}"
        itens.append(meta)
    return itens

# 1. Carregamento dos Arquivos
pasta_atual = Path(".")
zips_locais = list(pasta_atual.glob("*.zip"))
shps_locais = list(pasta_atual.rglob("*.shp"))

arquivo_upload = None
if shps_locais or zips_locais:
    with st.expander("📁 Enviar outro arquivo .ZIP do celular"):
        arquivo_upload = st.file_uploader("Escolha o arquivo .ZIP", type=["zip"])
else:
    st.info("👇 **Passo 1:** Toque abaixo para escolher o arquivo **.ZIP** com os mapas.")
    arquivo_upload = st.file_uploader("Escolher arquivo .ZIP", type=["zip"])

tmpdir_obj = tempfile.TemporaryDirectory()
tmpdir = Path(tmpdir_obj.name)
lista_mapas = []

if arquivo_upload is not None:
    zip_path = tmpdir / "upload.zip"
    with open(zip_path, "wb") as f:
        f.write(arquivo_upload.getbuffer())
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)
        lista_mapas = listar_shapefiles(tmpdir)
    except zipfile.BadZipFile:
        st.error("❌ Arquivo .ZIP inválido.")
        st.stop()
elif shps_locais:
    lista_mapas = listar_shapefiles(pasta_atual)
elif zips_locais:
    try:
        with zipfile.ZipFile(zips_locais[0], "r") as z:
            z.extractall(tmpdir)
        lista_mapas = listar_shapefiles(tmpdir)
    except Exception:
        pass

if not lista_mapas:
    st.stop()

# Inicializa o estado de cada checkbox na memória (marca o 1º por padrão na primeira abertura)
for idx, item in enumerate(lista_mapas):
    chave = item["key"]
    if chave not in st.session_state:
        st.session_state[chave] = (idx == 0)

# 2. Filtros Rápidos (Operação e Equipamento de Telemetria)
col_f1, col_f2 = st.columns(2)

with col_f1:
    operacoes_presentes = sorted(list({item["operacao"] for item in lista_mapas}))
    opcoes_op = ["📋 TODAS AS MÁQUINAS"]
    if "COLHEDORA" in operacoes_presentes:
        opcoes_op.append("🚜 SÓ COLHEDORA")
    if "TRANSBORDO" in operacoes_presentes:
        opcoes_op.append("🚛 SÓ TRANSBORDO")
    if "OUTROS" in operacoes_presentes and len(operacoes_presentes) > 1:
        opcoes_op.append("📍 OUTROS")

    filtro_op = st.radio("1️⃣ Filtrar por Máquina:", options=opcoes_op, horizontal=True)

with col_f2:
    equipamentos_presentes = sorted(list({item["equipamento"] for item in lista_mapas if item["equipamento"] != "Não especificado"}))
    if equipamentos_presentes:
        opcoes_eq = ["📡 TODOS OS EQUIPAMENTOS"] + [f"📡 {eq}" for eq in equipamentos_presentes]
        filtro_eq = st.radio("2️⃣ Filtrar por Equipamento / Monitor:", options=opcoes_eq, horizontal=True)
    else:
        filtro_eq = "📡 TODOS OS EQUIPAMENTOS"

# Aplica os filtros selecionados
mapas_filtrados = []
for item in lista_mapas:
    if filtro_op == "🚜 SÓ COLHEDORA" and item["operacao"] != "COLHEDORA":
        continue
    if filtro_op == "🚛 SÓ TRANSBORDO" and item["operacao"] != "TRANSBORDO":
        continue
    if filtro_op == "📍 OUTROS" and item["operacao"] != "OUTROS":
        continue
    if filtro_eq != "📡 TODOS OS EQUIPAMENTOS":
        nome_eq_limpo = filtro_eq.replace("📡 ", "")
        if item["equipamento"] != nome_eq_limpo:
            continue
    mapas_filtrados.append(item)

# 3. Funções de Callback para os botões funcionarem instantaneamente
chaves_filtradas = [item["key"] for item in mapas_filtrados]
todas_as_chaves = [item["key"] for item in lista_mapas]

def marcar_visiveis(chaves):
    for k in chaves:
        st.session_state[k] = True

def limpar_tudo(chaves):
    for k in chaves:
        st.session_state[k] = False

st.markdown("**3️⃣ Toque nos blocos abaixo para marcar ou desmarcar no mapa:**")

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    st.button(
        "✅ Marcar Todos da Lista",
        on_click=marcar_visiveis,
        args=(chaves_filtradas,),
        use_container_width=True
    )
with col_btn2:
    st.button(
        "🧹 Limpar Seleção",
        on_click=limpar_tudo,
        args=(todas_as_chaves,),
        use_container_width=True
    )

# Renderiza os checkboxes (vinculados diretamente ao session_state pela key)
with st.container(border=True):
    if not mapas_filtrados:
        st.info("Nenhum bloco encontrado para este filtro.")
    for item in mapas_filtrados:
        st.checkbox(item["label"], key=item["key"])

# Coleta todos os blocos que estão marcados
itens_selecionados = [item for item in lista_mapas if st.session_state.get(item["key"], False)]

tipo_mapa = st.radio(
    "4️⃣ Tipo de imagem do mapa:",
    options=["🛰️ Satélite (Foto Real)", "🛣️ Mapa de Estradas"],
    horizontal=True
)

if not itens_selecionados:
    st.warning("👆 Nenhum bloco está marcado. Toque em pelo menos uma caixa acima (ou em 'Marcar Todos') para ver o mapa.")
    st.stop()

# 4. Construção do Mapa
m = folium.Map(
    location=[-22.8526, -47.4446],
    zoom_start=16,
    tiles=None,
    control_scale=True
)

if "Satélite" in tipo_mapa:
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        name="Satélite",
        max_zoom=21
    ).add_to(m)
else:
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        attr="Google",
        name="Estradas",
        max_zoom=21
    ).add_to(m)

bounds = []
centro_lat, centro_lon = None, None
html_legenda = ""

for idx, item in enumerate(itens_selecionados):
    lbl = item["label"]
    caminho_shp = item["path"]
    cor_atual = CORES_BLOCOS[idx % len(CORES_BLOCOS)]
    
    try:
        gdf = gpd.read_file(caminho_shp)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        elif gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)

        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]

        if not gdf.empty:
            minx, miny, maxx, maxy = gdf.total_bounds
            bounds.append([miny, minx])
            bounds.append([maxy, maxx])

            centro_lat = (miny + maxy) / 2
            centro_lon = (minx + maxx) / 2

            # Contorno preto para alto contraste sob luz solar
            folium.GeoJson(
                gdf,
                style_function=lambda x: {
                    "color": "#000000",
                    "weight": 6,
                    "opacity": 0.75
                },
                tooltip=lbl
            ).add_to(m)

            # Traçado colorido principal
            folium.GeoJson(
                gdf,
                name=lbl,
                style_function=lambda x, cor=cor_atual: {
                    "color": cor,
                    "weight": 3.5,
                    "opacity": 1.0,
                    "fillColor": cor,
                    "fillOpacity": 0.3
                },
                tooltip=f"<b>{lbl}</b>"
            ).add_to(m)

            # Pino identificador no centro do bloco
            folium.Marker(
                location=[centro_lat, centro_lon],
                tooltip=lbl,
                popup=f"<b>{lbl}</b>",
                icon=folium.Icon(
                    color="orange" if item["operacao"] == "TRANSBORDO" else "green",
                    icon="info-sign"
                )
            ).add_to(m)

            html_legenda += f'<span class="legenda-item" style="background-color: {cor_atual};">{lbl}</span>'

    except Exception:
        st.warning(f"Não foi possível carregar {lbl}.")

if bounds:
    m.fit_bounds(bounds)

Fullscreen(
    position="topleft",
    title="Tela Cheia",
    title_cancel="Sair da Tela Cheia",
    force_separate_button=True
).add_to(m)

LocateControl(
    auto_start=False,
    position="topleft",
    strings={"title": "📍 Mostrar minha posição no mapa (GPS)"},
    flyTo=True
).add_to(m)

st.markdown(f"**🎨 Legenda dos blocos marcados ({len(itens_selecionados)}):**<br>{html_legenda}", unsafe_allow_html=True)

if centro_lat and centro_lon:
    link_google_maps = f"https://www.google.com/maps/dir/?api=1&destination={centro_lat},{centro_lon}"
    st.markdown(
        f'<a href="{link_google_maps}" target="_blank" class="btn-maps">'
        f'🧭 IR ATÉ A ÁREA SELECIONADA (ABRIR GOOGLE MAPS)</a>',
        unsafe_allow_html=True
    )

st_folium(m, use_container_width=True, height=500, returned_objects=[])