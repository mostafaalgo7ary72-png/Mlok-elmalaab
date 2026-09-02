import os
import asyncio
import requests
import json
import base64
import re
import random
import sys
import time
import pickle
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import PIL.Image
from PIL import ImageOps, ImageFilter, ImageDraw, ImageFont
import numpy as np

# ====================== إعدادات تقليل اللوج (Clean Logs) ======================
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger('googleapiclient').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('moviepy').setLevel(logging.CRITICAL)

# ====================== إصلاح توافق Pillow مع MoviePy ======================
if not hasattr(PIL.Image, 'Resampling'):
    PIL.Image.Resampling = PIL.Image
try:
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
except AttributeError:
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip
from groq import Groq
import edge_tts

# ====================== المتغيرات البيئة والإعدادات ======================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
YOUTUBE_TOKEN_B64 = os.environ.get('YOUTUBE_TOKEN')
FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID')

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
FPS = 24
HISTORY_FILE = "history.json"
SOURCE_INDEX_FILE = "source_index.json"
FAILED_LINKS_FILE = "failed_links.json"
CHANNEL_NAME_AR = "ملوك الملعب"
CHANNEL_NAME_EN = "Kings of the Stadium"

# ====================== موديلات Groq المدعومة فقط (محدث سبتمبر 2026) ======================
# llama-3.3-70b-versatile و llama-3.1-8b-instant بقوا Enterprise فقط ومش متاحين لحسابات المطورين العادية
# mixtral-8x7b-32768 و gemma2-9b-it و llama3-8b-8192 اتلغوا (decommissioned)
GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-safeguard-20b"
]

# ====================== المصادر مرقمة بالترتيب ======================
SOURCES = [
    {"id": 1, "name": "Btolat", "url": "https://www.btolat.com/news"},
    {"id": 2, "name": "Arriyadiyah", "url": "https://www.arriyadiyah.com/"},
    {"id": 3, "name": "So3ody", "url": "https://www.so3ody.com/"},
    {"id": 4, "name": "TalkSport", "url": "https://talksport.com/football/"},
    {"id": 5, "name": "London Football", "url": "https://www.football.london/"},
    {"id": 6, "name": "Yardbarker", "url": "https://www.yardbarker.com/soccer"},
    {"id": 7, "name": "FourFourTwo", "url": "https://www.fourfourtwo.com/news"},
    {"id": 8, "name": "TeamTalk", "url": "https://www.teamtalk.com/"},
    {"id": 9, "name": "Man Evening News", "url": "https://www.manchestereveningnews.co.uk/sport/football/"}
]

# ====================== الكلمات المفتاحية ======================
KEYWORDS_ARABIC = [
    "كرة القدم",
    "مباراة",
    "هدف",
    "أهداف",
    "ملخص",
    "الدوري",
    "الكأس",
    "البطولة",
    "انتقالات",
    "ميركاتو",
    "صفقة",
    "عاجل",
    "رسميا",
    "تشكيل",
    "مدرب",
    "ركلة جزاء",
    "تسلل",
    "طرد",
    "إنذار",
    "حكم",
    "فار",
    "VAR",
    "إصابة",
    "تصفيات",
    "نهائي",
    "نصف نهائي",
    "دوري أبطال",
    "الكونفدرالية",
    "الدوري الإنجليزي",
    "الدوري الإسباني",
    "الدوري السعودي",
    "دوري روشن",
    "كأس العالم",
    "كأس الأمم",
    "يورو",
    "السوبر",
    "الأهلي",
    "الزمالك",
    "بيراميدز",
    "المصري",
    "الإسماعيلي",
    "الهلال",
    "النصر",
    "الاتحاد",
    "الأهلي السعودي",
    "الشباب",
    "ريال مدريد",
    "برشلونة",
    "ليفربول",
    "مانشستر سيتي",
    "مانشستر يونايتد",
    "أرسنال",
    "تشيلسي",
    "بايرن ميونخ",
    "باريس سان جيرمان",
    "محمد صلاح",
    "صلاح",
    "كريستيانو رونالدو",
    "رونالدو",
    "ميسي",
    "نيمار",
    "بنزيما"
]

KEYWORDS_ENGLISH = [
    "football",
    "soccer",
    "goal",
    "match",
    "league",
    "cup",
    "transfer",
    "premier league",
    "laliga",
    "serie a",
    "bundesliga",
    "champions league",
    "world cup",
    "euro",
    "real madrid",
    "barcelona",
    "liverpool",
    "man city",
    "arsenal",
    "al ahly",
    "zamalek",
    "al hilal",
    "al nassr",
    "salah",
    "messi",
    "ronaldo",
    "mbappe",
    "haaland",
    "benzema"
]

STRICT_KEYWORDS = KEYWORDS_ARABIC + KEYWORDS_ENGLISH

BLACKLIST_KEYWORDS = [
    "basketball",
    "tennis",
    "nba",
    "f1",
    "politics",
    "economy",
    "art",
    "cinema",
    "weather",
    "crime",
    "election",
    "كرة سلة",
    "تنس",
    "سياسة",
    "اقتصاد",
    "فن",
    "سينما",
    "طقس",
    "جريمة"
]


# ====================== نظام ترتيب المصادر (محسن) ======================
def get_current_source_index():
    """الحصول على رقم المصدر الحالي من الملف"""
    if os.path.exists(SOURCE_INDEX_FILE):
        try:
            with open(SOURCE_INDEX_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('current_index', 0)
        except Exception as e:
            print(f"⚠️ خطأ في قراءة ملف المصادر: {e}")
            return 0
    return 0


def save_next_source_index(current_index):
    """حفظ رقم المصدر التالي للتشغيل القادم"""
    next_index = (current_index + 1) % len(SOURCES)
    
    data = {
        'current_index': next_index,
        'last_used_index': current_index,
        'last_used_source': SOURCES[current_index]['name'],
        'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'total_sources': len(SOURCES)
    }
    
    with open(SOURCE_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"📝 تم حفظ المصدر التالي: [{next_index + 1}/{len(SOURCES)}] {SOURCES[next_index]['name']}")


def get_current_source():
    """الحصول على المصدر الحالي للاستخدام"""
    current_index = get_current_source_index()
    source = SOURCES[current_index]
    
    print(f"")
    print(f"📌 ═══════════════════════════════════════════════")
    print(f"📌 المصدر الحالي: [{source['id']}/{len(SOURCES)}] {source['name']}")
    print(f"📌 الرابط: {source['url']}")
    print(f"📌 ═══════════════════════════════════════════════")
    print(f"")
    
    return current_index, source


# ====================== دوال الهيستوري ======================
def load_history():
    """تحميل كل الروابط من الهيستوري"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict):
                        return {item['link'] for item in data if 'link' in item}
                    else:
                        return set(data)
        except Exception as e:
            print(f"⚠️ خطأ في قراءة الهيستوري: {e}")
            return set()
    return set()


def save_history(link, source_name):
    """حفظ الرابط الجديد في الهيستوري مع كل الروابط السابقة"""
    data = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception as e:
            print(f"⚠️ خطأ في قراءة الهيستوري للحفظ: {e}")
            data = []
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_entry = {
        "link": link,
        "source": source_name,
        "added_at": current_time
    }
    
    data.append(new_entry)
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"✅ تم حفظ الرابط في الهيستوري (إجمالي: {len(data)} رابط)")


# ====================== دوال الروابط الفاشلة ======================
def save_failed_link(link, source_name, reason):
    """حفظ رابط فشل مع سبب الفشل في ملف منفصل عشان نراجعهم"""
    data = []
    if os.path.exists(FAILED_LINKS_FILE):
        try:
            with open(FAILED_LINKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception as e:
            print(f"⚠️ خطأ في قراءة ملف الروابط الفاشلة: {e}")
            data = []

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_entry = {
        "link": link,
        "source": source_name,
        "reason": reason,
        "failed_at": current_time
    }

    data.append(new_entry)

    with open(FAILED_LINKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"📝 تم تسجيل رابط فاشل ({reason}): {link}")


# ====================== دوال التنظيف ======================
def clean_text_strict(text):
    """تنظيف النص من الحروف الإنجليزية والرموز الغريبة"""
    if not text:
        return ""
    text = re.sub(r'[a-zA-Z]', '', text)
    text = re.sub(r'[^\u0600-\u06FF0-9\s\.\,\!\?\(\)\-\#\_]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def download_and_flip_image(url, filename):
    """تحميل الصورة وعكسها أفقياً"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            img = PIL.Image.open(filename)
            img = img.convert('RGB')
            img = ImageOps.mirror(img)
            img.save(filename, 'JPEG', quality=95)
            print(f"✅ تم تحميل وعكس الصورة: {filename}")
            return True
        else:
            print(f"❌ فشل تحميل الصورة - Status: {response.status_code}")
    except Exception as e:
        print(f"❌ فشل تحميل/عكس الصورة: {e}")
    return False


# ====================== استخراج المحتوى ======================
def get_article_content(url):
    """استخراج محتوى المقال من الرابط"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = ""
        if soup.title:
            title = soup.title.string
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()

        img_url = None
        og_image = soup.find("meta", property="og:image")
        if og_image:
            img_url = og_image.get("content")
        
        if not img_url:
            tw_image = soup.find("meta", attrs={"name": "twitter:image"})
            if tw_image:
                img_url = tw_image.get("content")
        
        if not img_url:
            first_img = soup.find("img", src=True)
            if first_img:
                img_url = first_img.get("src")
        
        if not img_url:
            return None

        paragraphs = soup.find_all('p')
        text_content = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30])
        
        if len(text_content) < 500:
            return None
        
        return {
            'title': title,
            'text': text_content,
            'image': img_url,
            'url': url
        }
    except Exception as e:
        return None


# ====================== البحث عن الأخبار (بالترتيب) ======================
def find_best_news():
    """البحث عن أفضل خبر بالترتيب - بتجرب كل المصادر في نفس التشغيلة قبل ما توقف"""
    history = load_history()
    
    total_sources = len(SOURCES)
    attempts = 0
    
    while attempts < total_sources:
        attempts += 1
        current_index, source = get_current_source()
        save_next_source_index(current_index)
        
        try:
            print(f"🔎 جاري البحث في: {source['name']}...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            resp = requests.get(source['url'], headers=headers, timeout=10)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            links = soup.find_all('a', href=True)
            valid_links = []
            
            for a in links:
                href = a['href']
                if not href.startswith('http'):
                    base = "/".join(source['url'].split('/')[:3])
                    if href.startswith('/'):
                        href = base + href
                    else:
                        href = base + '/' + href
                
                if href in history:
                    continue
                
                check_str = (href + " " + a.get_text()).lower()
                
                is_sports = False
                for kw in STRICT_KEYWORDS:
                    if kw.lower() in check_str:
                        is_sports = True
                        break
                
                if not is_sports:
                    continue
                
                is_blacklisted = False
                for bl in BLACKLIST_KEYWORDS:
                    if bl.lower() in check_str:
                        is_blacklisted = True
                        break
                
                if is_blacklisted:
                    continue

                if len(a.get_text().strip()) > 15:
                    valid_links.append(href)
            
            print(f"📋 تم العثور على {len(valid_links)} رابط محتمل")
            
            if valid_links:
                random.shuffle(valid_links)
                for chosen_link in valid_links[:10]:
                    data = get_article_content(chosen_link)
                    
                    if data and len(data['text']) > 800 and data['image']:
                        title_check = data['title'].lower()
                        has_keyword = False
                        for kw in STRICT_KEYWORDS:
                            if kw.lower() in title_check:
                                has_keyword = True
                                break
                        
                        if has_keyword:
                            print(f"🎯 تم العثور على خبر مناسب!")
                            data['source_name'] = source['name']
                            data['source_id'] = source['id']
                            return data
                        else:
                            save_failed_link(chosen_link, source['name'], "العنوان لا يحتوي على كلمات مفتاحية رياضية")
                    else:
                        save_failed_link(chosen_link, source['name'], "فشل استخراج المحتوى / المحتوى قصير / لا توجد صورة")
            
            print(f"😔 لم يتم العثور على خبر مناسب في {source['name']}")
            
        except Exception as e:
            print(f"❌ خطأ في المصدر {source['name']}: {e}")
        
        if attempts < total_sources:
            print(f"➡️ جاري الانتقال للمصدر التالي في نفس التشغيلة...")
    
    print(f"😴 تم تجربة كل المصادر ({total_sources}) في هذه التشغيلة ولم يتم العثور على خبر مناسب")
    return None


# ====================== الذكاء الاصطناعي (محتوى طويل) ======================
def generate_ai_content(article):
    """توليد المحتوى باستخدام الذكاء الاصطناعي"""
    client = Groq(api_key=GROQ_API_KEY)
    
    # تقصير نص المقال عشان مايتجاوزش حد التوكنز بالدقيقة (TPM) في الخطة المجانية
    MAX_ARTICLE_CHARS = 3000
    article_text = article['text']
    if len(article_text) > MAX_ARTICLE_CHARS:
        article_text = article_text[:MAX_ARTICLE_CHARS]
    
    prompt = f"""
أنت محلل رياضي محترف ومعلق كروي خبير.
سأعطيك خبر رياضي، مطلوب منك إنشاء محتوى احترافي باللغة العربية الفصحى.

النص الأصلي:
العنوان: {article['title']}
المحتوى: {article_text}

التعليمات الإلزامية الصارمة:
1. لا تخترع أي معلومات غير موجودة في النص الأصلي إطلاقاً
2. استخدم التفاصيل الموجودة في النص دون حشو
3. اقرأ الخبر كاملاً وأعد صياغته بأسلوب احترافي
4. اكتب بأسلوب سردي تحليلي غني بالمفردات العربية الفصحى
5. النص يجب أن يكون متوسط الطول (700-900 كلمة) لتغطية 3-4 دقائق
6. البنية المطلوبة:
   - Hook: جملة افتتاحية قوية جداً تجذب المشاهد فوراً
   - Body: شرح مفصل للخبر مع تحليل ودقة
   - CTA: دعوة للاشتراك والتفاعل في النهاية

7. العنوان يجب أن يكون:
   - 50-60 حرف فقط
   - يحتوي كلمات مفتاحية قوية للسيو
   - جذاب ومثير للفضول

8. الوصف يجب أن يكون:
   - 120 كلمة تقريباً
   - يبدأ بـ Hook قوي
   - يحتوي Body مختصر
   - ينتهي بـ CTA

9. الهاشتاقات:
   - 15 هاشتاق بالضبط
   - كلها مرتبطة بمحتوى الفيديو والخبر
   - باللغة العربية

10. نص الشورتس:
    - 30-45 ثانية فقط
    - Hook + Body + CTA
    - بدون هاشتاقات في النص
    - مختصر ومركز

المطلوب بصيغة JSON فقط:
{{
    "video_title": "عنوان جذاب للفيديو الطويل (50-60 حرف) يحتوي كلمات مفتاحية قوية",
    "video_script": "النص الكامل للفيديو (Hook + Body + CTA) - 700-900 كلمة",
    "video_description": "وصف احترافي 120 كلمة (Hook + Body + CTA)",
    "shorts_title": "عنوان مختصر وجذاب للشورتس (40 حرف)",
    "shorts_script": "نص مختصر للشورتس (Hook + Body + CTA) - 30-45 ثانية فقط بدون هاشتاقات",
    "hashtags": ["#هاشتاق1", "#هاشتاق2", "... 15 هاشتاق مرتبط بالمحتوى"],
    "facebook_post": "منشور فيسبوك جذاب مع إيموجي"
}}
"""
    
    for model in GROQ_MODELS:
        try:
            print(f"🤖 جاري التجربة مع موديل: {model}")
            
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that outputs strictly valid JSON. You write in professional Arabic Fusha (فصحى). Never invent information not in the source."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )
            
            content = json.loads(completion.choices[0].message.content)
            
            content['video_title'] = clean_text_strict(content.get('video_title', ''))
            content['video_script'] = clean_text_strict(content.get('video_script', ''))
            content['video_description'] = clean_text_strict(content.get('video_description', ''))
            content['shorts_title'] = clean_text_strict(content.get('shorts_title', ''))
            content['shorts_script'] = clean_text_strict(content.get('shorts_script', ''))
            content['facebook_post'] = clean_text_strict(content.get('facebook_post', ''))
            
            tags = []
            for t in content.get('hashtags', []):
                ct = clean_text_strict(t).replace(' ', '_')
                if ct and not ct.startswith('#'):
                    ct = '#' + ct
                if len(ct) > 2:
                    tags.append(ct)
            
            defaults = [
                "#كرة_القدم",
                "#الرياضة",
                "#أخبار_رياضية",
                "#الدوري_الانجليزي",
                "#دوري_ابطال_اوروبا",
                "#الأهلي",
                "#الزمالك",
                "#ليفربول",
                "#ريال_مدريد",
                "#محمد_صلاح",
                "#الهلال",
                "#النصر",
                "#الدوري_السعودي",
                "#مانشستر_سيتي",
                "#برشلونة",
                "#بايرن_ميونخ",
                "#ميسي",
                "#رونالدو",
                "#نيمار",
                "#عاجل"
            ]
            
            while len(tags) < 15:
                for d in defaults:
                    if d not in tags:
                        tags.append(d)
                    if len(tags) >= 15:
                        break
            
            content['hashtags'] = tags[:15]
            
            if len(content['video_title']) > 60:
                content['video_title'] = content['video_title'][:57] + "..."
            
            if len(content['shorts_title']) > 40:
                content['shorts_title'] = content['shorts_title'][:37] + "..."
            
            print(f"✅ تم توليد المحتوى بنجاح باستخدام: {model}")
            return content
        
        except Exception as e:
            print(f"⚠️ فشل الموديل {model}: {e}")
            continue
    
    print("❌ فشلت جميع الموديلات")
    return None


# ====================== توليد الصوت ======================
async def generate_audio(text, output_file):
    """توليد الصوت باستخدام Edge TTS - صوت شاكر المصري بالفصحى"""
    voice = "ar-EG-ShakirNeural"
    rate = "-5%"
    
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_file)
    
    print(f"✅ تم توليد الصوت: {output_file}")
    return output_file


# ====================== إنشاء إطار الأخبار ======================
def create_news_overlay(width, height):
    """إنشاء إطار الأخبار الاحترافي"""
    img = PIL.Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    bar_height = int(height * 0.12)
    bar_y = height - bar_height
    
    draw.rectangle([(0, bar_y), (width, height)], fill=(200, 0, 0, 230))
    draw.rectangle([(0, bar_y), (width, bar_y + 5)], fill=(255, 215, 0, 255))
    
    font = None
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "arialbd.ttf"
    ]
    
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, int(height * 0.04))
            break
        except Exception as e:
            continue
    
    if not font:
        font = ImageFont.load_default()
    
    text = f"{CHANNEL_NAME_AR} | {CHANNEL_NAME_EN}"
    
    try:
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except Exception as e:
        text_width = len(text) * 20
        text_height = 40
    
    text_x = (width - text_width) / 2
    text_y = bar_y + (bar_height - text_height) / 2 - 5
    
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
    
    badge_width = int(width * 0.13)
    badge_height = int(height * 0.05)
    badge_x = width - badge_width - 10
    badge_y = bar_y - badge_height - 10
    
    draw.rectangle([(badge_x, badge_y), (width - 10, bar_y - 10)], fill=(255, 255, 255, 255))
    
    badge_font = None
    for path in font_paths:
        try:
            badge_font = ImageFont.truetype(path, int(height * 0.03))
            break
        except Exception as e:
            continue
    
    if not badge_font:
        badge_font = font
    
    badge_text = "عاجل"
    
    try:
        badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        badge_text_width = badge_bbox[2] - badge_bbox[0]
        badge_text_height = badge_bbox[3] - badge_bbox[1]
    except Exception as e:
        badge_text_width = 60
        badge_text_height = 30
    
    badge_text_x = badge_x + (badge_width - badge_text_width) / 2
    badge_text_y = badge_y + (badge_height - badge_text_height) / 2
    
    draw.text((badge_text_x, badge_text_y), badge_text, font=badge_font, fill=(200, 0, 0, 255))
    
    overlay_path = f"overlay_{width}x{height}.png"
    img.save(overlay_path)
    
    return overlay_path


# ====================== إنشاء الفيديو مع Zoom ======================
def create_zooming_video(image_path, audio_path, output_path, width, height, is_shorts):
    """إنشاء فيديو مع تأثير الزوم"""
    try:
        video_type = "شورتس" if is_shorts else "فيديو"
        print(f"🎬 جاري المونتاج ({video_type})...")
        
        audio = AudioFileClip(audio_path)
        duration = audio.duration + 1
        
        print(f"⏱️ المدة: {duration:.1f} ثانية ({duration/60:.2f} دقيقة)")
        
        img = ImageClip(image_path)
        
        aspect_ratio = img.w / img.h
        target_ratio = width / height
        
        if aspect_ratio > target_ratio:
            img = img.resize(height=height)
            x_center = (img.w - width) / 2
            img = img.crop(x1=x_center, width=width, height=height)
        else:
            img = img.resize(width=width)
            y_center = (img.h - height) / 2
            img = img.crop(y1=y_center, width=width, height=height)
        
        if is_shorts:
            zoom_factor = 1.15
        else:
            zoom_factor = 1.08
        
        def zoom_effect(t):
            return 1 + (zoom_factor - 1) * (t / duration)
        
        zoomed_bg = (img
                     .resize(zoom_effect)
                     .set_position('center')
                     .set_duration(duration))
        
        overlay_path = create_news_overlay(width, height)
        overlay_clip = (ImageClip(overlay_path)
                        .set_duration(duration)
                        .set_position(("center", "top")))
        
        final = CompositeVideoClip(
            [zoomed_bg, overlay_clip],
            size=(width, height)
        ).set_audio(audio)
        
        final.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            verbose=False,
            logger=None
        )
        
        if os.path.exists(overlay_path):
            os.remove(overlay_path)
        
        print(f"✅ تم إنشاء {video_type}: {output_path}")
        return True
    
    except Exception as e:
        print(f"❌ Video Error: {e}")
        return False


# ====================== الرفع لليوتيوب ======================
def get_youtube_service():
    """الحصول على خدمة يوتيوب"""
    try:
        token_data = base64.b64decode(YOUTUBE_TOKEN_B64)
        
        try:
            creds = pickle.loads(token_data)
        except Exception as e:
            creds_data = json.loads(token_data.decode('utf-8'))
            creds = Credentials.from_authorized_user_info(creds_data)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        return build('youtube', 'v3', credentials=creds)
    
    except Exception as e:
        print(f"❌ Youtube Auth Error: {e}")
        return None


def upload_to_youtube(video_path, title, description, tags, is_shorts):
    """رفع الفيديو لليوتيوب"""
    youtube = get_youtube_service()
    if not youtube:
        return False
    
    video_type = "شورتس" if is_shorts else "فيديو"
    print(f"🚀 جاري رفع {video_type} لليوتيوب...")
    
    final_title = title
    if is_shorts:
        final_title = title + " #Shorts"
    
    hashtags_str = " ".join(tags)
    full_description = f"{description}\n\n{hashtags_str}"
    
    clean_tags = []
    for t in tags:
        clean_tag = t.replace("#", "").replace("_", " ")
        if clean_tag:
            clean_tags.append(clean_tag)
    
    body = {
        'snippet': {
            'title': final_title,
            'description': full_description,
            'tags': clean_tags,
            'categoryId': '17'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    try:
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        res = None
        while res is None:
            status, res = req.next_chunk()
            if status:
                print(f"   📤 تقدم الرفع: {int(status.progress() * 100)}%")
        
        video_id = res.get('id')
        print(f"✅ يوتيوب ({video_type}) تم الرفع: https://youtu.be/{video_id}")
        return True
    
    except Exception as e:
        print(f"❌ Youtube Upload Failed: {e}")
        return False


# ====================== الرفع لفيسبوك ======================
def upload_to_facebook(video_path, message_body, hashtags_list):
    """رفع الفيديو لفيسبوك"""
    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID:
        print("⚠️ فيسبوك غير مفعل - لا يوجد توكن أو Page ID")
        return False
    
    print("🚀 جاري رفع الفيديو لفيسبوك...")
    
    hashtags_str = " ".join(hashtags_list)
    full_message = f"{message_body}\n\n{hashtags_str}"
    
    url = f"https://graph-video.facebook.com/v18.0/{FACEBOOK_PAGE_ID}/videos"
    
    try:
        file_size = os.path.getsize(video_path)
        
        start_response = requests.post(
            url,
            params={
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'upload_phase': 'start',
                'file_size': file_size
            }
        ).json()
        
        session_id = start_response.get('upload_session_id')
        if not session_id:
            print(f"❌ فشل بدء رفع فيسبوك: {start_response}")
            return False
        
        with open(video_path, 'rb') as f:
            transfer_response = requests.post(
                url,
                data={
                    'access_token': FACEBOOK_ACCESS_TOKEN,
                    'upload_phase': 'transfer',
                    'start_offset': 0,
                    'upload_session_id': session_id
                },
                files={
                    'video_file_chunk': (os.path.basename(video_path), f, 'video/mp4')
                }
            )
        
        finish_response = requests.post(
            url,
            data={
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'upload_phase': 'finish',
                'upload_session_id': session_id,
                'description': full_message
            }
        ).json()
        
        if finish_response.get('success'):
            print("✅ فيسبوك تم الرفع بنجاح")
            return True
        else:
            print(f"❌ فيسبوك فشل: {finish_response}")
            return False
    
    except Exception as e:
        print(f"❌ Facebook Failed: {e}")
        return False


# ====================== التنفيذ الرئيسي ======================
async def main():
    """الدالة الرئيسية للتنفيذ"""
    print("=" * 60)
    print("⚽ بدء تشغيل بوت ملوك الملعب ⚽")
    print("=" * 60)
    print(f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 عدد المصادر: {len(SOURCES)}")
    print("=" * 60)
    
    article = find_best_news()
    if not article:
        print("😴 لم يتم العثور على أخبار كروية جديدة في هذا المصدر.")
        print("💡 سيتم الانتقال للمصدر التالي في التشغيل القادم.")
        return
    
    print(f"\n📰 الخبر المختار:")
    print(f"   المصدر: [{article['source_id']}] {article['source_name']}")
    print(f"   العنوان: {article['title'][:80]}...")
    print(f"   الرابط: {article['url']}")
    print(f"   طول المحتوى: {len(article['text'])} حرف")
    
    ai = generate_ai_content(article)
    if not ai:
        print("❌ فشل إنشاء المحتوى بالذكاء الاصطناعي")
        return
    
    print(f"\n✍️ المحتوى المُنشأ:")
    print(f"   عنوان الفيديو: {ai['video_title']}")
    print(f"   عنوان الشورتس: {ai['shorts_title']}")
    print(f"   طول سكريبت الفيديو: {len(ai['video_script'])} حرف")
    print(f"   طول سكريبت الشورتس: {len(ai['shorts_script'])} حرف")
    print(f"   عدد الهاشتاقات: {len(ai['hashtags'])}")
    
    img_file = "image.jpg"
    video_audio = "video_audio.mp3"
    shorts_audio = "shorts_audio.mp3"
    video_file = "video.mp4"
    shorts_file = "shorts.mp4"
    
    print("\n📥 تحميل الصورة...")
    if not download_and_flip_image(article['image'], img_file):
        print("❌ فشل تحميل الصورة")
        save_failed_link(article['url'], article['source_name'], "فشل تحميل صورة الخبر")
        return
    
    print("\n🎙️ توليد الصوت للفيديو الطويل...")
    await generate_audio(ai['video_script'], video_audio)
    
    print("\n🎙️ توليد الصوت للشورتس...")
    await generate_audio(ai['shorts_script'], shorts_audio)
    
    print("\n🎬 إنتاج الفيديو الطويل...")
    video_success = create_zooming_video(
        img_file,
        video_audio,
        video_file,
        VIDEO_WIDTH,
        VIDEO_HEIGHT,
        is_shorts=False
    )
    
    print("\n🎬 إنتاج الشورتس...")
    shorts_success = create_zooming_video(
        img_file,
        shorts_audio,
        shorts_file,
        SHORTS_WIDTH,
        SHORTS_HEIGHT,
        is_shorts=True
    )
    
    if video_success:
        print("\n📤 رفع الفيديو الطويل...")
        yt_ok = upload_to_youtube(
            video_file,
            ai['video_title'],
            ai['video_description'],
            ai['hashtags'],
            is_shorts=False
        )
        if not yt_ok:
            save_failed_link(article['url'], article['source_name'], "فشل رفع الفيديو الطويل لليوتيوب")
        fb_ok = upload_to_facebook(video_file, ai['facebook_post'], ai['hashtags'])
        if not fb_ok:
            save_failed_link(article['url'], article['source_name'], "فشل رفع الفيديو لفيسبوك")
    
    if shorts_success:
        print("\n📤 رفع الشورتس...")
        shorts_description = ai['shorts_script']
        shorts_ok = upload_to_youtube(
            shorts_file,
            ai['shorts_title'],
            shorts_description,
            ai['hashtags'],
            is_shorts=True
        )
        if not shorts_ok:
            save_failed_link(article['url'], article['source_name'], "فشل رفع الشورتس لليوتيوب")
    
    print("\n💾 حفظ الرابط في الهيستوري...")
    save_history(article['url'], article['source_name'])
    
    print("\n🧹 تنظيف الملفات المؤقتة...")
    files_to_remove = [img_file, video_audio, shorts_audio, video_file, shorts_file]
    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print(f"   ✓ تم حذف: {f}")
    
    print("\n" + "=" * 60)
    print("✅ اكتمل التنفيذ بنجاح")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
