import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import re
from datetime import datetime

def parse_pro_final():
    """
    ФИНАЛЬНАЯ ВЕРСИЯ (v3)
    Исправлены: рейтинг (2.9 кВт), цены со скидкой, поиск родителя, ошибки Python 3.12
    """
    # 1. Настройка браузера (убраны конфликтующие опции)
    options = uc.ChromeOptions()
    options.add_argument('--lang=ru')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    print("🚀 Запускаем браузер...")
    driver = uc.Chrome(options=options)
    
    try:
        url = "https://www.vseinstrumenti.ru/category/bezmaslyanye-kompressory-394/"
        print(f"🌐 Открываем: {url}")
        driver.get(url)
        
        print("⏳ Ждём загрузки... (60 сек на капчу)")
        time.sleep(60)

        # Прокрутка для подгрузки lazy-load элементов
        print("📜 Прокручиваем страницу...")
        for i in range(3):
            driver.execute_script(f"window.scrollTo(0, {(i+1) * 500});")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")

        items = []
        
        # Известные бренды
        known_brands = ['FUBAG', 'DAEWOO', 'Gigant', 'ELITECH', 'Aurora', 'DGM', 
                        'PATRIOT', 'BORT', 'DENZEL', 'CHAMPION', 'ZUBR', 'HYUNDAI', 
                        'METABO', 'KARCHER', 'Inforce', 'ЗУБР', 'Calibr', 'Pegas']

        # 2. Ищем все ссылки на товары
        links_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        print(f"\n📊 Найдено ссылок на товары: {len(links_elements)}")

        processed_links = set()

        for link_elem in links_elements:
            if len(items) >= 15: 
                break
            
            try:
                link = link_elem.get_attribute('href')
                name = link_elem.text.strip()
                
                # Пропускаем дубликаты и пустые названия
                if not link or link in processed_links or not name or len(name) < 10:
                    continue
                processed_links.add(link)

                # 3. Ищем родительский контейнер (карточку товара)
                # Поднимаемся вверх до первого div, который похож на карточку
                try:
                    parent_container = link_elem.find_element(
                        By.XPATH, 
                        "./ancestor::div[contains(@class, 'card') or contains(@class, 'product') or contains(@class, 'item') or @data-qa][1]"
                    )
                except:
                    # Фолбэк: берем просто родителя ссылки
                    parent_container = link_elem.find_element(By.XPATH, "./..")
                
                # Получаем текст ТОЛЬКО этой карточки
                block_text = parent_container.text
                
                # === БРЕНД ===
                brand = "Не определён"
                for b in known_brands:
                    if b.upper() in name.upper():
                        brand = b
                        break

                # === ЦЕНА ===
                price = "По запросу"
                old_price = ""
                
                # Ищем цены в тексте блока (формат: 14 290 ₽)
                # r'' - raw string, чтобы избежать SyntaxWarning в Python 3.12+
                prices_in_block = re.findall(r'(\d{1,3}(?:\s?\d{3})+)\s*[₽₽]', block_text)
                
                if prices_in_block:
                    # Логика скидки: если есть знак "%", то последняя цена - новая, предпоследняя - старая
                    # Используем raw string для regex
                    if re.search(r'-\d+%', block_text) and len(prices_in_block) >= 2:
                        old_price = prices_in_block[-2].replace(' ', '')
                        price = prices_in_block[-1].replace(' ', '')
                    else:
                        # Иначе первая найденная цена - текущая
                        price = prices_in_block[0].replace(' ', '')

                # === НАЛИЧИЕ ===
                stock = "Неизвестно"
                block_text_lower = block_text.lower()
                
                if "шт. в магазинах сегодня" in block_text_lower:
                    match = re.search(r'(\d+)\s*шт\.\s*в\s*магазинах', block_text_lower)
                    stock = f"{match.group(1)} шт. в магазинах" if match else "В наличии"
                elif "на складе" in block_text_lower:
                    match = re.search(r'>\s*(\d+)\s*шт\.\s*на\s*складе', block_text_lower)
                    stock = f"> {match.group(1)} шт. на складе" if match else "На складе"
                elif "в наличии" in block_text_lower:
                    stock = "В наличии"
                
                # Фолбэк: если цена есть, а наличие не нашли, считаем "В наличии"
                if stock == "Неизвестно" and price != "По запросу":
                    stock = "В наличии"

                # === АРТИКУЛ ===
                sku = ""
                # 1. Пробуем взять из названия (последние цифры)
                name_sku_match = re.search(r'(\d{5,})$', name.replace(' ', ''))
                if name_sku_match:
                    sku = name_sku_match.group(1)
                else:
                    # 2. Или из URL (последняя часть перед слешем, часто там ID товара)
                    url_match = re.search(r'/(\d{5,})-?\d*/?$', link)
                    if url_match:
                        sku = url_match.group(1)
                    # 3. Если нет, ищем 7-8 значное число в тексте, которое не является ценой
                    else:
                        all_nums = re.findall(r'\b(\d{7,8})\b', block_text)
                        clean_prices = [p.replace(' ', '') for p in prices_in_block]
                        for num in all_nums:
                            if num not in clean_prices:
                                sku = num
                                break

                # === РЕЙТИНГ И ОТЗЫВЫ (ИСПРАВЛЕНО) ===
                rating = ""
                reviews = ""
                
                # Ищем паттерн "4.5 (91)" — это надежнее, чем искать просто число
                # Регулярка ищет: число с точкой, пробелы, число в скобках
                rating_reviews_match = re.search(r'(\d\.\d)\s*\((\d+)\)', block_text)
                
                if rating_reviews_match:
                    rating = rating_reviews_match.group(1)
                    reviews = rating_reviews_match.group(2)
                else:
                    # Если не нашли пару, пробуем найти просто рейтинг (но аккуратно, чтобы не взять мощность)
                    # Рейтинг обычно от 3.0 до 5.0
                    rating_match = re.search(r'\b([3-5]\.\d)\b', block_text)
                    if rating_match:
                        rating = rating_match.group(1)

                # === ИЗОБРАЖЕНИЕ ===
                image_url = ""
                try:
                    img = parent_container.find_element(By.CSS_SELECTOR, "img")
                    src = img.get_attribute('data-src') or img.get_attribute('src')
                    if src:
                        if src.startswith('//'):
                            image_url = 'https:' + src
                        elif src.startswith('/'):
                            image_url = 'https://www.vseinstrumenti.ru' + src
                        else:
                            image_url = src
                except:
                    pass

                # === СБОРКА ЗАПИСИ ===
                item = {
                    'Наименование': name,
                    'Бренд': brand,
                    'Цена': price,
                    'Цена_со_скидкой': old_price,
                    'Наличие': stock,
                    'Артикул': sku,
                    'Рейтинг': rating,
                    'Отзывы': reviews,
                    'Ссылка_на_изображение': image_url,
                    'Ссылка_на_товар': link,
                    'Дата_парсинга': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                items.append(item)
                
                price_str = f"{price} ₽" if price != "По запросу" else price
                print(f"✓ [{len(items)}] {brand:10s} | {name[:40]} | {price_str} | {stock}")

            except Exception as e:
                # Ошибку пишем в лог, но не останавливаем скрипт
                # print(f"⚠ Ошибка на товаре: {e}") 
                continue

        # === СОХРАНЕНИЕ В EXCEL ===
        if items:
            filename = f'vsi_perfect_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            df = pd.DataFrame(items)
            df.to_excel(filename, index=False)
            
            print(f"\n{'='*70}")
            print(f"✅ ГОТОВО! Собрано {len(items)} товаров")
            print(f"📁 Файл сохранен: {filename}")
            print(f"{'='*70}")
        else:
            print("❌ Товары не найдены")

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n🔄 Закрываем браузер...")
        time.sleep(3)
        try:
            driver.quit()
        except:
            pass
        print("✅ Работа завершена")

if __name__ == "__main__":
    parse_pro_final()
