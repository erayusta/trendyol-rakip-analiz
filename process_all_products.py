#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import json
import logging
import glob
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import re
import argparse
from datetime import datetime

# .env dosyasını yükle
load_dotenv()

# Dosya yolları
PRODUCTS_FILE = os.getenv('PRODUCTS_FILE', 'products.json')
COMPETITOR_DATA_FILE = os.getenv('COMPETITOR_DATA_FILE', 'all_competitor_prices.json')
PRODUCT_DATA_DIR = os.getenv('PRODUCT_DATA_DIR', 'product_data')

# Trendyol ayarları
TRENDYOL_SHOP_URL = os.getenv('TRENDYOL_SHOP_URL', 'https://www.trendyol.com/sr?mid=1010350&os=1')
TRENDYOL_COOKIES = os.getenv('TRENDYOL_COOKIES', '')

# Bekleme ayarları
WAIT_AFTER_PRODUCTS = int(os.getenv('WAIT_AFTER_PRODUCTS', 5))
WAIT_TIME_SECONDS = int(os.getenv('WAIT_TIME_SECONDS', 5))

# Logging ayarları
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Logging ayarları
logging_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_driver():
    """Selenium WebDriver'ı başlatır."""
    try:
        # Chrome ayarlarını yapılandır
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        
        # Cloudflare tespitini atlatmak için ek ayarlar
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Headless modu (opsiyonel)
        # chrome_options.add_argument("--headless")
        
        # Manuel olarak indirilen ChromeDriver'ı kullan
        driver_path = os.path.join(os.getcwd(), "drivers", "chromedriver-mac-arm64", "chromedriver")
        logger.info(f"Manuel olarak indirilen ChromeDriver kullanılıyor: {driver_path}")
        
        # Service oluştur
        service = Service(driver_path)
        
        # Chrome tarayıcısını başlat
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        
        return driver
    except Exception as e:
        logger.error(f"Chrome başlatılırken hata: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise

def add_cookies(driver):
    """Tarayıcıya çerezleri ekler."""
    if not TRENDYOL_COOKIES:
        logger.warning("TRENDYOL_COOKIES çevresel değişkeni tanımlanmamış. Cloudflare koruması aşılamayabilir.")
        return
    
    # Çerezleri ayır ve ekle
    cookies_str = TRENDYOL_COOKIES
    cookie_pairs = cookies_str.split(';')
    
    for cookie_pair in cookie_pairs:
        if '=' in cookie_pair:
            name, value = cookie_pair.strip().split('=', 1)
            try:
                # Önce sayfayı yükle, sonra çerezleri ekle
                current_url = driver.current_url
                domain = '.trendyol.com'
                if 'trendyol.com' in current_url:
                    driver.add_cookie({'name': name, 'value': value, 'domain': domain})
            except Exception as e:
                logger.error(f"Çerez eklenirken hata oluştu: {str(e)}")
    
    logger.info("Çerezler tarayıcıya eklendi.")

def get_products_from_shop(driver, page_limit=1):
    """Mağaza sayfasından ürünleri çeker."""
    try:
        logger.info(f"Mağaza URL'si açılıyor: {TRENDYOL_SHOP_URL}")
        driver.get(TRENDYOL_SHOP_URL)
        time.sleep(5)  # Sayfanın yüklenmesi için bekle
        
        # Sayfayı açtıktan sonra çerezleri ekle
        add_cookies(driver)
        
        # Sayfayı yenile
        driver.refresh()
        time.sleep(5)  # Yenileme sonrası sayfanın yüklenmesi için bekle
        
        # Sayfa kaynağını kaydet
        with open('page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.info("Sayfa kaynağı 'page_source.html' dosyasına kaydedildi.")
        
        # Toplam ürün sayısını bul
        total_products = 0
        try:
            # Başlık veya açıklama metnini bul
            description_element = driver.find_element(By.CSS_SELECTOR, '.dscrptn-V2 h2, .dscrptn h2')
            description_text = description_element.text
            
            # "X sonuç listeleniyor" formatından sayıyı çıkar
            import re
            match = re.search(r'(\d+)\s+sonuç', description_text)
            if match:
                total_products = int(match.group(1))
                logger.info(f"Toplam {total_products} ürün bulundu.")
        except Exception as e:
            logger.warning(f"Toplam ürün sayısı bulunamadı: {str(e)}")
        
        all_products = []
        current_page = 1
        max_pages = (total_products + 23) // 24  # Her sayfada 24 ürün olduğunu varsayalım
        
        if max_pages == 0:
            max_pages = 1  # En az 1 sayfa olmalı
            
        logger.info(f"Toplam {max_pages} sayfa taranacak.")
        
        # Sayfa limitini uygula
        if page_limit and page_limit < max_pages:
            max_pages = page_limit
            logger.info(f"Sayfa limiti nedeniyle sadece {page_limit} sayfa taranacak.")
        
        # Tüm sayfaları dolaş
        while current_page <= max_pages:
            if current_page > 1:
                # Sonraki sayfa için URL oluştur
                page_url = TRENDYOL_SHOP_URL
                if '?' in page_url:
                    if '&pi=' in page_url:
                        page_url = re.sub(r'&pi=\d+', f'&pi={current_page}', page_url)
                    else:
                        page_url += f'&pi={current_page}'
                else:
                    page_url += f'?pi={current_page}'
                
                logger.info(f"Sayfa {current_page} açılıyor: {page_url}")
                driver.get(page_url)
                time.sleep(5)  # Sayfanın yüklenmesi için bekle
            
            # Test sonuçlarına göre doğru seçiciyi kullan
            product_elements = driver.find_elements(By.CSS_SELECTOR, '.p-card-wrppr')
            
            if not product_elements:
                logger.warning("Hiçbir ürün elementi bulunamadı. Alternatif seçiciler deneniyor...")
                # Alternatif seçicileri dene
                selectors = [
                    '.prdct-desc-cntnr',  # Ürün açıklama konteyneri
                    '.product-card',   # Arama sonuçları sayfası
                    '.product-item',   # Alternatif tasarım
                    '.product-box'     # Başka bir alternatif
                ]
                
                for selector in selectors:
                    product_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if product_elements:
                        logger.info(f"Ürün elementleri '{selector}' seçicisi ile bulundu: {len(product_elements)} adet")
                        break
            
            if not product_elements:
                logger.warning("Hiçbir ürün elementi bulunamadı. Sayfa yapısı değişmiş olabilir.")
                return []
            
            logger.info(f"Toplam {len(product_elements)} ürün bulundu.")
            
            products = []
            for i, element in enumerate(product_elements):
                try:
                    # Ürün bilgilerini çıkar
                    product_name = ""
                    try:
                        # Test sonuçlarına göre doğru seçiciyi kullan
                        product_name_element = element.find_element(By.CSS_SELECTOR, '.prdct-desc-cntnr-name, h3')
                        product_name = product_name_element.text.strip()
                    except Exception as e:
                        logger.warning(f"Ürün {i+1} için isim bulunamadı: {str(e)}")
                    
                    # Ürün URL'sini bul
                    product_url = ""
                    try:
                        # Önce doğrudan a etiketini bul
                        url_elements = element.find_elements(By.CSS_SELECTOR, 'a')
                        if url_elements:
                            product_url = url_elements[0].get_attribute('href')
                        else:
                            # Eğer a etiketi bulunamazsa, üst elementi kontrol et
                            parent_element = element.find_element(By.XPATH, '..')
                            if parent_element.tag_name == 'a':
                                product_url = parent_element.get_attribute('href')
                            else:
                                # Eğer üst element a değilse, içindeki a elementini ara
                                url_element = parent_element.find_element(By.CSS_SELECTOR, 'a')
                                product_url = url_element.get_attribute('href')
                    except Exception as e:
                        logger.warning(f"Ürün {i+1} için URL bulunamadı: {str(e)}")
                    
                    # Ürün ID'sini URL'den çıkar
                    product_id = None
                    if product_url:
                        # URL formatı: https://www.trendyol.com/brand/name-p-123456789
                        parts = product_url.split('-p-')
                        if len(parts) > 1:
                            product_id = parts[1].split('?')[0].strip()
                            logger.info(f"Ürün ID: {product_id}, URL: {product_url}")
                        else:
                            logger.warning(f"Ürün ID bulunamadı, URL: {product_url}")
                    else:
                        logger.warning(f"Ürün URL'si bulunamadı: {product_name}")
                    
                    # Ürün fiyatını bul
                    product_price = ""
                    try:
                        # Fiyat seçicileri
                        price_selectors = ['.prc-box-dscntd', '.price', '.product-price', '.discounted-price', '.prc', '.prc-cntnr']
                        for price_selector in price_selectors:
                            try:
                                price_elements = element.find_elements(By.CSS_SELECTOR, price_selector)
                                if price_elements:
                                    product_price = price_elements[0].text.strip()
                                    break
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"Ürün {i+1} için fiyat bulunamadı: {str(e)}")
                    
                    # Ürün resmini bul
                    product_image = ""
                    try:
                        # Resim seçicileri
                        img_selectors = ['img.p-card-img', 'img.product-image', 'img', '.image-container img', '.img-container img']
                        for img_selector in img_selectors:
                            try:
                                img_elements = element.find_elements(By.CSS_SELECTOR, img_selector)
                                if img_elements:
                                    product_image = img_elements[0].get_attribute('src')
                                    break
                            except:
                                continue
                        
                        # Eğer element içinde resim bulunamadıysa, üst elementte ara
                        if not product_image:
                            parent_element = element.find_element(By.XPATH, '..')
                            img_elements = parent_element.find_elements(By.CSS_SELECTOR, 'img')
                            if img_elements:
                                product_image = img_elements[0].get_attribute('src')
                    except Exception as e:
                        logger.warning(f"Ürün {i+1} için resim bulunamadı: {str(e)}")
                    
                    # Ürün bilgilerini listeye ekle
                    if product_name and product_url:
                        product = {
                            "product_id": product_id,
                            "product_name": product_name,
                            "my_price": product_price,
                            "product_url": product_url,
                            "product_image": product_image
                        }
                        products.append(product)
                        logger.info(f"Ürün {i+1}: {product_name} - {product_price}")
                    
                except Exception as e:
                    logger.error(f"Ürün çıkarılırken hata: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            # Ürünleri kaydet
            all_products.extend(products)
            logger.info(f"Toplam {len(all_products)} ürün bulundu.")
            
            current_page += 1
        
        # Ürünleri kaydet
        with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)
        logger.info(f"Toplam {len(all_products)} ürün '{PRODUCTS_FILE}' dosyasına kaydedildi.")
        
        return all_products
    except Exception as e:
        logger.error(f"Ürünler çekilirken hata: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def extract_product_json(driver, page_source):
    """Sayfa kaynağından ürün JSON verisini çıkarır."""
    try:
        # JavaScript ile doğrudan değişkeni almayı dene
        try:
            product_data = driver.execute_script("return window.__PRODUCT_DETAIL_APP_INITIAL_STATE__")
            if product_data:
                logger.info("JavaScript ile ürün verisi alındı.")
                return product_data
        except Exception as e:
            logger.error(f"JavaScript ile ürün verisi alınamadı: {str(e)}")
        
        # Regex ile JSON verisini çıkar
        pattern = r'window\.__PRODUCT_DETAIL_APP_INITIAL_STATE__\s*=\s*({.*?});'
        matches = re.search(pattern, page_source, re.DOTALL)
        
        if matches:
            json_str = matches.group(1)
            try:
                product_data = json.loads(json_str)
                logger.info("Regex ile ürün verisi alındı.")
                return product_data
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse hatası: {str(e)}")
                # Hatalı JSON'ı kaydet
                with open(f'error_product_json.txt', 'w', encoding='utf-8') as f:
                    f.write(json_str)
                logger.info("Hatalı JSON 'error_product_json.txt' dosyasına kaydedildi.")
        else:
            logger.warning("Sayfada JSON verisi bulunamadı.")
        
        return None
    except Exception as e:
        logger.error(f"Ürün JSON verisi çıkarılırken hata: {str(e)}")
        return None

def process_product(driver, product, index, total):
    """Bir ürünü işler ve rakip fiyatlarını çeker."""
    product_name = product.get('product_name', 'Bilinmeyen Ürün')
    product_url = product.get('product_url', '')
    
    logger.info(f"İşleniyor: {index}/{total} - {product_name}")
    
    if not product_url:
        logger.error(f"Ürün URL'si bulunamadı: {product_name}")
        return None
    
    try:
        # Ürün sayfasını aç
        driver.get(product_url)
        time.sleep(5)  # Sayfanın yüklenmesi için bekle
        
        # Ürün ID'sini URL'den çıkar (eğer daha önce çıkarılmadıysa)
        product_id = product.get('product_id')
        if not product_id:
            # URL formatı: https://www.trendyol.com/brand/name-p-123456789
            parts = product_url.split('-p-')
            if len(parts) > 1:
                product_id = parts[1].split('?')[0].strip()
                product['product_id'] = product_id
                logger.info(f"Ürün ID URL'den çıkarıldı: {product_id}")
            else:
                logger.warning(f"Ürün ID URL'den çıkarılamadı: {product_url}")
        
        # Hata ayıklama için sayfa kaynağını kaydet
        with open('product_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        
        # Ürün JSON verisini çıkar
        product_json = extract_product_json(driver, driver.page_source)
        if product_json:
            # JSON verisini kaydet
            product_json_file = f'{PRODUCT_DATA_DIR}/product_json_{product_id}.json'
            with open(product_json_file, 'w', encoding='utf-8') as f:
                json.dump(product_json, f, ensure_ascii=False, indent=2)
            logger.info(f"Ürün JSON verisi '{product_json_file}' dosyasına kaydedildi.")
            
            # Rakip fiyatlarını çıkar
            competitor_prices = extract_competitor_prices(product_json, product)
            return competitor_prices  # Artık extract_competitor_prices her zaman bir sonuç döndürüyor
        else:
            logger.warning(f"Ürün {product_id} için JSON verisi çıkarılamadı.")
            # JSON verisi çıkarılamadıysa bile ürünü ekleyelim
            return {
                'product_id': product_id,
                'product_name': product_name,
                'product_image': product.get('product_image', ''),
                'product_url': product_url,
                'my_price': product.get('my_price', ''),
                'competitors': []
            }
        
    except Exception as e:
        logger.error(f"Ürün {product_id} işlenirken hata: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def extract_competitor_prices(product_json, product):
    """Ürün JSON verisinden rakip fiyatlarını çıkarır."""
    try:
        product_id = product.get('product_id')
        product_name = product.get('product_name', 'Bilinmeyen Ürün')
        my_price = product.get('my_price', '')
        product_image = product.get('product_image', '')
        product_url = product.get('product_url', '')
        
        if not product_id:
            logger.error(f"Ürün ID'si bulunamadı: {product_name}")
            return None
        
        # Kendi fiyatımızı JSON dosyasından al
        product_detail = product_json.get('product', {})
        if not my_price and product_detail:
            price_info = product_detail.get('price', {})
            discounted_price = price_info.get('discountedPrice', {})
            my_price = discounted_price.get('text', '')
            logger.info(f"Ürün {product_id} için fiyat JSON'dan alındı: {my_price}")
        
        # Rakip fiyatlarını çıkar - product_json içindeki otherMerchants alanından
        # Önce product_detail_context'i kontrol et (JSON yapısı değişebilir)
        other_merchants = product_detail.get('otherMerchants', [])
        
        # Eğer bulamazsak, kök seviyede de kontrol et
        if not other_merchants:
            other_merchants = product_json.get('otherMerchants', [])
            
        if not other_merchants:
            logger.warning(f"Ürün {product_id} için rakip satıcı bulunamadı.")
            # Rakip yoksa kendi ürünümüzü ekleyelim
            result = {
                'product_id': product_id,
                'product_name': product_name,
                'product_image': product_image,
                'product_url': product_url,
                'my_price': my_price,
                'competitors': []
            }
            return result
        
        competitors = []
        for merchant in other_merchants:
            merchant_info = merchant.get('merchant', {})
            merchant_name = merchant_info.get('name', 'Bilinmeyen Satıcı')
            merchant_price = merchant.get('price', {}).get('discountedPrice', {}).get('text', '')
            merchant_rating = merchant_info.get('sellerScore', 0)
            
            competitor = {
                'name': merchant_name,
                'price': merchant_price,
                'rating': merchant_rating
            }
            competitors.append(competitor)
        
        # Rakip fiyatlarını sırala
        competitors = sorted(competitors, key=lambda x: float(x['price'].replace('TL', '').replace('.', '').replace(',', '.').strip()) if x['price'] else float('inf'))
        
        # Sonuç objesini oluştur
        result = {
            'product_id': product_id,
            'product_name': product_name,
            'product_image': product_image,
            'product_url': product_url,
            'my_price': my_price,
            'competitors': competitors,
            'last_update': datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Ürün {product_id} için rakip fiyatları çıkarılırken hata: {str(e)}")
        return None

def process_all_products(limit=None, page_limit=None):
    """Tüm ürünleri işler."""
    try:
        # Komut satırı argümanlarını işle
        parser = argparse.ArgumentParser(description='Trendyol ürünlerini işle ve rakip fiyatlarını çek.')
        parser.add_argument('--only-fetch', action='store_true', help='Sadece ürünleri çek, işleme')
        parser.add_argument('--only-process', action='store_true', help='Sadece mevcut ürünleri işle, yeni çekme')
        parser.add_argument('--shop-url', type=str, help='Mağaza URL\'si')
        parser.add_argument('--limit', type=int, help='İşlenecek maksimum ürün sayısı')
        parser.add_argument('--page-limit', type=int, default=5, help='Taranacak maksimum sayfa sayısı')
        
        args = parser.parse_args()
        
        # Ürün listesini oku veya parametre olarak verilen ürünleri kullan
        if args.only_process:
            try:
                with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                    products = json.load(f)
                logger.info(f"'{PRODUCTS_FILE}' dosyasından {len(products)} ürün yüklendi.")
            except Exception as e:
                logger.error(f"Ürün dosyası yüklenirken hata: {str(e)}")
                return []
        else:
            driver = setup_driver()
            products = get_products_from_shop(driver, page_limit=args.page_limit)
            logger.info(f"Mağaza sayfasından {len(products)} ürün çekildi.")
            
            # Sadece çekme modunda ise, işleme yapma
            if args.only_fetch:
                logger.info("Sadece çekme modu seçildi. Ürünler işlenmeyecek.")
                return []
        
        logger.info(f"Toplam {len(products)} ürün işlenecek.")
        
        # product_data klasörünü oluştur (yoksa)
        os.makedirs(PRODUCT_DATA_DIR, exist_ok=True)
        
        # product_data klasörünü temizle
        import glob
        for file_path in glob.glob(f'{PRODUCT_DATA_DIR}/*'):
            try:
                os.remove(file_path)
                logger.info(f"Eski dosya silindi: {file_path}")
            except Exception as e:
                logger.error(f"Dosya silinirken hata: {str(e)}")
        
        # Tarayıcıyı başlat
        driver = setup_driver()
        logger.info("Chrome başlatıldı.")
        
        # Cookie'leri ekle
        add_cookies(driver)
        logger.info("Cookie'ler eklendi.")
        
        # Tüm ürünleri işle
        all_competitor_data = []
        
        for i, product in enumerate(products):
            if limit and i >= limit:
                break
            
            competitor_prices = process_product(driver, product, i+1, len(products))
            if competitor_prices:
                all_competitor_data.append(competitor_prices)
            
            # Her 5 üründe bir 10 saniye bekle (rate limiting önlemi)
            if (i + 1) % WAIT_AFTER_PRODUCTS == 0 and i < len(products) - 1:
                logger.info("Rate limiting önlemi: {} saniye bekleniyor...".format(WAIT_TIME_SECONDS))
                time.sleep(WAIT_TIME_SECONDS)
        
        # Tüm rakip fiyatlarını kaydet
        with open(COMPETITOR_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_competitor_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Rakip fiyatları '{COMPETITOR_DATA_FILE}' dosyasına kaydedildi.")
        
        # Tarayıcıyı kapat
        driver.quit()
        logger.info("Tarayıcı kapatıldı.")
        
        return all_competitor_data
        
    except Exception as e:
        logger.error(f"Ürünler işlenirken hata: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    
def main():
    """Ana fonksiyon."""
    import argparse
    
    # Komut satırı argümanlarını tanımla
    parser = argparse.ArgumentParser(description='Trendyol Ürün ve Rakip Fiyat Takip Aracı')
    parser.add_argument('--only-fetch', action='store_true', help='Sadece ürünleri çek, işleme')
    parser.add_argument('--only-process', action='store_true', help='Sadece mevcut ürünleri işle, yeni çekme')
    parser.add_argument('--shop-url', help='Mağaza URL\'si (varsayılan: .env dosyasındaki)')
    parser.add_argument('--limit', type=int, help='İşlenecek maksimum ürün sayısı')
    parser.add_argument('--page-limit', type=int, default=5, help='Taranacak maksimum sayfa sayısı')
    
    args = parser.parse_args()
    
    # Mağaza URL'sini güncelle (eğer belirtildiyse)
    global TRENDYOL_SHOP_URL
    if args.shop_url:
        TRENDYOL_SHOP_URL = args.shop_url
        logger.info(f"Mağaza URL'si komut satırı argümanından alındı: {TRENDYOL_SHOP_URL}")
    
    # Tarayıcıyı başlat
    driver = None
    products = None
    
    try:
        # Sadece işleme modu değilse, ürünleri çek
        if not args.only_process:
            driver = setup_driver()
            products = get_products_from_shop(driver, page_limit=args.page_limit)
            logger.info(f"Mağaza sayfasından {len(products)} ürün çekildi.")
            
            # Sadece çekme modunda ise, işleme yapma
            if args.only_fetch:
                logger.info("Sadece çekme modu seçildi. Ürünler işlenmeyecek.")
                return
        
        # Ürünleri işle
        if not args.only_fetch:
            if driver is None:
                driver = setup_driver()
            
            process_all_products(limit=args.limit, page_limit=args.page_limit)
            logger.info("Tüm ürünler işlendi.")
    
    finally:
        # Tarayıcıyı kapat
        if driver:
            driver.quit()
            logger.info("Tarayıcı kapatıldı.")

if __name__ == "__main__":
    main()
