# Псевдо-код интеграции AI в Telegram-бот

import torch
from telebot import TeleBot
import yfinance as yf

model = torch.load('ai_portfolio_model.pth')
model.eval()

def generate_portfolio(user_request):
    tickers = ['AAPL', 'MSFT', 'GOOGL']
    data = yf.download(tickers, period="1y")
    weights = model.predict(data)  # возвращает [0.4, 0.35, 0.25]
    expected_return = calculate_return(weights, data)
    risk = calculate_risk(weights, data)
    
    return f"Рекомендуемый портфель: {weights}\nОжидаемая доходность: {expected_return:.2%}\nРиск: {risk:.2%}"

bot = TeleBot("TOKEN")

@bot.message_handler(commands=['portfolio'])
def send_portfolio(message):
    result = generate_portfolio(message.text)
    bot.reply_to(message, result)
