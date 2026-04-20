import asyncio
import os
import logging
from datetime import datetime, timedelta
import feedparser
import urllib.parse
from telegram import Bot
from telegram.constants import ParseMode

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

COMPANIES = {
    "한화에어로스페이스": ["한화에어로스페이스", "Hanwha Aerospace"],
    "한화시스템":       ["한화시스템", "Hanwha Systems"],
    "LIG넥스원":       ["LIG넥스원", "LIG Nex1"],
    "현대로템":         ["현대로템", "Hyundai Rotem"],
    "한국항공우주":     ["한국항공우주", "Korea Aerospace Industries", "KAI"],
}

DEFENSE_RSS_FEEDS = [
    ("더구루",        "https://www.theguru.co.kr/rss/allArticle.xml"),
    ("디펜스타임즈",   "https://www.defensetimes.co.kr/rss/allArticle.xml"),
    ("브레이킹디펜스", "https://breakingdefense.com/feed/"),
    ("디펜스뉴스",     "https://www.defensenews.com/arc/outboundfeeds/rss/"),
]

INCLUDE_KEYWORDS = [
    "수주", "계약", "납품", "수출", "개발", "양산", "협약", "MOU", "협력",
    "입찰", "선정", "공급", "생산", "기술", "무기", "미사일",
    "전투기", "헬기", "드론", "위성", "방산", "방위", "해군", "육군", "공군",
    "자주포", "천궁", "K2", "K9", "레드백", "수리온", "함정", "잠수함",
    "order", "contract", "export", "develop", "supply", "defense", "missile",
    "aircraft", "helicopter", "drone", "satellite", "military", "weapon",
    "howitzer", "tank", "deal", "award", "delivery", "agreement"
]

EXCLUDE_KEYWORDS = [
    "신용등급", "주가", "투자의견", "목표주가", "매수", "매도",
    "주식", "펀드", "ETF", "배당", "영업이익", "순이익", "매출액",
    "stock", "share price", "rating", "analyst", "dividend",
    "earnings", "revenue", "profit", "loss", "upgrade", "downgrade"
]

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def is_relevant(title: str) -> bool:
    title_lower = title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    for kw in INCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


def clean_title(title: str) -> str:
    """구글 뉴스 제목에서 '- 매체명' 제거"""
    if " - " in title:
        title = title.rsplit(" - ", 1)[0]
    return title.strip()


def fetch_google_news(query: str, lang: str = "ko", country: str = "KR") -> list[dict]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={lang}&gl={country}&ceid={country}:{lang}"
    feed = feedparser.parse(url)
    now_utc = datetime.utcnow()
    cutoff = now_utc - timedelta(hours=24)

    articles = []
    for entry in feed.entries:
        try:
            pub = datetime(*entry.published_parsed[:6])
        except Exception:
            continue
        if pub < cutoff:
            continue
        articles.append({
            "title": clean_title(entry.title),
            "link": entry.link,
            "published": pub + timedelta(hours=9),
            "lang": "🇰🇷" if lang == "ko" else "🇺🇸",
        })
    return articles


def fetch_defense_rss(company_queries: list[str]) -> list[dict]:
    now_utc = datetime.utcnow()
    cutoff = now_utc - timedelta(hours=24)
    articles = []

    for media_name, rss_url in DEFENSE_RSS_FEEDS:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        pub = datetime(*entry.updated_parsed[:6])
                    else:
                        continue
                except Exception:
                    continue
                if pub < cutoff:
                    continue
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not any(q.lower() in title.lower() for q in company_queries):
                    continue
                articles.append({
                    "title": clean_title(title),
                    "link": link,
                    "published": pub + timedelta(hours=9),
                    "lang": f"⭐ {media_name}",
                })
        except Exception as e:
            logger.warning(f"{media_name} RSS 오류: {e}")
    return articles


def fetch_company_news(queries: list[str]) -> list[dict]:
    seen = set()
    all_articles = []

    for a in fetch_defense_rss(queries):
        if a["title"] not in seen:
            seen.add(a["title"])
            all_articles.append(a)

    for a in fetch_google_news(queries[0], lang="ko", country="KR"):
        if a["title"] not in seen and is_relevant(a["title"]):
            seen.add(a["title"])
            all_articles.append(a)

    for q in queries[1:]:
        for a in fetch_google_news(q, lang="en", country="US"):
            if a["title"] not in seen and is_relevant(a["title"]):
                seen.add(a["title"])
                all_articles.append(a)

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    return all_articles


def format_company_message(company: str, articles: list[dict], index: int, total_companies: int) -> str:
    """기업 하나당 메시지 하나 생성"""
    now_kst = datetime.utcnow() + timedelta(hours=9)

    lines = []
    lines.append(f"🏢 *{company}* ({len(articles)}건)")
    lines.append(f"🕐 {now_kst.strftime('%Y-%m-%d %H:%M')} KST · {index}/{total_companies}")
    lines.append(f"⭐방산전문  🇰🇷국내  🇺🇸해외")
    lines.append("─" * 26)

    if not articles:
        lines.append("관련 핵심 뉴스 없음")
    else:
        for a in articles[:15]:
            time_str = a["published"].strftime("%m/%d %H:%M")
            flag = a.get("lang", "")
            title = a["title"][:55] + ("..." if len(a["title"]) > 55 else "")
            # 마크다운 링크 형식으로 깔끔하게
            lines.append(f"{flag} `{time_str}`\n[{title}]({a['link']})\n")

    return "\n".join(lines)


async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        raise ValueError("TELEGRAM_TOKEN 또는 CHAT_ID 환경변수가 없습니다.")

    logger.info("뉴스 수집 시작...")
    articles_by_company = {}
    for company_key, queries in COMPANIES.items():
        articles = fetch_company_news(queries)
        articles_by_company[company_key] = articles
        logger.info(f"{company_key}: {len(articles)}건")

    bot = Bot(token=TELEGRAM_TOKEN)
    total = len(COMPANIES)

    for i, (company, articles) in enumerate(articles_by_company.items(), 1):
        msg = format_company_message(company, articles, i, total)
        await bot.send_message(
            chat_id=CHAT_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        await asyncio.sleep(1)

    logger.info("전송 완료!")


if __name__ == "__main__":
    asyncio.run(main())
