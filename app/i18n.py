# app/i18n.py
from __future__ import annotations

from typing import Dict


def normalize_lang(code: str | None) -> str:
    """
    מנרמל קוד שפה (כמו he-IL, ru-RU) לערכים קצרים:
    en / he / ru / es / ar
    """
    if not code:
        return "en"

    code = code.lower()

    if code.startswith("he"):
        return "he"
    if code.startswith("iw"):  # יש לקוחות ישנים של טלגרם
        return "he"
    if code.startswith("ru"):
        return "ru"
    if code.startswith("es"):
        return "es"
    if code.startswith("ar"):
        return "ar"

    return "en"


# === בסיס הטקסטים לפי שפה ===
LANG_DATA: Dict[str, Dict[str, str]] = {
    "en": {
        # ----- language menu -----
        "LANGUAGE_MENU_TITLE": "Choose your preferred language:",
        "LANGUAGE_BUTTON_EN": "English",
        "LANGUAGE_BUTTON_HE": "עברית",
        "LANGUAGE_BUTTON_RU": "Русский",
        "LANGUAGE_BUTTON_ES": "Español",
        "LANGUAGE_BUTTON_AR": "العربية",
        "LANGUAGE_SET_CONFIRM": "Your preferred language has been updated.",
        #  מיוחדים לפי שפה (משתמשים בהם בקוד)
        "LANGUAGE_SET_CONFIRM_HE": "השפה המועדפת שלך עודכנה לעברית.",
        "LANGUAGE_SET_CONFIRM_RU": "Ваш предпочтительный язык обновлён на русский.",
        "LANGUAGE_SET_CONFIRM_ES": "Tu idioma preferido se ha cambiado a español.",
        # no special one for Arabic – נשתמש ב־LANGUAGE_SET_CONFIRM של ar

        # ----- /start -----
        "START_TITLE": "Welcome to the SLH Investor Gateway.",
        "START_INTRO_MIN_INVEST": (
            "This bot is intended for strategic investors (minimum {min_invest:,} ILS)."
        ),
        "START_FEATURES_INTRO": "With this bot you can:",
        "START_FEATURE_1": "- Link your personal BNB wallet (BSC)",
        "START_FEATURE_2": "- View your off-chain SLH balance",
        "START_FEATURE_3": "- Transfer SLH units to other investors (off-chain)",
        "START_FEATURE_4": "- Access external links for BNB purchase and staking info",
        "START_NEXT_STEPS_TITLE": "Next steps:",
        "START_STEP_LINK_WALLET_MISSING": "1) Use /link_wallet to connect your BNB (BSC) address.",
        "START_STEP_LINK_WALLET_SET": "1) BNB wallet linked: {bnb_address}",
        "START_STEP_BALANCE_ZERO": (
            "2) Once your existing investment is recorded, you will see your SLH balance via /balance."
        ),
        "START_STEP_BALANCE_NONZERO": (
            "2) Current SLH balance: {balance:.4f} (see /balance)."
        ),
        "START_STEP_WALLET": "3) Use /wallet to view full wallet details and ecosystem links.",
        "START_STEP_WHOAMI": "4) Use /whoami to see your ID, username and wallet status.",
        "START_STEP_SUMMARY": "5) Use /summary for a full investor dashboard.",
        "START_STEP_HISTORY": "6) Use /history to review your latest transactions.",
        "START_FOOTER_MENU": "You can also open /menu for a button-based experience.",
        "START_FOOTER_LANGUAGE": "You can change the interface language via /language.",

        # ----- /help -----
        "HELP_TITLE": "SLH Wallet Bot – Help",
        "HELP_BODY": (
            "/start – Intro and onboarding\n"
            "/menu – Main menu with buttons\n"
            "/summary – Full investor dashboard (wallet + balance + profile)\n"
            "/wallet – Wallet details and ecosystem links\n"
            "/link_wallet – Link your personal BNB (BSC) address\n"
            "/balance – View your SLH off-chain balance (+ on-chain if available)\n"
            "/history – Last transactions in the internal ledger\n"
            "/transfer – Internal off-chain transfer to another user\n"
            "/whoami – See your Telegram ID, username and wallet status\n"
            "/docs – Open the official SLH investor docs\n"
            "/language – Choose your preferred interface language\n"
            "/staking – Staking & yields (coming soon)\n"
            "/signals – Trading signals (coming soon)\n"
            "/academy – SLH Academy (coming soon)\n"
            "/referrals – Referral program (coming soon)\n"
            "/reports – Investor reports (coming soon)\n"
            "/portfolio_pro – Advanced portfolio (coming soon)\n"
            "\n"
            "Admin only:\n"
            "/admin_menu – Admin tools overview\n"
            "/admin_credit – Credit SLH to a user\n"
            "/admin_list_users – List users with balances\n"
            "/admin_ledger – Global ledger view (last 50 txs)\n"
            "/admin_selftest – Run deep self-test (DB/ENV/BSC/Telegram)\n"
        ),

        # ----- generic errors -----
        "GENERIC_UNKNOWN_COMMAND": "Command not recognized.\nUse /help to see available commands.",
    },
    "he": {
        # ----- language menu -----
        "LANGUAGE_MENU_TITLE": "בחר/י שפה מועדפת:",
        "LANGUAGE_BUTTON_EN": "English",
        "LANGUAGE_BUTTON_HE": "עברית",
        "LANGUAGE_BUTTON_RU": "Русский",
        "LANGUAGE_BUTTON_ES": "Español",
        "LANGUAGE_BUTTON_AR": "العربية",
        "LANGUAGE_SET_CONFIRM": "השפה המועדפת שלך עודכנה.",
        "LANGUAGE_SET_CONFIRM_HE": "השפה המועדפת שלך עודכנה לעברית.",
        "LANGUAGE_SET_CONFIRM_RU": "השפה המועדפת שלך עודכנה לרוסית.",
        "LANGUAGE_SET_CONFIRM_ES": "השפה המועדפת שלך עודכנה לספרדית.",

        # ----- /start -----
        "START_TITLE": "ברוך הבא ל-SLH Investor Gateway.",
        "START_INTRO_MIN_INVEST": (
            "הבוט מיועד למשקיעים אסטרטגיים (מינימום {min_invest:,} ₪)."
        ),
        "START_FEATURES_INTRO": "באמצעות הבוט ניתן:",
        "START_FEATURE_1": "- לקשר את ארנק ה-BNB האישי שלך (BSC)",
        "START_FEATURE_2": "- לראות את יתרת ה-SLH שלך במערכת (Off-Chain)",
        "START_FEATURE_3": "- להעביר יחידות SLH למשקיעים אחרים במערכת (Off-Chain)",
        "START_FEATURE_4": "- לקבל קישורים חיצוניים לרכישת BNB ולמידע על סטייקינג",
        "START_NEXT_STEPS_TITLE": "הצעדים הבאים:",
        "START_STEP_LINK_WALLET_MISSING": "1) השתמש/י ב-/link_wallet כדי לחבר את כתובת ה-BNB שלך.",
        "START_STEP_LINK_WALLET_SET": "1) ארנק BNB מחובר: {bnb_address}",
        "START_STEP_BALANCE_ZERO": (
            "2) לאחר שיוזנו ההשקעות הקיימות שלך, תוכל/י לראות את יתרת ה-SLH ב-/balance."
        ),
        "START_STEP_BALANCE_NONZERO": (
            "2) יתרת ה-SLH הנוכחית שלך: {balance:.4f} (ראו /balance)."
        ),
        "START_STEP_WALLET": "3) /wallet – פירוט ארנק וקישורים באקו-סיסטם.",
        "START_STEP_WHOAMI": "4) /whoami – מזהה טלגרם, משתמש וסטטוס ארנק.",
        "START_STEP_SUMMARY": "5) /summary – דשבורד משקיע במסך אחד.",
        "START_STEP_HISTORY": "6) /history – היסטוריית טרנזקציות אחרונות.",
        "START_FOOTER_MENU": "ניתן גם לפתוח /menu לתפריט כפתורים.",
        "START_FOOTER_LANGUAGE": "אפשר לשנות שפה דרך /language.",

        # ----- /help -----
        "HELP_TITLE": "SLH Wallet Bot – עזרה",
        "HELP_BODY": (
            "/start – מסך פתיחה והסבר\n"
            "/menu – תפריט כפתורים ראשי\n"
            "/summary – דשבורד משקיע (ארנק + יתרה + פרופיל)\n"
            "/wallet – פרטי ארנק וקישורי אקו-סיסטם\n"
            "/link_wallet – קישור כתובת BNB אישית (BSC)\n"
            "/balance – צפייה ביתרת SLH במערכת (+ מידע On-Chain אם קיים)\n"
            "/history – עד 10 הטרנזקציות האחרונות במערכת\n"
            "/transfer – העברת SLH פנימית למשתמש אחר\n"
            "/whoami – פרופיל המשקיע שלך במערכת\n"
            "/docs – פתיחת מסמכי המשקיעים הרשמיים\n"
            "/language – בחירת שפת ממשק\n"
            "/staking – סטייקינג ותשואות (בקרוב)\n"
            "/signals – אותות מסחר (בקרוב)\n"
            "/academy – אקדמיית SLH (בקרוב)\n"
            "/referrals – תוכנית הפניות (בקרוב)\n"
            "/reports – דוחות משקיעים (בקרוב)\n"
            "/portfolio_pro – פורטפוליו מתקדם (בקרוב)\n"
            "\n"
            "לאדמין בלבד:\n"
            "/admin_menu – תפריט כלים לאדמין\n"
            "/admin_credit – טעינת SLH למשתמש\n"
            "/admin_list_users – רשימת משתמשים ויתרות\n"
            "/admin_ledger – תצוגה גלובלית של ה-Ledger (50 אחרונות)\n"
            "/admin_selftest – בדיקת Self-Test מלאה (DB / ENV / BSC / Telegram)\n"
        ),

        "GENERIC_UNKNOWN_COMMAND": "הפקודה לא זוהתה.\nהשתמש/י ב-/help כדי לראות את כל הפקודות.",
    },
    "ru": {
        "LANGUAGE_MENU_TITLE": "Выберите предпочитаемый язык:",
        "LANGUAGE_BUTTON_EN": "English",
        "LANGUAGE_BUTTON_HE": "עברית",
        "LANGUAGE_BUTTON_RU": "Русский",
        "LANGUAGE_BUTTON_ES": "Español",
        "LANGUAGE_BUTTON_AR": "العربية",
        "LANGUAGE_SET_CONFIRM": "Предпочитаемый язык обновлён.",
        "LANGUAGE_SET_CONFIRM_HE": "Ваш язык обновлён на иврит.",
        "LANGUAGE_SET_CONFIRM_RU": "Ваш язык обновлён на русский.",
        "LANGUAGE_SET_CONFIRM_ES": "Ваш язык обновлён на испанский.",

        "START_TITLE": "Добро пожаловать в SLH Investor Gateway.",
        "START_INTRO_MIN_INVEST": (
            "Этот бот предназначен для стратегических инвесторов (от {min_invest:,} ₪)."
        ),
        "START_FEATURES_INTRO": "С помощью бота вы можете:",
        "START_FEATURE_1": "- привязать личный BNB-кошелёк (BSC)",
        "START_FEATURE_2": "- просматривать off-chain баланс SLH",
        "START_FEATURE_3": "- переводить единицы SLH другим инвесторам внутри системы",
        "START_FEATURE_4": "- получать внешние ссылки для покупки BNB и стейкинга",
        "START_NEXT_STEPS_TITLE": "Следующие шаги:",
        "START_STEP_LINK_WALLET_MISSING": "1) Используйте /link_wallet, чтобы привязать адрес BNB.",
        "START_STEP_LINK_WALLET_SET": "1) Привязанный BNB-адрес: {bnb_address}",
        "START_STEP_BALANCE_ZERO": (
            "2) После занесения ваших инвестиций вы увидите баланс SLH через /balance."
        ),
        "START_STEP_BALANCE_NONZERO": (
            "2) Текущий баланс SLH: {balance:.4f} (см. /balance)."
        ),
        "START_STEP_WALLET": "3) /wallet – детали кошелька и ссылки экосистемы.",
        "START_STEP_WHOAMI": "4) /whoami – ваш Telegram ID, имя пользователя и статус кошелька.",
        "START_STEP_SUMMARY": "5) /summary – сводный дашборд инвестора.",
        "START_STEP_HISTORY": "6) /history – последние транзакции.",
        "START_FOOTER_MENU": "Также можно открыть /menu для меню с кнопками.",
        "START_FOOTER_LANGUAGE": "Язык интерфейса можно изменить через /language.",

        "HELP_TITLE": "SLH Wallet Bot – справка",
        "HELP_BODY": (
            "/start – вступление и подключение\n"
            "/menu – главное меню с кнопками\n"
            "/summary – дашборд инвестора\n"
            "/wallet – детали кошелька и ссылки\n"
            "/link_wallet – привязать BNB-адрес (BSC)\n"
            "/balance – off-chain баланс SLH\n"
            "/history – последние транзакции\n"
            "/transfer – перевод SLH внутри системы\n"
            "/whoami – информация о вашем профиле\n"
            "/docs – официальные документы для инвесторов\n"
            "/language – выбор языка\n"
            "/staking – стейкинг и доходность (скоро)\n"
            "/signals – торговые сигналы (скоро)\n"
            "/academy – академия SLH (скоро)\n"
            "/referrals – реферальная программа (скоро)\n"
            "/reports – отчёты для инвесторов (скоро)\n"
            "/portfolio_pro – расширенный портфель (скоро)\n"
            "\n"
            "Только для админа:\n"
            "/admin_menu, /admin_credit, /admin_list_users, /admin_ledger, /admin_selftest\n"
        ),

        "GENERIC_UNKNOWN_COMMAND": "Команда не распознана.\nИспользуйте /help, чтобы увидеть доступные команды.",
    },
    "es": {
        "LANGUAGE_MENU_TITLE": "Elige tu idioma preferido:",
        "LANGUAGE_BUTTON_EN": "English",
        "LANGUAGE_BUTTON_HE": "עברית",
        "LANGUAGE_BUTTON_RU": "Русский",
        "LANGUAGE_BUTTON_ES": "Español",
        "LANGUAGE_BUTTON_AR": "العربية",
        "LANGUAGE_SET_CONFIRM": "Tu idioma preferido se ha actualizado.",
        "LANGUAGE_SET_CONFIRM_HE": "Tu idioma se ha cambiado a hebreo.",
        "LANGUAGE_SET_CONFIRM_RU": "Tu idioma se ha cambiado a ruso.",
        "LANGUAGE_SET_CONFIRM_ES": "Tu idioma se ha cambiado a español.",

        "START_TITLE": "Bienvenido al SLH Investor Gateway.",
        "START_INTRO_MIN_INVEST": (
            "Este bot está pensado para inversores estratégicos (mínimo {min_invest:,} ILS)."
        ),
        "START_FEATURES_INTRO": "Con este bot puedes:",
        "START_FEATURE_1": "- Vincular tu monedero personal de BNB (BSC)",
        "START_FEATURE_2": "- Ver tu saldo off-chain de SLH",
        "START_FEATURE_3": "- Transferir unidades SLH a otros inversores (off-chain)",
        "START_FEATURE_4": "- Acceder a enlaces externos para comprar BNB y staking",
        "START_NEXT_STEPS_TITLE": "Siguientes pasos:",
        "START_STEP_LINK_WALLET_MISSING": "1) Usa /link_wallet para conectar tu dirección de BNB (BSC).",
        "START_STEP_LINK_WALLET_SET": "1) Monedero BNB vinculado: {bnb_address}",
        "START_STEP_BALANCE_ZERO": (
            "2) Una vez registradas tus inversiones, podrás ver tu saldo SLH en /balance."
        ),
        "START_STEP_BALANCE_NONZERO": (
            "2) Saldo actual de SLH: {balance:.4f} (ver /balance)."
        ),
        "START_STEP_WALLET": "3) /wallet – detalles del monedero y enlaces del ecosistema.",
        "START_STEP_WHOAMI": "4) /whoami – tu ID de Telegram, usuario y estado del monedero.",
        "START_STEP_SUMMARY": "5) /summary – panel completo de inversor.",
        "START_STEP_HISTORY": "6) /history – últimas transacciones.",
        "START_FOOTER_MENU": "También puedes abrir /menu para un menú con botones.",
        "START_FOOTER_LANGUAGE": "Puedes cambiar el idioma de la interfaz con /language.",

        "HELP_TITLE": "SLH Wallet Bot – ayuda",
        "HELP_BODY": (
            "/start – introducción\n"
            "/menu – menú principal con botones\n"
            "/summary – panel completo del inversor\n"
            "/wallet – detalles del monedero y enlaces\n"
            "/link_wallet – vincular tu dirección BNB (BSC)\n"
            "/balance – ver tu saldo off-chain de SLH\n"
            "/history – últimas transacciones\n"
            "/transfer – transferencia interna de SLH\n"
            "/whoami – ver tu perfil en el sistema\n"
            "/docs – documentación oficial para inversores\n"
            "/language – elegir idioma\n"
            "/staking – staking y rendimientos (próximamente)\n"
            "/signals – señales de trading (próximamente)\n"
            "/academy – academia SLH (próximamente)\n"
            "/referrals – programa de referidos (próximamente)\n"
            "/reports – informes de inversores (próximamente)\n"
            "/portfolio_pro – portafolio avanzado (próximamente)\n"
            "\n"
            "Solo admin:\n"
            "/admin_menu, /admin_credit, /admin_list_users, /admin_ledger, /admin_selftest\n"
        ),

        "GENERIC_UNKNOWN_COMMAND": "Comando no reconocido.\nUsa /help para ver los comandos disponibles.",
    },
    "ar": {
        "LANGUAGE_MENU_TITLE": "اختر لغتك المفضلة:",
        "LANGUAGE_BUTTON_EN": "English",
        "LANGUAGE_BUTTON_HE": "עברית",
        "LANGUAGE_BUTTON_RU": "Русский",
        "LANGUAGE_BUTTON_ES": "Español",
        "LANGUAGE_BUTTON_AR": "العربية",
        "LANGUAGE_SET_CONFIRM": "تم تحديث لغتك المفضلة.",

        "START_TITLE": "مرحباً بك في بوابة مستثمري SLH.",
        "START_INTRO_MIN_INVEST": (
            "هذا البوت مخصص للمستثمرين الاستراتيجيين (حد أدنى {min_invest:,} شيكل)."
        ),
        "START_FEATURES_INTRO": "من خلال هذا البوت يمكنك:",
        "START_FEATURE_1": "- ربط محفظة BNB الشخصية الخاصة بك (شبكة BSC)",
        "START_FEATURE_2": "- عرض رصيد SLH خارج السلسلة (Off-Chain)",
        "START_FEATURE_3": "- تحويل وحدات SLH إلى مستثمرين آخرين داخل النظام",
        "START_FEATURE_4": "- الوصول إلى روابط خارجية لشراء BNB ومعلومات عن الـ Staking",
        "START_NEXT_STEPS_TITLE": "الخطوات التالية:",
        "START_STEP_LINK_WALLET_MISSING": "1) استخدم /link_wallet لربط عنوان BNB الخاص بك.",
        "START_STEP_LINK_WALLET_SET": "1) محفظة BNB المرتبطة: {bnb_address}",
        "START_STEP_BALANCE_ZERO": (
            "2) بعد تسجيل استثماراتك سيتم عرض رصيد SLH الخاص بك عبر /balance."
        ),
        "START_STEP_BALANCE_NONZERO": (
            "2) رصيد SLH الحالي: {balance:.4f} (انظر /balance)."
        ),
        "START_STEP_WALLET": "3) /wallet – تفاصيل المحفظة وروابط النظام.",
        "START_STEP_WHOAMI": "4) /whoami – معرف تيليجرام، اسم المستخدم وحالة المحفظة.",
        "START_STEP_SUMMARY": "5) /summary – لوحة معلومات شاملة للمستثمر.",
        "START_STEP_HISTORY": "6) /history – أحدث العمليات.",
        "START_FOOTER_MENU": "يمكنك أيضاً فتح /menu لعرض قائمة الأزرار.",
        "START_FOOTER_LANGUAGE": "يمكنك تغيير لغة الواجهة عبر /language.",

        "HELP_TITLE": "SLH Wallet Bot – مساعدة",
        "HELP_BODY": (
            "/start – شاشة البداية وشرح موجز\n"
            "/menu – القائمة الرئيسية بالأزرار\n"
            "/summary – لوحة معلومات للمستثمر\n"
            "/wallet – تفاصيل المحفظة وروابط المنظومة\n"
            "/link_wallet – ربط عنوان BNB الخاص بك\n"
            "/balance – عرض رصيد SLH خارج السلسلة\n"
            "/history – أحدث العمليات\n"
            "/transfer – تحويل داخلي لوحدات SLH\n"
            "/whoami – عرض ملفك في النظام\n"
            "/docs – المستندات الرسمية للمستثمرين\n"
            "/language – اختيار لغة الواجهة\n"
            "/staking – Staking وعوائد (قريباً)\n"
            "/signals – إشارات تداول (قريباً)\n"
            "/academy – أكاديمية SLH (قريباً)\n"
            "/referrals – برنامج الإحالة (قريباً)\n"
            "/reports – تقارير المستثمرين (قريباً)\n"
            "/portfolio_pro – محفظة متقدمة (قريباً)\n"
            "\n"
            "للأدمن فقط:\n"
            "/admin_menu, /admin_credit, /admin_list_users, /admin_ledger, /admin_selftest\n"
        ),

        "GENERIC_UNKNOWN_COMMAND": "لم يتم التعرف على الأمر.\nاستخدم /help لعرض الأوامر المتاحة.",
    },
}

# === מודולי 'בקרוב' ו-Coming soon (נוסיף/נעדכן בסוף ה-LANG_DATA) ===

EXTRA_KEYS = {
    "en": {
        "MODULE_NAME_STAKING": "Staking & yields",
        "MODULE_NAME_SIGNALS": "Trading signals",
        "MODULE_NAME_ACADEMY": "SLH Academy",
        "MODULE_NAME_REFERRALS": "Referral program",
        "MODULE_NAME_REPORTS": "Investor reports",
        "MODULE_NAME_PORTFOLIO": "Advanced portfolio",
        "COMING_SOON_TITLE": "Coming soon",
        "COMING_SOON_BODY": (
            "The module \"{module}\" is on the roadmap and will be available soon.\n"
            "For now you can already use the existing wallet, balance and transfer tools.\n"
            "Stay tuned – this is part of the SLH economic engine."
        ),
    },
    "he": {
        "MODULE_NAME_STAKING": "סטייקינג ותשואות",
        "MODULE_NAME_SIGNALS": "אותות מסחר",
        "MODULE_NAME_ACADEMY": "אקדמיית SLH",
        "MODULE_NAME_REFERRALS": "תוכנית הפניות",
        "MODULE_NAME_REPORTS": "דוחות משקיעים",
        "MODULE_NAME_PORTFOLIO": "פורטפוליו מתקדם",
        "COMING_SOON_TITLE": "בקרוב",
        "COMING_SOON_BODY": (
            "המודול \"{module}\" נמצא כבר בתכנון וייפתח בהמשך.\n"
            "בינתיים אפשר להשתמש בארנק, ביתרות ובהעברות הקיימות.\n"
            "עקבו אחר העדכונים – זה חלק מהמנוע הכלכלי של SLH."
        ),
    },
    "ru": {
        "MODULE_NAME_STAKING": "Стейкинг и доходность",
        "MODULE_NAME_SIGNALS": "Торговые сигналы",
        "MODULE_NAME_ACADEMY": "Академия SLH",
        "MODULE_NAME_REFERRALS": "Реферальная программа",
        "MODULE_NAME_REPORTS": "Инвестиционные отчёты",
        "MODULE_NAME_PORTFOLIO": "Расширенный портфель",
        "COMING_SOON_TITLE": "Скоро",
        "COMING_SOON_BODY": (
            "Модуль \"{module}\" уже в планах и будет доступен позже.\n"
            "Пока вы можете пользоваться кошельком, балансом и переводами.\n"
            "Следите за обновлениями – это часть экономического двигателя SLH."
        ),
    },
    "es": {
        "MODULE_NAME_STAKING": "Staking y rendimientos",
        "MODULE_NAME_SIGNALS": "Señales de trading",
        "MODULE_NAME_ACADEMY": "Academia SLH",
        "MODULE_NAME_REFERRALS": "Programa de referidos",
        "MODULE_NAME_REPORTS": "Informes para inversores",
        "MODULE_NAME_PORTFOLIO": "Portafolio avanzado",
        "COMING_SOON_TITLE": "Próximamente",
        "COMING_SOON_BODY": (
            "El módulo \"{module}\" está en la hoja de ruta y estará disponible pronto.\n"
            "Por ahora ya puedes usar el monedero, el saldo y las transferencias.\n"
            "Estate atento: esto forma parte del motor económico de SLH."
        ),
    },
    "ar": {
        "MODULE_NAME_STAKING": "الستيكينغ والعوائد",
        "MODULE_NAME_SIGNALS": "إشارات التداول",
        "MODULE_NAME_ACADEMY": "أكاديمية SLH",
        "MODULE_NAME_REFERRALS": "برنامج الإحالة",
        "MODULE_NAME_REPORTS": "تقارير المستثمرين",
        "MODULE_NAME_PORTFOLIO": "محفظة متقدمة",
        "COMING_SOON_TITLE": "قريباً",
        "COMING_SOON_BODY": (
            "الوحدة \"{module}\" موجودة في خطة العمل وستتوفر قريباً.\n"
            "حالياً يمكنك استخدام المحفظة والرصيد والتحويلات الحالية.\n"
            "تابع التحديثات – فهذا جزء من المحرك الاقتصادي لـ SLH."
        ),
    },
}

for lang_code, mapping in EXTRA_KEYS.items():
    if lang_code in LANG_DATA:
        LANG_DATA[lang_code].update(mapping)


def t(lang: str, key: str) -> str:
    """
    תרגום פשוט:
    1. ניסיון לפי lang
    2. אם חסר – fallback ל-en
    3. אם עדיין חסר – מחזיר את המפתח עצמו (key)
    """
    lang = normalize_lang(lang)
    data = LANG_DATA.get(lang, {})
    if key in data:
        return data[key]
    data_en = LANG_DATA.get("en", {})
    if key in data_en:
        return data_en[key]
    return key
