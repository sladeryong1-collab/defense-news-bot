import asyncio
import logging
from datetime import datetime, timedelta
import feedparser
import urllib.parse
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ─── 설정 ───────────────────────────────────────────────
TELEGRAM_TOKEN = "8627580348:AAFsW0pEPXDK3m5qZhNp2nTw5MBYzojSeso"

COMPANIES = {
    "한화에어로스페이스": "한화에어로스페이스",
    "한화시스템": "한화시스템",
    "LIG넥스원": "LIG넥스원",
    "현대로템": "현대로템",
    "한국항공우주": "한국항공우주",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─── 구글 뉴스 크롤링 ────────────────────────────────────
def fetch_news(company_name: str) -> list[dict]:
    """구글 뉴스 RSS에서 지난 24시간 뉴스를 가져옵니다."""
    query = urllib.parse.quote(company_name)
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

    feed = feedparser.parse(url)
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=24)

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
            "published": pub + timedelta(hours=9),  # KST 변환
        })

    # 최신순 정렬
    articles.sort(key=lambda x: x["published"], reverse=True)
    return articles


# ─── 메시지 포맷팅 ────────────────────────────────────────
def format_news_message(articles_by_company: dict) -> str:
    """뉴스를 텔레그램 메시지 형식으로 포맷합니다."""
    now_kst = datetime.utcnow() + timedelta(hours=9)
    lines = []
    lines.append(f"📰 *방산주 뉴스 브리핑*")
    lines.append(f"🕐 {now_kst.strftime('%Y-%m-%d %H:%M')} KST 기준 최근 24시간")
    lines.append("─" * 30)

    total = 0
    for company, articles in articles_by_company.items():
        count = len(articles)
        total += count
        lines.append(f"\n🏢 *{company}* ({count}건)")

        if not articles:
            lines.append("  • 관련 뉴스 없음")
        else:
            for a in articles[:5]:  # 회사당 최대 5개
                time_str = a["published"].strftime("%m/%d %H:%M")
                title = a["title"][:50] + ("..." if len(a["title"]) > 50 else "")
                # 텔레그램 마크다운 특수문자 이스케이프
                title = title.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
                lines.append(f"  • `{time_str}` [{title}]({a['link']})")

    lines.append("\n─" * 30)
    lines.append(f"📊 총 *{total}건* 뉴스")
    return "\n".join(lines)


# ─── 커맨드 핸들러 ────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *방산주 뉴스 봇*에 오신 걸 환영합니다\\!\n\n"
        "📋 *사용 가능한 명령어*\n"
        "/news \\- 지난 24시간 방산주 뉴스 조회\n"
        "/help \\- 도움말\n\n"
        "5개 기업의 구글 뉴스를 실시간으로 가져옵니다\\.\n"
        "한화에어로스페이스, 한화시스템, LIG넥스원, 현대로템, 한국항공우주"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *도움말*\n\n"
        "/news \\- 5개 방산 기업의 지난 24시간 뉴스를 가져옵니다\\.\n"
        "각 기업별 최대 5개 기사를 표시합니다\\.\n\n"
        "⏱ 뉴스 수집에 약 10\\~15초가 소요됩니다\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """뉴스 조회 명령어 처리"""
    loading_msg = await update.message.reply_text("⏳ 뉴스를 수집 중입니다... (10~15초 소요)")

    try:
        articles_by_company = {}
        for company_key, company_query in COMPANIES.items():
            articles_by_company[company_key] = fetch_news(company_query)

        message = format_news_message(articles_by_company)

        await loading_msg.delete()
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"뉴스 수집 오류: {e}")
        await loading_msg.edit_text(f"❌ 오류가 발생했습니다: {str(e)}")


# ─── 메인 ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("news", news_command))

    logger.info("봇 시작됨!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
