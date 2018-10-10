import tkgcore

bot = tkgcore.Bot("_binance_test.json", "mm.log")

bot.init_logging()
bot.load_config_from_file(bot.config_filename)

bot.init_exchange()
bot.test_balance = 0
bot.start_currency = list(["BTC"])
bot.init_exchange()
bot.load_markets()
balance = bot.load_balance()

ticker = bot.exchange._ccxt.fetch_tickers("ETH/BTC")

order1_price = ticker["ETH/BTC"]["bid"]  # BTC -> ETH
order2_price = ticker["ETH/BTC"]["ask"]  # ETH -> BTC

start_amount = 0.0011

dest_amount1 = start_amount / order1_price

order1 = tkgcore.RecoveryOrder("ETH/BTC", "BTC", start_amount, "ETH", dest_amount1,
                              cancel_threshold=bot.markets["ETH/BTC"]["limits"]["amount"]["min"],
                              max_best_amount_order_updates=300, max_order_updates=20)

om = tkgcore.OwaManager(bot.exchange)

om.add_order(order1)

while len(om.get_open_orders()) > 0:
    om.proceed_orders()

dest_amount2 = order1.filled_start_amount * 1.001

order2 = tkgcore.RecoveryOrder("ETH/BTC", "ETH", order1.filled_dest_amount, "BTC", dest_amount2,
                              cancel_threshold=bot.markets["ETH/BTC"]["limits"]["amount"]["min"],
                              max_best_amount_order_updates=300, max_order_updates=20)

om.add_order(order2)

while len(om.get_open_orders()) > 0:
    om.proceed_orders()

print("Filled order1 BTC spent {}".format(order1.filled_start_amount))
print("Goint Get BTC {}".format(dest_amount2))
print("Got BTC {}".format(order2.filled_dest_amount))

print(order2.filled_dest_amount)
if order2.filled_dest_amount > start_amount:
    print("OK")

