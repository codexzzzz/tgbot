import os
import asyncio
import logging
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from ai_chat import ask_deepseek
from database import (
    init_db,
    upsert_user,
    reset_daily_photos_if_needed,
    increment_photo_count,
    get_photo_count_today,
    save_photo,
    get_last_photos,
    get_top_users,
    ban_user,
    unban_user,
    grant_premium,
    revoke_premium,
    is_user_banned,
    is_user_premium,
    get_all_forums,
    add_forum,
    delete_forum,
    can_submit_today,
    mark_submitted_today,
    save_feedback,
    get_feedback,
    get_user_last_feedback,
    get_user_photos,
    get_user_photo_count,
    delete_user_photo,
)
from imgbb import upload_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DEVELOPER_ID = int(os.environ.get("DEVELOPER_USER_ID", "0"))
DAILY_LIMIT = 50
PREMIUM_PRICE_STARS = 10

FORUM_WAIT_TITLE = 1
FORUM_WAIT_URL = 2
REVIEW_WAIT_TEXT = 3
SUGGESTION_WAIT_TEXT = 4
AI_CONSULT_WAIT = 5


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Загрузить фото", callback_data="menu_upload"),
            InlineKeyboardButton("🗂 Форумы", callback_data="menu_forums"),
        ],
        [
            InlineKeyboardButton("⭐ Premium", callback_data="menu_premium"),
            InlineKeyboardButton("📊 Мой статус", callback_data="menu_status"),
        ],
        [
            InlineKeyboardButton("🤖 ИИ Консультация", callback_data="menu_ai"),
        ],
        [
            InlineKeyboardButton("💬 Отзывы и предложения", callback_data="menu_feedback"),
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
        ],
    ])


async def send_main_menu(target, user_first_name: str, edit: bool = False):
    text = (
        f"👋 Привет, <b>{user_first_name}</b>!\n\n\n"
        "📁 <b>Хостинг изображений</b>\n\n\n"
        "Отправь мне фото — я мгновенно загружу его\n"
        "и дам постоянную ссылку.\n\n"
        "📌 <b>Бесплатно:</b> 50 фото/сутки · 2 недели хранения\n"
        "⭐ <b>Premium:</b> безлимит · навсегда · всего <b>10 звёзд</b>"
    )
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)
    await send_main_menu(update.message, user.first_name)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data == "menu_upload":
        await query.message.reply_text(
            "📸 <b>Загрузка фото</b>\n\n"
            "Просто отправьте мне фото прямо в чат — я сразу же\n"
            "загружу его и пришлю ссылку!",
            parse_mode="HTML",
        )

    elif data == "menu_forums":
        await show_forums(query.message, edit=False)

    elif data == "menu_premium":
        await show_premium(query.message, user.id, edit=False)

    elif data == "menu_status":
        await show_status(query.message, user)

    elif data == "menu_help":
        await show_help(query.message, edit=False)

    elif data == "menu_feedback":
        await show_feedback_menu(query.message, edit=False)

    elif data == "menu_back":
        await upsert_user(user.id, user.username, user.first_name)
        await send_main_menu(query.message, user.first_name, edit=True)


async def show_help(target, edit: bool = False):
    text = (
        "❓ <b>Как пользоваться ботом</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📸 <b>Загрузка фото</b>\n"
        "Просто отправьте фото в чат — получите ссылку.\n\n"
        "🗂 <b>Форумы</b>\n"
        "Каталог форумов популярных игровых проектов.\n"
        "Любой может добавить свой форум.\n\n"
        "💬 <b>Отзывы и предложения</b>\n"
        "Оставьте отзыв или идею для развития бота.\n"
        "Лимит: 1 отзыв и 1 предложение в сутки.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📦 <b>Бесплатный план</b>\n"
        "• До <b>50 фото</b> в сутки\n"
        "• Срок хранения: <b>2 недели</b>\n\n"
        "⭐ <b>Premium — всего лишь 10 звёзд</b>\n"
        "• <b>Безлимит</b> фото в сутки\n"
        "• Хранение <b>навсегда</b>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Купить Premium", callback_data="menu_premium")],
        [InlineKeyboardButton("◀ Назад", callback_data="menu_back")],
    ])
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_help(update.message)


async def show_status(target, user):
    await upsert_user(user.id, user.username, user.first_name)
    await reset_daily_photos_if_needed(user.id)
    premium = await is_user_premium(user.id)
    count = await get_photo_count_today(user.id)

    if premium:
        plan_line = "⭐ <b>Premium</b>"
        bar = "🟨🟨🟨🟨🟨🟨🟨🟨🟨🟨 ∞"
        limit_lines = "• Лимит: <b>безлимит</b>\n• Хранение: <b>навсегда</b>"
    else:
        remaining = max(0, DAILY_LIMIT - count)
        filled = int((count / DAILY_LIMIT) * 10)
        bar = "🟩" * filled + "⬜" * (10 - filled) + f" {count}/{DAILY_LIMIT}"
        plan_line = "📦 <b>Бесплатный</b>"
        limit_lines = (
            f"• Загружено сегодня: <b>{count}</b> из <b>{DAILY_LIMIT}</b>\n"
            f"• Осталось: <b>{remaining}</b>\n"
            f"• Хранение: <b>2 недели</b>"
        )

    text = (
        f"📊 <b>Ваш профиль</b>\n\n"
        f"👤 {user.first_name}"
        + (f" (@{user.username})" if user.username else "") + "\n"
        f"💎 Тариф: {plan_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Активность сегодня</b>\n"
        f"{bar}\n"
        f"{limit_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    kb_rows = []
    if not premium:
        kb_rows.append([InlineKeyboardButton("⭐ Получить Premium за 10 звёзд", callback_data="menu_premium")])
    kb_rows.append([InlineKeyboardButton("📷 Мои фотографии", callback_data="myphotos_0")])
    kb_rows.append([InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")])

    await target.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_status(update.message, update.effective_user)


async def show_premium(target, user_id: int, edit: bool = False):
    premium = await is_user_premium(user_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="menu_back")]])

    if premium:
        text = (
            "⭐ <b>У вас активен Premium!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Безлимитная загрузка фото\n"
            "✅ Хранение навсегда\n"
            "✅ Приоритетная обработка\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Спасибо за поддержку! 🙏"
        )
        if edit:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await target.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return

    text = (
        "⭐ <b>Premium-подписка</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔓 <b>Безлимит</b> фото в сутки\n"
        "🔒 Хранение <b>навсегда</b>\n"
        "⚡ Приоритетная обработка\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💰 Цена: <b>всего лишь 10 звёзд</b>\n\n"
        "Нажмите кнопку ниже для мгновенной оплаты:"
    )
    buy_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Оплатить 10 звёзд", callback_data="buy_premium")],
        [InlineKeyboardButton("◀ Назад", callback_data="menu_back")],
    ])
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=buy_kb)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=buy_kb)


async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)
    await show_premium(update.message, user.id)


async def buy_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="⭐ Premium-подписка",
        description="Безлимитные фото навсегда. Хранение без срока истечения. Всего лишь 10 звёзд!",
        payload="premium_purchase",
        currency="XTR",
        prices=[LabeledPrice(label="Premium (навсегда)", amount=PREMIUM_PRICE_STARS)],
    )


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload == "premium_purchase":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неизвестный платёж")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payload = update.message.successful_payment.invoice_payload
    if payload == "premium_purchase":
        import aiosqlite
        from database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user.id,))
            await db.commit()

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")]])
        await update.message.reply_text(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⭐ <b>Premium активирован!</b>\n\n"
            "✅ Безлимитная загрузка фото\n"
            "✅ Хранение навсегда\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Спасибо за поддержку! 🙏",
            parse_mode="HTML",
            reply_markup=kb,
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)

    if await is_user_banned(user.id):
        await update.message.reply_text("🚫 <b>Вы заблокированы</b> и не можете использовать бота.", parse_mode="HTML")
        return

    await reset_daily_photos_if_needed(user.id)
    premium = await is_user_premium(user.id)
    count = await get_photo_count_today(user.id)

    if not premium and count >= DAILY_LIMIT:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Купить Premium за 10 звёзд", callback_data="buy_premium")]])
        await update.message.reply_text(
            "❌ <b>Дневной лимит исчерпан</b>\n\n"
            f"Вы загрузили <b>{DAILY_LIMIT}</b> фото за сегодня.\n"
            "Лимит сбросится в полночь.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⭐ Снимите ограничения навсегда с <b>Premium за 10 звёзд</b>:",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    msg = await update.message.reply_text("⏳ <b>Загружаю...</b>", parse_mode="HTML")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        buf = BytesIO()
        await file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, upload_image, image_bytes, premium)

        url = result["url"]
        delete_url = result["delete_url"]
        expires_at = result["expires_at"]

        await save_photo(user.id, user.username, url, delete_url, expires_at)
        await increment_photo_count(user.id)

        if premium:
            storage_badge = "🔒 навсегда"
            extra = ""
        else:
            remaining = DAILY_LIMIT - count - 1
            storage_badge = "⏳ 2 недели"
            filled = int(((count + 1) / DAILY_LIMIT) * 10)
            bar = "🟩" * filled + "⬜" * (10 - filled)
            extra = (
                f"\n\n{bar} <b>{count + 1}/{DAILY_LIMIT}</b>\n"
                f"💡 <b>Premium за 10 звёзд</b> — безлимит и вечное хранение"
            )

        kb_rows = [[InlineKeyboardButton("🔗 Открыть изображение", url=url)]]
        if not premium:
            kb_rows.append([InlineKeyboardButton("⭐ Получить Premium", callback_data="buy_premium")])

        text = (
            f"✅ <b>Загружено!</b>\n\n"
            f"🔗 <code>{url}</code>\n\n"
            f"💾 Хранение: {storage_badge}"
            f"{extra}"
        )

        await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))

    except Exception as e:
        logger.error(f"Upload error: {e}")
        await msg.edit_text("❌ <b>Ошибка при загрузке.</b> Попробуйте ещё раз.", parse_mode="HTML")


def build_forums_keyboard(forums: list) -> InlineKeyboardMarkup:
    keyboard = []
    preset = [f for f in forums if f["is_preset"]]
    user_added = [f for f in forums if not f["is_preset"]]

    for forum in preset:
        keyboard.append([InlineKeyboardButton(f"🎮 {forum['title']}", url=forum["url"])])

    if user_added:
        keyboard.append([InlineKeyboardButton("─── От сообщества ───", callback_data="forums_noop")])
        for forum in user_added:
            keyboard.append([InlineKeyboardButton(f"📌 {forum['title']}", url=forum["url"])])

    keyboard.append([InlineKeyboardButton("➕ Добавить форум", callback_data="forum_add")])
    keyboard.append([InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(keyboard)


async def show_forums(target, edit: bool = False):
    forums = await get_all_forums()
    total = len(forums)
    preset_count = sum(1 for f in forums if f["is_preset"])
    user_count = total - preset_count

    text = (
        "🗂 <b>Форумы игровых проектов</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Всего в базе: <b>{total}</b>\n"
        f"🎮 Официальных: <b>{preset_count}</b>\n"
        f"👥 От сообщества: <b>{user_count}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Нажмите на проект, чтобы открыть форум."
    )
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=build_forums_keyboard(forums))
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=build_forums_keyboard(forums))


async def forums_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)
    await show_forums(update.message)


async def forums_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


async def forum_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "➕ <b>Добавление форума</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>Шаг 1 из 2</b>\n\n"
        "Введите <b>название проекта</b>:\n"
        "<i>Пример: Black Russia</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    return FORUM_WAIT_TITLE


async def forum_got_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if len(title) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Попробуйте ещё раз:")
        return FORUM_WAIT_TITLE
    if len(title) > 100:
        await update.message.reply_text("❌ Название слишком длинное (макс. 100 символов). Попробуйте ещё раз:")
        return FORUM_WAIT_TITLE

    context.user_data["forum_title"] = title
    await update.message.reply_text(
        f"✅ Название: <b>{title}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 <b>Шаг 2 из 2</b>\n\n"
        "Введите <b>ссылку на форум</b>:\n"
        "<i>Пример: https://forum.blackrussia.online</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    return FORUM_WAIT_URL


async def forum_got_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ Ссылка должна начинаться с <code>http://</code> или <code>https://</code>\n"
            "Попробуйте ещё раз:",
            parse_mode="HTML",
        )
        return FORUM_WAIT_URL

    if len(url) > 500:
        await update.message.reply_text("❌ Ссылка слишком длинная. Попробуйте ещё раз:")
        return FORUM_WAIT_URL

    title = context.user_data.get("forum_title", "Без названия")
    await add_forum(title, url, user.id, user.username)
    context.user_data.clear()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂 Открыть форумы", callback_data="menu_forums")],
        [InlineKeyboardButton("◀ Меню", callback_data="menu_back")],
    ])
    await update.message.reply_text(
        f"🎉 <b>Форум добавлен!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{title}</b>\n"
        f"🔗 {url}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Теперь он виден всем пользователям в разделе форумов.",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def forum_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")]])
    await update.message.reply_text("❌ Действие отменено.", reply_markup=kb)
    return ConversationHandler.END


async def show_feedback_menu(target, edit: bool = False):
    text = (
        "💬 <b>Отзывы и предложения</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⭐ <b>Отзыв</b> — поделитесь впечатлением о боте.\n"
        "💡 <b>Предложение</b> — расскажите, что улучшить.\n\n"
        "Лимит: <b>1 отзыв</b> и <b>1 предложение</b> в сутки.\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ Написать отзыв", callback_data="feedback_review"),
            InlineKeyboardButton("💡 Предложение", callback_data="feedback_suggestion"),
        ],
        [InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")],
    ])
    if edit:
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def feedback_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await upsert_user(user.id, user.username, user.first_name)

    can = await can_submit_today(user.id, "review")
    if not can:
        last = await get_user_last_feedback(user.id, "review")
        last_text = f"\n\n📄 Ваш последний отзыв:\n<i>«{last['text']}»</i>" if last else ""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ Вернуть отзыв", callback_data="show_last_review")],
            [InlineKeyboardButton("◀ Назад", callback_data="menu_feedback")],
        ])
        await query.message.reply_text(
            "⏳ <b>Кулдаун активен</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Вы уже оставили отзыв сегодня.\n"
            "Следующий отзыв можно оставить <b>завтра</b>."
            f"{last_text}\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return ConversationHandler.END

    await query.message.reply_text(
        "⭐ <b>Написать отзыв</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Расскажите о своём опыте использования бота.\n"
        "Что понравилось? Что нет?\n\n"
        "✍ Введите ваш отзыв:\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    return REVIEW_WAIT_TEXT


async def feedback_suggestion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await upsert_user(user.id, user.username, user.first_name)

    can = await can_submit_today(user.id, "suggestion")
    if not can:
        last = await get_user_last_feedback(user.id, "suggestion")
        last_text = f"\n\n📄 Ваше последнее предложение:\n<i>«{last['text']}»</i>" if last else ""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ Вернуть предложение", callback_data="show_last_suggestion")],
            [InlineKeyboardButton("◀ Назад", callback_data="menu_feedback")],
        ])
        await query.message.reply_text(
            "⏳ <b>Кулдаун активен</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Вы уже оставили предложение сегодня.\n"
            "Следующее предложение можно оставить <b>завтра</b>."
            f"{last_text}\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return ConversationHandler.END

    await query.message.reply_text(
        "💡 <b>Написать предложение</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Есть идея, как улучшить бота?\n"
        "Опишите её — мы обязательно рассмотрим!\n\n"
        "✍ Введите ваше предложение:\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    return SUGGESTION_WAIT_TEXT


async def show_last_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    last = await get_user_last_feedback(user.id, "review")
    if not last:
        await query.message.reply_text("❌ Отзыв не найден.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="menu_feedback")]])
    await query.message.reply_text(
        f"⭐ <b>Ваш последний отзыв</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>«{last['text']}»</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Отправлен: {last['created_at'][:10]}",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def show_last_suggestion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    last = await get_user_last_feedback(user.id, "suggestion")
    if not last:
        await query.message.reply_text("❌ Предложение не найдено.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="menu_feedback")]])
    await query.message.reply_text(
        f"💡 <b>Ваше последнее предложение</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>«{last['text']}»</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Отправлено: {last['created_at'][:10]}",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def review_got_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if len(text) < 5:
        await update.message.reply_text("❌ Отзыв слишком короткий. Напишите хотя бы пару слов:")
        return REVIEW_WAIT_TEXT
    if len(text) > 1000:
        await update.message.reply_text("❌ Отзыв слишком длинный (макс. 1000 символов). Сократите текст:")
        return REVIEW_WAIT_TEXT

    await save_feedback("review", user.id, user.username, user.first_name, text)
    await mark_submitted_today(user.id, "review")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Оставить предложение", callback_data="feedback_suggestion")],
        [InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")],
    ])
    await update.message.reply_text(
        "✅ <b>Отзыв принят, спасибо!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>«{text}»</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ваш отзыв будет рассмотрен разработчиком. 🙏",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def suggestion_got_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if len(text) < 5:
        await update.message.reply_text("❌ Предложение слишком короткое. Напишите хотя бы пару слов:")
        return SUGGESTION_WAIT_TEXT
    if len(text) > 1000:
        await update.message.reply_text("❌ Предложение слишком длинное (макс. 1000 символов). Сократите текст:")
        return SUGGESTION_WAIT_TEXT

    await save_feedback("suggestion", user.id, user.username, user.first_name, text)
    await mark_submitted_today(user.id, "suggestion")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Написать отзыв", callback_data="feedback_review")],
        [InlineKeyboardButton("◀ Главное меню", callback_data="menu_back")],
    ])
    await update.message.reply_text(
        "✅ <b>Предложение принято, спасибо!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>«{text}»</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ваша идея будет рассмотрена разработчиком. 💡",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def ai_consult_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✖ Отмена", callback_data="ai_cancel")]])
    await query.message.reply_text(
        "🤖 <b>ИИ Консультация</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Задай мне любой вопрос о проектах:\n"
        "🎮 Black Russia · Матрёшка РП · Amazing RP\n"
        "🎮 MTA Провинция · GTA 5 RP · Majestic RP\n"
        "🎮 Arizona RP · Grand Mobile · и других SAMP/RP\n\n"
        "💬 Просто напиши свой вопрос текстом:\n"
        "━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return AI_CONSULT_WAIT


async def ai_consult_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return AI_CONSULT_WAIT

    thinking_msg = await update.message.reply_text(
        "⏳ <b>Думаю над ответом...</b>",
        parse_mode="HTML",
    )

    try:
        answer = await ask_deepseek(user_text)
    except Exception as e:
        logging.error(f"DeepSeek error: {e}")
        answer = "❌ Произошла ошибка при обращении к ИИ. Попробуй ещё раз позже."

    await thinking_msg.delete()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Ещё вопрос", callback_data="ai_again")],
        [InlineKeyboardButton("◀ Главное меню", callback_data="ai_back")],
    ])
    await update.message.reply_text(
        f"🤖 <b>ИИ Консультация</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Вопрос:</b> {user_text}\n\n"
        f"<b>Ответ:</b>\n{answer}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def ai_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_main_menu(query.message, query.from_user.first_name)
    return ConversationHandler.END


async def ai_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✖ Отмена", callback_data="ai_cancel")]])
    await query.message.reply_text(
        "🤖 <b>ИИ Консультация</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Задай следующий вопрос:\n"
        "━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return AI_CONSULT_WAIT


async def ai_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_main_menu(query.message, query.from_user.first_name)
    return ConversationHandler.END


PHOTOS_PER_PAGE = 5


async def myphotos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    offset = int(query.data.split("_")[1])

    total = await get_user_photo_count(user.id)
    photos = await get_user_photos(user.id, limit=PHOTOS_PER_PAGE, offset=offset)

    if total == 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="menu_status")]])
        await query.message.reply_text(
            "📷 <b>Мои фотографии</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "У вас пока нет загруженных фото.\n"
            "Отправьте фото в чат — и оно появится здесь!\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    lines = []
    for p in photos:
        short_url = p["url"].replace("https://", "").replace("http://", "")
        if len(short_url) > 35:
            short_url = short_url[:33] + "…"
        date_str = p["uploaded_at"][:10]
        expire = f"до {p['expires_at'][:10]}" if p.get("expires_at") else "навсегда"
        lines.append(f"📎 <a href='{p['url']}'>{short_url}</a>\n📅 {date_str} · 💾 {expire}")

    text = (
        f"📷 <b>Мои фотографии</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Всего: <b>{total}</b> фото · Страница <b>{offset // PHOTOS_PER_PAGE + 1}</b>"
        f" из <b>{(total + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines)
    )

    kb_rows = []
    for p in photos:
        short = p["url"].replace("https://i.ibb.co/", "").replace("https://", "")
        short = short[:28] + "…" if len(short) > 30 else short
        kb_rows.append([
            InlineKeyboardButton(f"🔗 {short}", url=p["url"]),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"phdel_{p['id']}_{offset}"),
        ])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Назад", callback_data=f"myphotos_{offset - PHOTOS_PER_PAGE}"))
    if offset + PHOTOS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"myphotos_{offset + PHOTOS_PER_PAGE}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton("↩ К статусу", callback_data="menu_status")])

    await query.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb_rows),
        disable_web_page_preview=True,
    )


async def photo_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    photo_id = int(parts[1])
    offset = int(parts[2])

    delete_url = await delete_user_photo(photo_id, user.id)

    if delete_url is None:
        await query.answer("❌ Фото не найдено или уже удалено.", show_alert=True)
        return

    if delete_url:
        try:
            import requests as req
            req.get(delete_url, timeout=5)
        except Exception:
            pass

    total_after = await get_user_photo_count(user.id)
    new_offset = min(offset, max(0, total_after - PHOTOS_PER_PAGE))
    new_offset = (new_offset // PHOTOS_PER_PAGE) * PHOTOS_PER_PAGE

    await query.answer("🗑 Фото удалено!", show_alert=False)

    if total_after == 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ К статусу", callback_data="menu_status")]])
        await query.message.edit_text(
            "📷 <b>Мои фотографии</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Фото удалено.\n"
            "Больше фотографий нет.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    photos = await get_user_photos(user.id, limit=PHOTOS_PER_PAGE, offset=new_offset)
    lines = []
    for p in photos:
        short_url = p["url"].replace("https://", "").replace("http://", "")
        if len(short_url) > 35:
            short_url = short_url[:33] + "…"
        date_str = p["uploaded_at"][:10]
        expire = f"до {p['expires_at'][:10]}" if p.get("expires_at") else "навсегда"
        lines.append(f"📎 <a href='{p['url']}'>{short_url}</a>\n📅 {date_str} · 💾 {expire}")

    text = (
        f"📷 <b>Мои фотографии</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Всего: <b>{total_after}</b> фото · Страница <b>{new_offset // PHOTOS_PER_PAGE + 1}</b>"
        f" из <b>{(total_after + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines)
    )

    kb_rows = []
    for p in photos:
        short = p["url"].replace("https://i.ibb.co/", "").replace("https://", "")
        short = short[:28] + "…" if len(short) > 30 else short
        kb_rows.append([
            InlineKeyboardButton(f"🔗 {short}", url=p["url"]),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"phdel_{p['id']}_{new_offset}"),
        ])

    nav = []
    if new_offset > 0:
        nav.append(InlineKeyboardButton("◀ Назад", callback_data=f"myphotos_{new_offset - PHOTOS_PER_PAGE}"))
    if new_offset + PHOTOS_PER_PAGE < total_after:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"myphotos_{new_offset + PHOTOS_PER_PAGE}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton("↩ К статусу", callback_data="menu_status")])

    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb_rows),
        disable_web_page_preview=True,
    )


async def developer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != DEVELOPER_ID:
        await update.message.reply_text("❌ <b>Нет доступа.</b>", parse_mode="HTML")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Последние 100 фото", callback_data="dev_photos")],
        [InlineKeyboardButton("👥 Топ 100 пользователей", callback_data="dev_top_users")],
        [
            InlineKeyboardButton("⭐ Отзывы", callback_data="dev_reviews"),
            InlineKeyboardButton("💡 Предложения", callback_data="dev_suggestions"),
        ],
        [
            InlineKeyboardButton("🚫 Забанить", callback_data="dev_ban"),
            InlineKeyboardButton("✅ Разбанить", callback_data="dev_unban"),
        ],
        [InlineKeyboardButton("⭐ Выдать Premium", callback_data="dev_grant")],
    ])
    await update.message.reply_text(
        "🛠 <b>Панель разработчика</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def dev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if user.id != DEVELOPER_ID:
        await query.answer("Нет доступа", show_alert=True)
        return
    await query.answer()

    data = query.data

    if data == "dev_photos":
        photos = await get_last_photos(100)
        if not photos:
            await query.message.reply_text("📸 Фото ещё не загружалось.")
            return
        chunks = []
        current = "📸 <b>Последние 100 фото:</b>\n\n"
        for i, p in enumerate(photos, 1):
            line = f"{i}. @{p['username'] or 'unknown'} — <a href='{p['url']}'>{p['url']}</a> ({p['uploaded_at'][:10]})\n"
            if len(current) + len(line) > 4000:
                chunks.append(current)
                current = ""
            current += line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await query.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=True)

    elif data == "dev_top_users":
        users = await get_top_users(100)
        if not users:
            await query.message.reply_text("👥 Пользователей пока нет.")
            return
        chunks = []
        current = "👥 <b>Топ 100 пользователей:</b>\n\n"
        for i, u in enumerate(users, 1):
            prem = " ⭐" if u["is_premium"] else ""
            uname = f"@{u['username']}" if u["username"] else u["first_name"] or str(u["user_id"])
            line = f"{i}. {uname}{prem} — {u['photo_count']} фото\n"
            if len(current) + len(line) > 4000:
                chunks.append(current)
                current = ""
            current += line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await query.message.reply_text(chunk, parse_mode="HTML")

    elif data == "dev_reviews":
        items = await get_feedback("review", 50)
        if not items:
            await query.message.reply_text("⭐ Отзывов пока нет.")
            return
        chunks = []
        current = f"⭐ <b>Последние отзывы ({len(items)}):</b>\n\n"
        for i, f in enumerate(items, 1):
            uname = f"@{f['username']}" if f["username"] else f["first_name"] or str(f["user_id"])
            line = (
                f"<b>{i}. {uname}</b> · {f['created_at'][:10]}\n"
                f"<i>«{f['text']}»</i>\n\n"
            )
            if len(current) + len(line) > 4000:
                chunks.append(current)
                current = ""
            current += line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await query.message.reply_text(chunk, parse_mode="HTML")

    elif data == "dev_suggestions":
        items = await get_feedback("suggestion", 50)
        if not items:
            await query.message.reply_text("💡 Предложений пока нет.")
            return
        chunks = []
        current = f"💡 <b>Последние предложения ({len(items)}):</b>\n\n"
        for i, f in enumerate(items, 1):
            uname = f"@{f['username']}" if f["username"] else f["first_name"] or str(f["user_id"])
            line = (
                f"<b>{i}. {uname}</b> · {f['created_at'][:10]}\n"
                f"<i>«{f['text']}»</i>\n\n"
            )
            if len(current) + len(line) > 4000:
                chunks.append(current)
                current = ""
            current += line
        if current:
            chunks.append(current)
        for chunk in chunks:
            await query.message.reply_text(chunk, parse_mode="HTML")

    elif data == "dev_ban":
        await query.message.reply_text(
            "🚫 <b>Бан пользователя</b>\n\nВведите команду:\n<code>/ban @username</code>",
            parse_mode="HTML",
        )

    elif data == "dev_unban":
        await query.message.reply_text(
            "✅ <b>Разбан пользователя</b>\n\nВведите команду:\n<code>/unban @username</code>",
            parse_mode="HTML",
        )

    elif data == "dev_grant":
        await query.message.reply_text(
            "⭐ <b>Выдача Premium</b>\n\nВведите команду:\n<code>/givepremium @username</code>",
            parse_mode="HTML",
        )


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEVELOPER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /ban @username")
        return
    username = context.args[0].lstrip("@")
    ok = await ban_user(username)
    if ok:
        await update.message.reply_text(f"✅ Пользователь @{username} заблокирован.")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEVELOPER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /unban @username")
        return
    username = context.args[0].lstrip("@")
    ok = await unban_user(username)
    if ok:
        await update.message.reply_text(f"✅ Пользователь @{username} разблокирован.")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")


async def givepremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEVELOPER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /givepremium @username")
        return
    username = context.args[0].lstrip("@")
    ok = await grant_premium(username)
    if ok:
        await update.message.reply_text(f"⭐ Пользователю @{username} выдан Premium.")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")


async def revokepremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEVELOPER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /revokepremium @username")
        return
    username = context.args[0].lstrip("@")
    ok = await revoke_premium(username)
    if ok:
        await update.message.reply_text(f"✅ Premium у @{username} отозван.")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")


async def post_init(application):
    await init_db()
    logger.info("Database initialized")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    add_forum_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(forum_add_callback, pattern="^forum_add$")],
        states={
            FORUM_WAIT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, forum_got_title)],
            FORUM_WAIT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, forum_got_url)],
        },
        fallbacks=[CommandHandler("cancel", forum_cancel)],
        allow_reentry=True,
    )

    feedback_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(feedback_review_callback, pattern="^feedback_review$"),
            CallbackQueryHandler(feedback_suggestion_callback, pattern="^feedback_suggestion$"),
        ],
        states={
            REVIEW_WAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, review_got_text)],
            SUGGESTION_WAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, suggestion_got_text)],
        },
        fallbacks=[CommandHandler("cancel", forum_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("premium", premium_cmd))
    app.add_handler(CommandHandler("forums", forums_cmd))
    app.add_handler(CommandHandler("developer", developer_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("givepremium", givepremium_cmd))
    app.add_handler(CommandHandler("revokepremium", revokepremium_cmd))

    ai_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ai_consult_start, pattern="^menu_ai$"),
            CallbackQueryHandler(ai_again_callback, pattern="^ai_again$"),
        ],
        states={
            AI_CONSULT_WAIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ai_consult_answer),
                CallbackQueryHandler(ai_cancel_callback, pattern="^ai_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", ai_cancel_callback),
            CallbackQueryHandler(ai_back_callback, pattern="^ai_back$"),
            CallbackQueryHandler(ai_cancel_callback, pattern="^ai_cancel$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(add_forum_conv)
    app.add_handler(feedback_conv)
    app.add_handler(ai_conv)

    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(buy_premium_callback, pattern="^buy_premium$"))
    app.add_handler(CallbackQueryHandler(dev_callback, pattern="^dev_"))
    app.add_handler(CallbackQueryHandler(forums_noop_callback, pattern="^forums_noop$"))
    app.add_handler(CallbackQueryHandler(show_last_review_callback, pattern="^show_last_review$"))
    app.add_handler(CallbackQueryHandler(show_last_suggestion_callback, pattern="^show_last_suggestion$"))
    app.add_handler(CallbackQueryHandler(myphotos_callback, pattern=r"^myphotos_\d+$"))
    app.add_handler(CallbackQueryHandler(photo_delete_callback, pattern=r"^phdel_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(ai_back_callback, pattern="^ai_back$"))
    app.add_handler(CallbackQueryHandler(ai_again_callback, pattern="^ai_again$"))
    app.add_handler(CallbackQueryHandler(ai_cancel_callback, pattern="^ai_cancel$"))

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
