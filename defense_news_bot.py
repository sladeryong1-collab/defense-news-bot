import asyncio
import os
import logging
from datetime import datetime, timedelta
import feedparser
import urllib.parse
from telegram import Bot
from telegram.constants import ParseMode

# ─── 설정 ───────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

COMPANIES = {
    "한화에어로스페이스": ["한화에어로스페이스", "Hanwha Aerospace"],
    "한화시스템":       ["한화시스템", "Hanwha Systems"],
    "LIG넥스원":       ["LIG넥스원", "LIG Nex1"],
    "현대로템":         ["현대로템", "Hyundai Rotem"],
    "한국항공우주":     ["한국항공우주", "Korea Aerospace Industries", "KAI"],
}

# 포함 키워드 (하나라도 있으면 통과)
INCLUDE_KEYWORDS = [
    "수주", "계약", "납품", "수출", "개발", "양산", "협약", "MOU", "협력",
    "입찰", "선정", "공급", "생산", "제조", "기술", "무기", "미사일",
    "전투기", "헬기", "드론", "위성", "방산", "방위", "군", "해군", "육군", "공군",
    "order", "contract", "export", "develop", "supply", "defense", "missile",
    "aircraft", "helicopter", "drone", "satellite", "military", "weapon",
    "delivery", "production", "agreement", "deal", "award"
]

# 제외 키워드 (하나라도 있으면 제외)
EXCLUDE_KEYWORDS = [
    "신용등급", "주가", "투자의견", "목표주가", "매수", "매도", "상향", "하향",
    "주식", "펀드", "ETF", "배당", "실적발표", "영업이익", "순이익", "매출액",
    "stock", "share price", "rating", "analyst", "dividend", "earnings",
    "revenue", "profit", "loss", "upgrade", "downgrade", "buy", "sell"
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─── 필터 함수 ────────────────────────────────────────────
def is_relevant(title: str) -> bool:
    title_lower = title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    for kw in INCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


# ─── 구글 뉴스 크롤링 ────────────────────────────────────
def fetch_news(query: str, lang: str = "ko", country: str = "KR") -> list[dict]:
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
            "title": entry.title,
            "link": entry.link,
            "published": pub + timedelta(hours=9),
        })
    return articles


def fetch_company_news(company_key: str, queries: list[str]) -> list[dict]:
    seen = set()
    all_articles = []

    # 한국어 뉴스
    for q in queries[:1]:
        for a in fetch_news(q, lang="ko", country="KR"):
            if a["title"] not in seen and is_relevant(a["title"]):
                seen.add(a["title"])
                a["lang"] = "🇰🇷"
                all_articles.append(a)

    # 영어 뉴스
    for q in queries[1:]:
        for a in fetch_news(q, lang="en", country="US"):
            if a["title"] not in seen and is_relevant(a["title"]):
                seen.add(a["title"])
                a["lang"] = "🇺🇸"
                all_articles.append(a)

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    return all_articles


# ─── 메시지 포맷팅 ────────────────────────────────────────
def format_message(articles_by_company: dict) -> list[str]:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    messages = []

    header = (
        f"📰 *방산주 핵심 뉴스 브리핑*\n"
        f"🕐 {now_kst.strftime('%Y-%m-%d %H:%M')} KST 기준 최근 24시간\n"
        f"{'─' * 28}"
    )

    body_lines = []
    total = 0
    for company, articles in articles_by_company.items():
        total += len(articles)
        body_lines.append(f"\n🏢 *{company}* ({len(articles)}건)")
        if not articles:
            body_lines.append("  • 관련 핵심 뉴스 없음")
        else:
            for a in articles[:15]:
                time_str = a["published"].strftime("%m/%d %H:%M")
                flag = a.get("lang", "")
                title = a["title"][:50] + ("..." if len(a["title"]) > 50 else "")
                body_lines.append(f"  {flag} `{time_str}` [{title}]({a['link']})")

    footer = f"\n{'─' * 28}\n📊 총 *{total}건* 핵심 뉴스"

    full = header + "\n" + "\n".join(body_lines) + footer
    if len(full) <= 4000:
        return [full]

    messages.append(header)
    chunk = ""
    for line in body_lines:
        if len(chunk) + len(line) > 3800:
            messages.append(chunk)
            chunk = line
        else:
            chunk += "\n" + line
    if chunk:
        messages.append(chunk)
    messages.append(footer)
    return messages


# ─── 메인 ─────────────────────────────────────────────────
async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        raise ValueError("TELEGRAM_TOKEN 또는 CHAT_ID 환경변수가 없습니다.")

    logger.info("뉴스 수집 시작...")
    articles_by_company = {}
    for company_key, queries in COMPANIES.items():
        articles = fetch_company_news(company_key, queries)
        articles_by_company[company_key] = articles
        logger.info(f"{company_key}: {len(articles)}건 (필터 후)")

    messages = format_message(articles_by_company)

    bot = Bot(token=TELEGRAM_TOKEN)
    for msg in messages:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.5)

    logger.info("전송 완료!")


if __name__ == "__main__":
    asyncio.run(main())
