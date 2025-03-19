#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
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

def test_selectors(url):
    """Belirtilen URL'deki CSS seçicileri test eder."""
    driver = setup_driver()
    try:
        logger.info(f"URL açılıyor: {url}")
        driver.get(url)
        time.sleep(5)  # Sayfanın yüklenmesi için bekle
        
        # Sayfa kaynağını kaydet
        with open('page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.info("Sayfa kaynağı 'page_source.html' dosyasına kaydedildi.")
        
        # Farklı ürün seçicilerini dene
        selectors = [
            '.p-card-wrppr',  # Standart mağaza sayfası
            '.product-card',   # Arama sonuçları sayfası
            '.product-item',   # Alternatif tasarım
            '.product-box',    # Başka bir alternatif
            '.prdct-cntnr-wrppr', # Yeni tasarım
            '.srch-prdct-cntnr', # Arama sonuçları
            '.prdct-desc-cntnr', # Ürün açıklaması
            '.p-card', # Kart
            '.product', # Genel ürün
            '.prdct' # Kısaltma
        ]
        
        results = {}
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            results[selector] = len(elements)
            logger.info(f"Seçici '{selector}': {len(elements)} element bulundu")
            
            if len(elements) > 0:
                logger.info(f"İlk element HTML: {elements[0].get_attribute('outerHTML')[:200]}...")
                
                # İlk elementin içindeki alt elementleri kontrol et
                for i, element in enumerate(elements[:3]):  # İlk 3 elementi kontrol et
                    logger.info(f"Element {i+1} için alt elementler:")
                    
                    # İsim seçicileri
                    name_selectors = ['.prdct-desc-cntnr-name', '.product-name', '.name', '.title', 'h3', '.prdct-name']
                    for name_selector in name_selectors:
                        name_elements = element.find_elements(By.CSS_SELECTOR, name_selector)
                        if name_elements:
                            logger.info(f"  İsim seçici '{name_selector}': {name_elements[0].text}")
                    
                    # Fiyat seçicileri
                    price_selectors = ['.prc-box-dscntd', '.price', '.product-price', '.discounted-price', '.prc', '.prc-cntnr']
                    for price_selector in price_selectors:
                        price_elements = element.find_elements(By.CSS_SELECTOR, price_selector)
                        if price_elements:
                            logger.info(f"  Fiyat seçici '{price_selector}': {price_elements[0].text}")
                    
                    # URL seçicileri
                    url_elements = element.find_elements(By.CSS_SELECTOR, 'a')
                    if url_elements:
                        logger.info(f"  URL: {url_elements[0].get_attribute('href')}")
                    
                    # Resim seçicileri
                    img_selectors = ['img.p-card-img', 'img.product-image', 'img', '.image-container img', '.img-container img']
                    for img_selector in img_selectors:
                        img_elements = element.find_elements(By.CSS_SELECTOR, img_selector)
                        if img_elements:
                            logger.info(f"  Resim seçici '{img_selector}': {img_elements[0].get_attribute('src')}")
        
        # Sonuçları JSON olarak kaydet
        with open('selector_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Seçici sonuçları 'selector_results.json' dosyasına kaydedildi.")
        
    except Exception as e:
        logger.error(f"Seçiciler test edilirken hata: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
        logger.info("Tarayıcı kapatıldı.")

if __name__ == "__main__":
    # Test URL'si
    test_url = "https://www.trendyol.com/sr?mid=1010350&os=1"
    
    # Seçicileri test et
    test_selectors(test_url)
