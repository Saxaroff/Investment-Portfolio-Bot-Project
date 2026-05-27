import json
import os
from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
import telebot
from telebot import types

from config import TOKEN, PERIOD_MAP, PORTFOLIO_PERIOD_CHOICES, STATS_PERIOD_CHOICES
from services.market_data import (
    normalize_tickers,
    download_close_prices,
    get_risk_free_rate,
    get_stock_info,
    get_stock_history,
)
from services.portfolio import build_full_portfolio_report, optimize_portfolios
from services.formatters import format_full_portfolio_report, format_weights
from services.ai_service import explain_portfolio_with_llm
bot = telebot.TeleBot(TOKEN)
user_data = {}


def make_keyboard(buttons, row_width=2):
    markup = types.ReplyKeyboardMarkup(row_width=row_width, resize_keyboard=True)
    markup.add(*[types.KeyboardButton(btn) for btn in buttons])
    return markup


def main_menu_keyboard():
    return make_keyboard([
        '📊 Статистика акций',
        '📈 Анализ портфеля',
        '💼 Составление портфеля на определенную сумму',
        '🔍 Получение тикера',
        'ℹ️ Справочник'
    ], row_width=2)


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Привет! Я телеграм-бот для статистики акций и анализа портфеля.",
        reply_markup=main_menu_keyboard()
    )


def send_main_menu(message, custom_message=None):
    text = custom_message or "Что бы вы хотели сделать дальше?"
    bot.reply_to(message, text, reply_markup=main_menu_keyboard())


def get_period(text):
    return PERIOD_MAP.get(text, '1mo')


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        if message.text == '📊 Статистика акций':
            user_data[message.chat.id] = {'action': message.text}
            bot.reply_to(
                message,
                "Выберите временной период:",
                reply_markup=make_keyboard(STATS_PERIOD_CHOICES, row_width=2)
            )

        elif message.text == '🔍 Получение тикера':
            user_data[message.chat.id] = {'action': message.text}
            bot.reply_to(message, "Введите название компании для получения тикера:")
            bot.register_next_step_handler(message, get_ticker)

        elif message.text == 'ℹ️ Справочник':
            show_reference(message)

        elif message.text in ['📈 Анализ портфеля', '💼 Составление портфеля на определенную сумму']:
            user_data[message.chat.id] = {'action': message.text}
            bot.reply_to(
                message,
                "Выберите временной период:",
                reply_markup=make_keyboard(PORTFOLIO_PERIOD_CHOICES, row_width=2)
            )

        elif message.text in STATS_PERIOD_CHOICES:
            if message.chat.id not in user_data:
                bot.reply_to(message, "Пожалуйста, воспользуйтесь кнопками для выбора.")
                return

            user_data[message.chat.id]['period'] = message.text
            action = user_data[message.chat.id]['action']

            if action == '📈 Анализ портфеля':
                bot.reply_to(
                    message,
                    "Введите тикеры через пробел для анализа портфеля.\nПример: AAPL MSFT NVDA"
                )
                bot.register_next_step_handler(message, analyze_portfolio)

            elif action == '📊 Статистика акций':
                bot.reply_to(
                    message,
                    "Введите тикеры через пробел для получения статистики.\nПример: AAPL MSFT"
                )
                bot.register_next_step_handler(message, show_stock_statistics)

            elif action == '💼 Составление портфеля на определенную сумму':
                bot.reply_to(
                    message,
                    "Введите сумму и тикеры через пробел.\nПример: 5000 AAPL MSFT NVDA"
                )
                bot.register_next_step_handler(message, build_portfolio)

        else:
            bot.reply_to(message, "Пожалуйста, воспользуйтесь кнопками для выбора.")

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")


def analyze_portfolio(message):
    try:
        tickers = normalize_tickers(message.text.split())
        period = get_period(user_data[message.chat.id]['period'])

        close_data = download_close_prices(tickers, period)
        risk_free_rate = get_risk_free_rate()
        result = optimize_portfolios(close_data, risk_free_rate)

        max_sharpe = result["max_sharpe"]
        min_vol = result["min_volatility"]

        response = (
            "📊 Анализ портфеля завершен\n\n"
            "📈 Максимальный коэффициент Шарпа\n"
            f"Ожидаемая годовая доходность: {max_sharpe['theoretical_performance'][0] * 100:.2f}%\n"
            f"Годовой риск: {max_sharpe['theoretical_performance'][1] * 100:.2f}%\n"
            f"Шарп: {max_sharpe['theoretical_performance'][2]:.3f}\n\n"
            "Распределение:\n"
            f"{format_weights(max_sharpe['weights'])}\n\n"
            "🛡 Минимальная волатильность\n"
            f"Ожидаемая годовая доходность: {min_vol['theoretical_performance'][0] * 100:.2f}%\n"
            f"Годовой риск: {min_vol['theoretical_performance'][1] * 100:.2f}%\n"
            f"Шарп: {min_vol['theoretical_performance'][2]:.3f}\n\n"
            "Распределение:\n"
            f"{format_weights(min_vol['weights'])}"
        )

        bot.reply_to(message, response)
        send_main_menu(message, "Анализ завершен. Что бы вы хотели сделать дальше?")

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")
        send_main_menu(message, "Произошла ошибка. Что бы вы хотели сделать дальше?")


def get_recommendation(fundamental_metrics):
    recommendation = ""

    if 'beta' in fundamental_metrics and fundamental_metrics['beta'] is not None:
        beta = fundamental_metrics['beta']
        if beta < 1:
            recommendation += "Бета меньше 1, что указывает на меньшую волатильность по сравнению с рынком.\n"
        elif beta > 1:
            recommendation += "Бета больше 1, что указывает на большую волатильность по сравнению с рынком.\n"
        else:
            recommendation += "Бета равна 1, что указывает на среднюю волатильность по сравнению с рынком.\n\n"

    if 'currentRatio' in fundamental_metrics and fundamental_metrics['currentRatio'] is not None:
        current_ratio = fundamental_metrics['currentRatio']
        if current_ratio > 2:
            recommendation += "Текущая ликвидность высокая, что указывает на хорошую способность компании погасить текущие обязательства.\n"
        elif current_ratio < 1:
            recommendation += "Текущая ликвидность низкая, что может указывать на возможные проблемы с погашением текущих обязательств.\n"
        else:
            recommendation += "Текущая ликвидность находится в норме.\n\n"

    if 'enterpriseToEbitda' in fundamental_metrics and fundamental_metrics['enterpriseToEbitda'] is not None:
        ev_ebitda = fundamental_metrics['enterpriseToEbitda']
        if ev_ebitda < 10:
            recommendation += "Низкий показатель EV/EBITDA может свидетельствовать о недооцененности компании.\n"
        elif ev_ebitda > 15:
            recommendation += "Высокий показатель EV/EBITDA может свидетельствовать о переоцененности компании.\n"
        else:
            recommendation += "Показатель EV/EBITDA находится в норме.\n"

    return recommendation or "Недостаточно фундаментальных данных для автоматического комментария."
def show_stock_statistics(message):
    try:
        stocks = normalize_tickers(message.text.split())
        period_text = user_data[message.chat.id]['period']
        period = get_period(period_text)
        response = ''

        for stock in stocks:
            try:
                stock_info = get_stock_info(stock)
                info = stock_info.info
                stock_name = info.get('shortName', stock)
                stock_history = get_stock_history(stock, period)

                stock_change_percentage = (stock_history.iloc[-1] - stock_history.iloc[0]) / stock_history.iloc[0] * 100
                average_price = stock_history.mean()
                std_dev_price = stock_history.std()

                response += f"{stock_name} ({stock}):\n"
                response += "Общая информация:\n"
                response += f"Изменение цены за {period_text}: {stock_change_percentage:.2f}%\n"
                response += f"Средняя цена за {period_text}: ${average_price:.2f}\n"
                response += f"Стандартное отклонение цены за {period_text}: ${std_dev_price:.2f}\n\n"

                response += "Финансовые метрики:\n"
                for label, key in [
                    ("P/E Ratio", "trailingPE"),
                    ("P/S Ratio", "priceToSalesTrailing12Months"),
                    ("Beta", "beta"),
                    ("EV/EBITDA", "enterpriseToEbitda"),
                    ("EV/Revenue", "enterpriseToRevenue"),
                    ("Объем торгов", "volume"),
                    ("Капитализация рынка", "marketCap"),
                    ("Текущая ликвидность (Current Ratio)", "currentRatio"),
                    ("Dividend Rate", "dividendRate"),
                    ("PEG Ratio", "pegRatio"),
                ]:
                    value = info.get(key)
                    if value is not None:
                        response += f"{label}: {value}\n"

                dividend_yield = info.get("dividendYield")
                if dividend_yield is not None:
                    response += f"Дивидендная доходность: {dividend_yield * 100:.2f}%\n"

                institutional_ownership = info.get("institutionalOwnership")
                if institutional_ownership is not None:
                    response += f"Доля институциональных инвесторов: {institutional_ownership * 100:.2f}%\n"

                response += "\n"

                plt.figure(figsize=(8, 4))
                plt.plot(stock_history.index, stock_history.values, label='Цена')
                plt.scatter(stock_history.index[-1], stock_history.values[-1], color='red', label='Последняя цена')
                plt.text(stock_history.index[-1], stock_history.values[-1], f'{stock_history.values[-1]:.2f}', color='red')
                plt.xlabel('Дата')
                plt.ylabel('Цена')
                plt.title(f'Изменение цены акций {stock_name} ({stock})')
                plt.xticks(rotation=30)
                plt.grid()
                plt.legend()

                buf = BytesIO()
                plt.tight_layout()
                plt.savefig(buf, format='png')
                buf.seek(0)
                bot.send_photo(message.chat.id, buf)
                plt.close()

                recommendation = get_recommendation(info)
                bot.send_message(message.chat.id, recommendation)

            except Exception as e:
                response += f"Ошибка при обработке акции {stock}: {str(e)}\n\n"

        bot.reply_to(message, response)
        send_main_menu(message, "Статистика завершена. Что бы вы хотели сделать дальше?")

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")
        send_main_menu(message, "Произошла ошибка. Что бы вы хотели сделать дальше?")
def save_portfolio(portfolio):
    with open("portfolio.json", "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
def load_portfolio():
    if os.path.exists("portfolio.json"):
        with open("portfolio.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None
def build_portfolio(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            raise ValueError("Нужно указать сумму и минимум два тикера. Пример: 5000 AAPL MSFT")

        amount = float(parts[0])
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля.")

        tickers = normalize_tickers(parts[1:])
        period = get_period(user_data[message.chat.id]['period'])

        close_data = download_close_prices(tickers, period)
        risk_free_rate = get_risk_free_rate()
        report = build_full_portfolio_report(close_data, amount, risk_free_rate)

        text_report = format_full_portfolio_report(report)
        bot.reply_to(message, text_report)

        try:
            portfolio_payload = {
                "market_stress": report.get("market_stress"),
                "max_sharpe": report.get("max_sharpe"),
                "min_volatility": report.get("min_volatility"),
            }

            llm_analysis = explain_portfolio_with_llm(portfolio_payload)
            bot.send_message(
                message.chat.id,
                f"AI-анализ портфеля:\n\n{llm_analysis}"
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"AI-анализ временно недоступен: {e}"
            )
        save_portfolio(report)

        weights = report["max_sharpe"]["weights"]
        labels = [ticker for ticker, weight in weights.items() if weight > 0]
        sizes = [weight for ticker, weight in weights.items() if weight > 0]

        if labels and sizes:
            fig, ax = plt.subplots(figsize=(8, 6))
            wedges, _ = ax.pie(sizes, labels=labels, startangle=90)
            ax.axis('equal')
            percentages = [f'{ticker}: {weight * 100:.2f}%' for ticker, weight in weights.items() if weight > 0]
            plt.title('Портфель с максимальным коэффициентом Шарпа')
            plt.legend(wedges, percentages, title="Активы", loc="center left", bbox_to_anchor=(1.05, 0.5))
            plt.tight_layout()

            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            bot.send_photo(message.chat.id, buf)
            plt.close()

        send_main_menu(message, "Составление портфеля завершено. Что бы вы хотели сделать дальше?")

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")
        send_main_menu(message, "Произошла ошибка. Что бы вы хотели сделать дальше?")
def show_reference(message):
    reference_text = """
Справочник по метрикам:

1. P/E Ratio (Price-to-Earnings Ratio):
- Отношение рыночной цены акции к прибыли на одну акцию.

2. P/S Ratio (Price-to-Sales Ratio):
- Отношение рыночной цены акции к выручке на одну акцию.

3. Дивидендная доходность:
- Отношение годовых дивидендов к текущей цене акции.

4. Beta:
- Волатильность акции относительно рынка.

5. Объем торгов:
- Количество акций, проданных и купленных за период.

6. Капитализация рынка:
- Общая рыночная стоимость всех акций компании.

7. EV/EBITDA:
- Показатель стоимости компании с учетом долга и денежных средств.

8. Текущая ликвидность (Current Ratio):
- Отношение текущих активов к текущим обязательствам.

9. Доля институциональных инвесторов:
- Процент акций, принадлежащих крупным инвесторам.

10. Forward P/E Ratio:
- Отношение текущей цены акции к ожидаемой прибыли.

11. Dividend Rate:
- Размер дивидендов на акцию.

12. PEG Ratio:
- Отношение P/E к ожидаемому росту прибыли.
"""
    bot.reply_to(message, reference_text)
    send_main_menu(message, "Справочник завершен. Что бы вы хотели сделать дальше?")
def get_ticker(message):
    try:
        company_name = message.text.lower()
        df = pd.read_excel('data/Tick.xlsx')
        ticker = None
        for _, row in df.iterrows():
            description = str(row.get('Description', '')).lower()
            if company_name in description:
                ticker = row.get('Symbol')
                break
        if ticker:
            bot.reply_to(message, f"Тикер для компании {message.text}: {ticker}")
        else:
            bot.reply_to(message, "Тикер для данной компании не найден.")

        send_main_menu(message, "Что бы вы хотели сделать дальше?")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")
        send_main_menu(message, "Произошла ошибка. Что бы вы хотели сделать дальше?")
bot.polling(none_stop=True)