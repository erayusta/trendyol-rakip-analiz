import os
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.express as px
import pandas as pd
import time
from datetime import datetime
import json
import logging
from scraper import TrendyolScraper
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Çevresel değişkenleri al
PORT = int(os.getenv('DASHBOARD_PORT', 8053))
DATA_FILE = os.getenv('DATA_FILE', 'price_data.json')
COMPETITOR_DATA_FILE = os.getenv('COMPETITOR_DATA_FILE', 'all_competitor_prices.json')
PRODUCT_DATA_DIR = os.getenv('PRODUCT_DATA_DIR', 'product_data')

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dash uygulamasını başlat
app = dash.Dash(
    __name__,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    suppress_callback_exceptions=True
)
server = app.server
app.title = "Trendyol Rakip Fiyat Takip Paneli"

# Veri dosyası
# DATA_FILE = "price_data.json"
# COMPETITOR_DATA_FILE = "all_competitor_prices.json"

def load_data():
    """Ürün verilerini yükler."""
    try:
        # Rakip fiyatları yükle - öncelikle bunları kontrol edelim
        if os.path.exists(COMPETITOR_DATA_FILE):
            with open(COMPETITOR_DATA_FILE, 'r', encoding='utf-8') as f:
                competitor_data = json.load(f)
                logger.info(f"Rakip fiyatları '{COMPETITOR_DATA_FILE}' dosyasından yüklendi.")
                
                # Eğer competitor_data bir liste ise (yeni format), doğrudan bu veriyi kullan
                if isinstance(competitor_data, list):
                    logger.info("Yeni format rakip verisi (liste) tespit edildi.")
                    return competitor_data
                
        # Eğer buraya kadar geldiyse, eski format veri veya DATA_FILE'ı kullanmayı dene
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Ürün verileri '{DATA_FILE}' dosyasından yüklendi.")
        else:
            # Dosya yoksa boş bir veri oluştur
            data = []
            logger.warning(f"'{DATA_FILE}' dosyası bulunamadı. Boş veri oluşturuldu.")
        
        # Eğer competitor_data tanımlı değilse, boş bir sözlük oluştur
        if 'competitor_data' not in locals():
            competitor_data = {}
            logger.warning(f"'{COMPETITOR_DATA_FILE}' dosyası bulunamadı veya eski format değil. Boş veri oluşturuldu.")
        
        # Ürün verilerini birleştir
        for product in data:
            product_id = product.get('product_id')
            if product_id:
                # Rakip fiyatlarını ekle
                if product_id in competitor_data:
                    product['competitor_prices'] = competitor_data[product_id]
                else:
                    product['competitor_prices'] = []
                
                # Ürün URL'sini kontrol et ve düzelt
                if 'product_url' not in product or not product['product_url']:
                    # Ürün URL'si yoksa oluştur
                    product['product_url'] = f"https://www.trendyol.com/brand/name-p-{product_id}"
                    logger.warning(f"Ürün ID {product_id} için URL oluşturuldu: {product['product_url']}")
                elif not product['product_url'].startswith('http'):
                    # URL http ile başlamıyorsa düzelt
                    product['product_url'] = f"https://www.trendyol.com{product['product_url']}"
                    logger.warning(f"Ürün ID {product_id} için URL düzeltildi: {product['product_url']}")
            else:
                logger.warning(f"Ürün ID bulunamadı: {product.get('product_name', 'İsimsiz ürün')}")
        
        return data
    except Exception as e:
        logger.error(f"Veri yüklenirken hata: {str(e)}")
        return []

def save_data(data):
    """Veriyi dosyaya kaydeder."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Veri dosyaya kaydedildi: {len(data)} ürün.")
    except Exception as e:
        logger.error(f"Veri kaydedilirken hata oluştu: {str(e)}")

def create_price_dataframe(data):
    """Fiyat verilerinden DataFrame oluşturur."""
    if not data:
        logger.warning("Veri yok, boş DataFrame döndürülüyor.")
        return pd.DataFrame()
    
    logger.info(f"DataFrame oluşturuluyor, veri uzunluğu: {len(data)}")
    logger.info(f"İlk ürün örneği: {data[0] if data else 'Veri yok'}")
    
    rows = []
    for product in data:
        try:
            # Ana ürün satırı
            my_price = product.get("my_price", "0 TL")
            if isinstance(my_price, dict) and "text" in my_price:
                my_price = my_price["text"]
            
            row = {
                "Ürün Adı": product.get("product_name", ""),
                "Satıcı": "Kendi Mağazam",
                "Fiyat": my_price.replace(" TL", "").replace(".", "").replace(",", ".") if isinstance(my_price, str) else my_price,
                "URL": product.get("product_url", ""),
                "Resim": product.get("product_image", ""),
                "Son Güncelleme": product.get("last_update", ""),
                "Ürün ID": product.get("product_id", "")
            }
            rows.append(row)
            
            # Rakip satırları
            competitors = product.get("competitors", [])
            logger.info(f"Ürün '{product.get('product_name', '')}' için {len(competitors)} rakip bulundu.")
            
            for comp in competitors:
                comp_price = comp.get("price", "0 TL")
                if isinstance(comp_price, dict) and "text" in comp_price:
                    comp_price = comp_price["text"]
                
                comp_row = {
                    "Ürün Adı": product.get("product_name", ""),
                    "Satıcı": comp.get("name", "Bilinmeyen"),
                    "Fiyat": comp_price.replace(" TL", "").replace(".", "").replace(",", ".") if isinstance(comp_price, str) else comp_price,
                    "URL": product.get("product_url", ""),
                    "Resim": product.get("product_image", ""),
                    "Son Güncelleme": product.get("last_update", ""),
                    "Ürün ID": product.get("product_id", "")
                }
                rows.append(comp_row)
        except Exception as e:
            logger.error(f"Ürün işlenirken hata: {str(e)}, Ürün: {product}")
    
    logger.info(f"Toplam {len(rows)} satır oluşturuldu.")
    
    if not rows:
        logger.warning("Hiç satır oluşturulamadı, boş DataFrame döndürülüyor.")
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    logger.info(f"DataFrame sütunları: {df.columns.tolist()}")
    
    # Fiyat sütununu sayısal değere dönüştür
    try:
        df["Fiyat"] = pd.to_numeric(df["Fiyat"], errors="coerce")
        logger.info("Fiyat sütunu sayısal değere dönüştürüldü.")
    except Exception as e:
        logger.error(f"Fiyat dönüştürülürken hata: {str(e)}")
    
    # En ucuz fiyatları işaretle
    df["En Ucuz"] = False
    for product_name in df["Ürün Adı"].unique():
        product_df = df[df["Ürün Adı"] == product_name]
        min_price_idx = product_df["Fiyat"].idxmin()
        if pd.notna(min_price_idx):
            df.loc[min_price_idx, "En Ucuz"] = True
    
    return df

# Uygulama düzeni
app.layout = html.Div([
    html.Div([
        html.H1("Trendyol Rakip Fiyat Takip Paneli", className="header-title"),
        html.P("Mağazanızdaki ürünlerin rakip fiyatlarını takip edin", className="header-description"),
        html.Div([
            html.Button("Verileri Güncelle", id="refresh-button", className="control-button"),
            dcc.Loading(
                id="loading-refresh",
                type="circle",
                children=[html.Div(id="refresh-output")]
            )
        ], className="header-controls"),
        html.Div([
            html.P(id="last-update-time", className="last-update-time")
        ])
    ], className="header"),
    
    html.Div([
        html.Div([
            html.H2("Ürün Fiyat Karşılaştırması"),
            dcc.Dropdown(
                id="product-dropdown",
                placeholder="Ürün seçin...",
                className="dropdown"
            ),
            dcc.Graph(id="price-comparison-graph"),
            html.Div(id="product-image-container", className="image-container")
        ], className="card"),
        
        html.Div([
            html.H2("Tüm Ürünler ve Rakip Fiyatları"),
            dash_table.DataTable(
                id="product-table",
                columns=[
                    {"name": "Ürün Adı", "id": "Ürün Adı"},
                    {"name": "Satıcı", "id": "Satıcı"},
                    {"name": "Fiyat (TL)", "id": "Fiyat", "type": "numeric", "format": {"specifier": ",.2f"}},
                    {"name": "Ürün Linki", "id": "URL", "presentation": "markdown"},
                    {"name": "En Ucuz", "id": "En Ucuz", "presentation": "markdown"}
                ],
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "left",
                    "padding": "10px",
                    "whiteSpace": "normal",
                    "height": "auto",
                },
                style_header={
                    "backgroundColor": "#f8f9fa",
                    "fontWeight": "bold",
                    "border": "1px solid #ddd",
                },
                markdown_options={"html": True, "link_target": "_blank"},
                style_data_conditional=[
                    {
                        "if": {"filter_query": "{Satıcı} = 'Kendi Mağazam'"},
                        "backgroundColor": "#e6f3ff",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {"filter_query": "{En Ucuz} = True"},
                        "backgroundColor": "#cff6cf",
                        "color": "green",
                    }
                ],
                sort_action="native",
                filter_action="native",
                page_size=15,
                markdown_options={"html": True},
            ),
        ], className="card"),
    ], className="content"),
])

@app.callback(
    [Output("product-dropdown", "options"),
     Output("product-dropdown", "value"),
     Output("product-table", "data"),
     Output("last-update-time", "children")],
    [Input("refresh-button", "n_clicks")],
    prevent_initial_call=False
)
def update_data(n_clicks):
    """Veriyi günceller veya mevcut veriyi yükler."""
    data = load_data()
    
    # İlk yükleme veya güncelleme isteği
    if n_clicks is not None:
        try:
            scraper = TrendyolScraper()
            new_data = scraper.analyze_all_products()
            scraper.close()
            
            # Zaman damgası ekle
            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            for item in new_data:
                item["last_update"] = timestamp
            
            # Veriyi güncelle ve kaydet
            data = new_data
            save_data(data)
            logger.info("Veriler başarıyla güncellendi.")
        except Exception as e:
            logger.error(f"Veri güncellenirken hata oluştu: {str(e)}")
    
    # DataFrame oluştur
    df = create_price_dataframe(data)
    
    # URL'leri markdown bağlantılarına dönüştür
    if not df.empty and "URL" in df.columns:
        df["URL"] = df.apply(lambda row: f"[Ürün Linki]({row['URL']})" if row['URL'] else "", axis=1)
    
    # En Ucuz sütununu daha kullanıcı dostu hale getir
    if not df.empty and "En Ucuz" in df.columns:
        df["En Ucuz"] = df.apply(
            lambda row: "✅ En Ucuz" if row["En Ucuz"] else "",
            axis=1
        )
    
    # Dropdown seçenekleri
    dropdown_options = []
    if not df.empty:
        unique_products = df["Ürün Adı"].unique()
        dropdown_options = [{"label": product, "value": product} for product in unique_products]
    
    # Son güncelleme zamanı
    last_update = "Son güncelleme: Henüz güncelleme yapılmadı"
    if data and "last_update" in data[0]:
        last_update = f"Son güncelleme: {data[0]['last_update']}"
    
    return dropdown_options, dropdown_options[0]["value"] if dropdown_options else None, df.to_dict("records"), last_update

@app.callback(
    [Output("price-comparison-graph", "figure"),
     Output("product-image-container", "children")],
    [Input("product-dropdown", "value"),
     Input("product-table", "data")],
    prevent_initial_call=True
)
def update_graph(selected_product, table_data):
    """Seçilen ürün için fiyat karşılaştırma grafiğini günceller."""
    if not selected_product or not table_data:
        return px.bar(title="Lütfen bir ürün seçin"), []
    
    # Seçilen ürün için verileri filtrele
    df = pd.DataFrame(table_data)
    filtered_df = df[df["Ürün Adı"] == selected_product].copy()
    
    if filtered_df.empty:
        return px.bar(title=f"{selected_product} için veri bulunamadı"), []
    
    # Ürün resmini al
    product_image = filtered_df["Resim"].iloc[0] if "Resim" in filtered_df.columns else ""
    image_element = []
    if product_image:
        image_element = [
            html.Div([
                html.Img(src=product_image, className="product-image"),
                html.P(selected_product, className="product-title")
            ])
        ]
    
    # Satıcıları fiyata göre sırala
    filtered_df = filtered_df.sort_values("Fiyat")
    
    # Kendi mağazamı vurgula
    filtered_df["Renk"] = "Rakip"
    filtered_df.loc[filtered_df["Satıcı"] == "Kendi Mağazam", "Renk"] = "Kendi Mağazam"
    
    # Grafiği oluştur
    fig = px.bar(
        filtered_df,
        x="Satıcı",
        y="Fiyat",
        color="Renk",
        title=f"{selected_product} - Fiyat Karşılaştırması",
        color_discrete_map={"Kendi Mağazam": "#007bff", "Rakip": "#6c757d"},
        labels={"Fiyat": "Fiyat (TL)"},
        text_auto='.2f'
    )
    
    fig.update_layout(
        xaxis_title="Satıcı",
        yaxis_title="Fiyat (TL)",
        plot_bgcolor="white",
        font=dict(family="Arial", size=12),
        margin=dict(l=40, r=40, t=50, b=40),
    )
    
    return fig, image_element

@app.callback(
    Output("refresh-output", "children"),
    [Input("refresh-button", "n_clicks")],
    prevent_initial_call=True
)
def show_refresh_message(n_clicks):
    """Yenileme işlemi sonucunu gösterir."""
    if n_clicks:
        return html.Div("Veriler güncellendi!", style={"marginTop": "10px", "color": "green"})
    return ""

# CSS stilleri
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                font-family: "Segoe UI", Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f5f5;
                color: #333;
            }
            
            .header {
                background-color: #007bff;
                color: white;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .header-title {
                margin: 0;
                font-size: 28px;
            }
            
            .header-description {
                margin: 10px 0 20px;
                font-size: 16px;
                opacity: 0.9;
            }
            
            .header-controls {
                display: flex;
                align-items: center;
            }
            
            .control-button {
                background-color: white;
                color: #007bff;
                border: none;
                padding: 10px 15px;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
                transition: background-color 0.3s;
            }
            
            .control-button:hover {
                background-color: #f0f0f0;
            }
            
            .last-update-time {
                margin-top: 10px;
                font-size: 14px;
                opacity: 0.9;
            }
            
            .content {
                padding: 20px;
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .card {
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
                margin-bottom: 20px;
            }
            
            .dropdown {
                margin-bottom: 15px;
            }
            
            h2 {
                margin-top: 0;
                margin-bottom: 15px;
                color: #333;
                font-size: 20px;
            }
            
            .image-container {
                display: flex;
                justify-content: center;
                margin-top: 20px;
            }
            
            .product-image {
                max-width: 200px;
                max-height: 200px;
                border-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .product-title {
                text-align: center;
                margin-top: 10px;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

if __name__ == "__main__":
    app.run_server(debug=True, port=8053)
