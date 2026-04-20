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

COMPANIES = [
    "한화에어로스페이스",
    "한화시스템",
    "LIG넥스원",
    "현대로템",
    "한국항공우주",
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def fetch_news(company: str) -> list[dict]:
    query = urllib.parse.quote(company)
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
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
    articles.sort(key=lambda x: x["published"], reverse=True)
    return articles


def format_message(articles_by_company: dict) -> str:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    lines = []
    lines.append(f"📰 *방산주 뉴스 브리핑*")
    lines.append(f"🕐 {now_kst.strftime('%Y-%m-%d %H:%M')} KST 기준 최근 24시간")
    lines.append("─" * 28)
    total = 0
    for company, articles in articles_by_company.items():
        total += len(articles)
        lines.append(f"\n🏢 *{company}* ({len(articles)}건)")
        if not articles:
            lines.append("  • 관련 뉴스 없음")
        else:
            for a in articles[:5]:
                time_str = a["published"].strftime("%m/%d %H:%M")
                title = a["title"][:45] + ("..." if len(a["title"]) > 45 else "")
                lines.append(f"  • `{time_str}` [{title}]({a['link']})")
    lines.append(f"\n─" * 28)
    lines.append(f"📊 총 *{total}건*")
    return "\n".join(lines)


async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        raise ValueError("TELEGRAM_TOKEN 또는 CHAT_ID 환경변수가 없습니다.")
    logger.info("뉴스 수집 시작...")
    articles_by_company = {}
    for company in COMPANIES:
        articles_by_company[company] = fetch_news(company)
        logger.info(f"{company}: {len(articles_by_company[company])}건")
    message = format_message(articles_by_company)
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=CHAT_ID,
        text=message,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )
    logger.info("전송 완료!")


if __name__ == "__main__":
    asyncio.run(main())
