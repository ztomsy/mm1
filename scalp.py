import tkgcore
from tkgcore import OrderWithAim
from scalp_bot import ScalpBot, ScalpsCollection, SingleScalp
import sys
import csv
import os
import time
from typing import Dict, Tuple, List
import copy


def log_scalp_status(_bot, _scalp):
    _bot.log(_bot.LOG_INFO, "######################################################################################")
    _bot.log(_bot.LOG_INFO, "Scalp ID: {}".format(_scalp.id))
    _bot.log(_bot.LOG_INFO, "Symbol: {}".format(_scalp.symbol))
    _bot.log(_bot.LOG_INFO, "Direction  {}->{}".format(_scalp.start_currency, _scalp.dest_currency))

    _bot.log(_bot.LOG_INFO,
             "State: {}. Depth: {}, Order1: price:{} status:{} filled:{}/{} (upd:{}/{}). Order2: price:{} status:{} state:{} filled:{}/{} (upd "
             "{}/{}) ".
             format(_scalp.state, _scalp.depth,
                    _scalp.order1.price if _scalp.order1 is not None else None,
                    _scalp.order1.status if _scalp.order1 is not None else None,
                    _scalp.order1.filled if _scalp.order1 is not None else None,
                    _scalp.order1.amount if _scalp.order1 is not None else None,
                    _scalp.order1.get_active_order().update_requests_count
                    if _scalp.order1 is not None and _scalp.order1.get_active_order() is not None else None,

                    _scalp.order1.max_order_updates if _scalp.order1 is not None else None,
                    _scalp.order2.price if _scalp.order2 is not None else None,
                    _scalp.order2.status if _scalp.order2 is not None else None,
                    _scalp.order2.state if _scalp.order2 is not None else None,
                    _scalp.order2.filled if _scalp.order2 is not None else None,
                    _scalp.order2.amount if _scalp.order2 is not None else None,
                    _scalp.order2.get_active_order().update_requests_count
                    if _scalp.order2 is not None and _scalp.order2.get_active_order() is not None else None,
                    _scalp.order2.max_order_updates if _scalp.order2 is not None else None))

    _bot.log(_bot.LOG_INFO, "######################################################################################")


def log_scalp_order(_bot, _scalp, _scalp_order: OrderWithAim):
    _bot.log(_bot.LOG_INFO, "######################################################################################")
    _bot.log(_bot.LOG_INFO, "Scalp ID: {}".format(_scalp.id))
    _bot.log(_bot.LOG_INFO,
             "State: {}. Order {}->{} status {} filled {}/{} (upd {}/{}).".
             format(_scalp.state,
                    _scalp_order.start_currency,
                    _scalp_order.dest_currency,
                    _scalp_order.status,
                    _scalp_order.filled,
                    _scalp_order.amount,
                    _scalp_order.get_active_order().update_requests_count,
                    _scalp_order.max_order_updates))


def report_close_scalp(_bot: ScalpBot, _scalp: SingleScalp):
    report = dict()

    report["scalp-id"] = _scalp.id
    report["result-fact-diff"] = float(_scalp.result_fact_diff)
    report["start-qty"] = float(_scalp.start_amount)
    report["cur1"] = str(_scalp.start_currency)
    report["cur2"] = str(_scalp.dest_currency)
    report["symbol"] = str(_scalp.symbol)
    report["state"] = str(_scalp.state)
    report["depth"] = str(_scalp.depth)

    if _scalp.order1 is not None and len(_scalp.order1.orders_history) > 0:
        report["leg1-order-updates"] = int(_scalp.order1.orders_history[0].update_requests_count)

        report["leg1-filled"] = float(_scalp.order1.orders_history[0].filled / _scalp.order1.orders_history[0].amount) if\
            _scalp.order1.orders_history[0].amount != 0.0 else None

        report["leg1-order-state"] = _scalp.order1.state
        report["leg1-order-status"] = _scalp.order1.status

    if _scalp.order2 is not None :
        report["leg2-order-state"] = _scalp.order2.state
        report["leg2-order-status"] = _scalp.order2.status
        report["leg2-filled"] = _scalp.order2.filled_dest_amount / _scalp.order2.best_dest_amount

        report["leg2-order1-updates"] = int(_scalp.order2.orders_history[0].update_requests_count) if \
            len(_scalp.order2.orders_history) > 0 else None

    _bot.log_report(report)
    _bot.save_csv_report(report, "{}.csv".format(_scalp.id))
    _bot.send_remote_report(report)

    # todo : report for order 2
    # report["leg2-order-updates"] = _scalp.order2.orders_history[0].update_requests_count if _scalp.order1 is not None
    #     else None

    return report


def report_order1_closed(_bot, _scalp):
    _bot.log(_bot.LOG_INFO, "Scalp ID: {}. Order 1 closed. Filled {} {}".format(_scalp.id, _scalp.order1.dest_currency,
                                                                                _scalp.order1.filled_dest_amount))


def report_order2_closed(_bot, _scalp):
    if _scalp.order2 is not None:
        _bot.log(_bot.LOG_INFO,
                 "Scalp ID: {}. Order 2 closed. Filled {} {}".format(_scalp.id, _scalp.order2.dest_currency,
                                                                     _scalp.order2.filled_dest_amount))
    else:
        _bot.log(_bot.LOG_INFO,
                 "Scalp ID: {}. Closed after Order 1.".format(_scalp.id))


bot = ScalpBot("", "scalp.log")

bot.set_from_cli(sys.argv[1:])  # cli parameters  override config
bot.load_config_from_file(bot.config_filename)  # config taken from cli or default

bot.init_exchange()

if bot.offline:
    bot.init_offline_mode()

bot.init_remote_reports()

bot.load_markets()

# init parameters
symbol = bot.symbol
start_currency = bot.start_currency
dest_currency = bot.dest_currency

start_amount = bot.start_amount
profit = bot.profit
commission = bot.commission

profit_with_fee = bot.target_single_order_profit(profit, commission)  # target profit considering commission
scalps_to_do = bot.scalps_to_do  # number of consecutive scalp runs

bot.run = 1  # current run
total_result = 0.0

ticker = bot.exchange.get_tickers(symbol)[symbol]

depth = 1

om = tkgcore.OwaManager(bot.exchange, bot.max_order_update_attempts, bot.max_order_update_attempts, bot.request_sleep)
# om.log = lambda x, y: x
om.log = bot.log  # override order manager logger to the bot logger
om.LOG_INFO = bot.LOG_INFO
om.LOG_ERROR = bot.LOG_ERROR
om.LOG_DEBUG = bot.LOG_DEBUG
om.LOG_CRITICAL = bot.LOG_CRITICAL

order1_side = tkgcore.core.get_order_type(start_currency, dest_currency, symbol)

if order1_side == "buy":
    start_price = ticker["bid"]*(1 - profit_with_fee*bot.first_order_price_margin_in_profits_with_fees
                                 - (depth-1)*bot.depth_step_in_profits*bot.profit)
elif order1_side == "sell":
    start_price = ticker["ask"] * (1 + profit_with_fee * bot.first_order_price_margin_in_profits_with_fees
                                   + (depth - 1) * bot.depth_step_in_profits*bot.profit)
else:
    bot.log(bot.LOG_ERROR, "Wrong symbol")
    sys.exit()

bot.log(bot.LOG_CRITICAL, "Init ticker:{}".format(start_price))

scalp = SingleScalp(symbol, start_currency, start_amount, depth,
                    start_price, dest_currency,
                    profit_with_fee, bot.commission, bot.order1_max_updates, bot.order2_max_updates_for_profit,
                    bot.order2_max_updates_market,
                    bot.cancel_threshold)

scalps = ScalpsCollection(bot.max_active_scalps)
# scalps.add_scalp(scalp)

scalps_added = 0
prev_ticker = None

tickers_hist = dict()
tickers_hist["ask"] = list()
tickers_hist["bid"] = list()

ticker_history_len = bot.ma_long_window + bot.ma_count

while True:
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "######################################################################################")
    bot.log(bot.LOG_INFO, "Run: {}/{}".format(bot.run, bot.max_runs))
    bot.log(bot.LOG_INFO, "Total active scalps: {} ".format(len(scalps.active_scalps)))
    bot.log(bot.LOG_INFO, "Scalps adeed: {}/{} ".format(scalps.scalps_order1_complete, bot.max_buy_orders_per_run))
    bot.log(bot.LOG_INFO, "Total result so far {}".format(total_result))

    scalps_in_oder1 = len(list(filter(lambda x: x.state == "order1", scalps.active_scalps.values())))
    scalps_in_oder2 = len(list(filter(lambda x: x.state == "order2", scalps.active_scalps.values())))

    bot.log(bot.LOG_INFO, "Total active orders: {}".format(len(om.get_open_orders())))
    bot.log(bot.LOG_INFO, "Scalps in order1:{} . Scalps in order2:{}".format(scalps_in_oder1, scalps_in_oder2))
    bot.log(bot.LOG_INFO, "######################################################################################")

    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")

    active_scalps = list(scalps.active_scalps.values())

    if bot.run > bot.max_runs and len(active_scalps) == 0:
        bot.log(bot.LOG_INFO, "Max runs reached {}/{} and no active scalps.".format(bot.run, bot.max_runs))
        break

    ticker = None
    ok_to_add_scapls = False

    # # request tickers if only going to add scalps:
    # if len(scalps.active_scalps) < scalps.max_scalps and bot.run <= bot.max_runs:

    try:
        bot.log(bot.LOG_INFO, "Getting ticker. Tickers collected {}/{}".format(len(tickers_hist["ask"]), bot.ma_long_window) )
        new_buy_order_price = None

        ticker = bot.exchange.get_tickers(symbol)[symbol]

    except Exception as e:
        bot.log(bot.LOG_ERROR, "Error while fetching tickers exchange_id:{} session_uuid:{}".
                format(bot.exchange_id, bot.session_uuid))

        bot.log(bot.LOG_ERROR, "Exception: {}".format(type(e).__name__))
        bot.log(bot.LOG_ERROR, "Exception body:", e.args)

    if ticker is not None and ticker["ask"] is not None \
            and ticker["bid"] is not None and ticker["ask"] > 0 and ticker["bid"] > 0:

        tickers_hist["ask"].append(ticker["ask"])
        tickers_hist["bid"].append(ticker["bid"])

        if (len(tickers_hist["ask"])) > ticker_history_len :
            tickers_hist["ask"] = tickers_hist["ask"][-ticker_history_len:]

        if (len(tickers_hist["bid"])) > ticker_history_len:
            tickers_hist["bid"] = tickers_hist["bid"][-ticker_history_len:]

    if len(tickers_hist["ask"]) < ticker_history_len:
        bot.log(bot.LOG_INFO, "Still collecting tickers {}/{}".format(len(tickers_hist["ask"]), ticker_history_len))
        continue

    else:
        bot.log(bot.LOG_INFO, "Collecting tickers done {}/{}".format(len(tickers_hist["ask"]), ticker_history_len))

        if order1_side == "buy":
            bot.log(bot.LOG_INFO, "Use ASK for MAs")
            ma_long = tkgcore.indicators.computeMA(tickers_hist["ask"], bot.ma_long_window)
            ma_short = tkgcore.indicators.computeMA(tickers_hist["ask"], bot.ma_short_window)
        else:
            bot.log(bot.LOG_INFO, "Use BID for MAs")
            ma_long = tkgcore.indicators.computeMA(tickers_hist["bid"], bot.ma_long_window)
            ma_short = tkgcore.indicators.computeMA(tickers_hist["bid"], bot.ma_short_window)

        bot.log(bot.LOG_INFO, "Last ma_long:{}".format(ma_long[-1:]))
        bot.log(bot.LOG_INFO, "Last ma_short:{}".format(ma_short[-1:]))

    ok_to_add_scapls = False

    ma_short_last = ma_short[-1:].item()
    ma_long_last = ma_long[-1:].item()

    if ma_short_last != 0:
        ma_short_long_rel_delta = (ma_short_last - ma_long_last) / ma_short_last
    else:
        ma_short_long_rel_delta = None

    if order1_side == "buy" and ma_short_long_rel_delta is not None \
            and ( ma_short_long_rel_delta > bot.ma_short_long_threshold):

        bot.log(bot.LOG_INFO, "Going to buy->sell. ma_short {} greater than ma_long{} more than threshold {}.".format(
            ma_short_last, ma_long_last, bot.ma_short_long_threshold))

        ok_to_add_scapls = True

    if order1_side == "sell" and ma_short_long_rel_delta is not None and  \
            (ma_short_long_rel_delta < bot.ma_short_long_threshold):

        bot.log(bot.LOG_INFO, "Going to sell->buy. ma_short less than ma_long less than rel. threshold {}.".format(
            ma_short_last, ma_long_last, bot.ma_short_long_threshold))

        ok_to_add_scapls = True

    if bot.offline:
        bot.log(bot.LOG_INFO, "Fetch_id {}".format(bot.exchange._offline_tickers_current_index-1))

    # create new scalp if  have not executed total amount of scalps
    if len(scalps.active_scalps) < scalps.max_scalps and bot.run <= bot.max_runs and ok_to_add_scapls:

        bot.log(bot.LOG_INFO, "Adding new scalp  ")

        if ticker is not None and ticker["ask"] is not None \
                and ticker["bid"] is not None and ticker["ask"] > 0 and ticker["bid"] > 0:

            depth_levels_to_add = scalps.missed_scalps_depth("order1", bot.max_active_scalps)

            for depth in depth_levels_to_add:

                if order1_side == "buy":
                    price = ticker["bid"]*(1 - profit_with_fee*bot.first_order_price_margin_in_profits_with_fees
                                           - (depth-1)*bot.depth_step_in_profits*bot.profit)
                else:
                    price = ticker["ask"] * (1 + profit_with_fee * bot.first_order_price_margin_in_profits_with_fees
                                   + (depth - 1) * bot.depth_step_in_profits*bot.profit)


                profit_with_fee_and_depth = profit_with_fee + bot.profit*bot.depth_step_in_profits*(depth-1)

                new_scalp = SingleScalp(symbol, start_currency, start_amount, depth, price, dest_currency,
                                        profit_with_fee_and_depth,
                                        bot.commission,
                                        bot.order1_max_updates,
                                        bot.order2_max_updates_for_profit,
                                        bot.order2_max_updates_market,
                                        bot.cancel_threshold
                                        )

                scalps.add_scalp(new_scalp)

    if scalps.scalps_order1_complete >= bot.max_active_scalps and bot.run <= bot.max_runs:
        bot.run += 1
        scalps.scalps_order1_complete = 0

    for scalp in active_scalps:
        bot.log(bot.LOG_INFO, "Proceed Scalp id: {}".format(scalp.id))

        order1_status = scalp.order1.status if scalp.order1 is not None else ""
        order2_status = scalp.order2.status if scalp.order2 is not None else ""

        scalp.update_state(order1_status, order2_status)

        log_scalp_status(bot, scalp)

        if scalp.state == "new":
            bot.log(bot.LOG_INFO, "Scalp ID: {}. Creating order 1".format(scalp.id))
            scalp.create_order1()
            om.add_order(scalp.order1)

        if scalp.state == "order1":
            pass
            # log_scalp_order(bot, scalp, scalp.order1)

        if scalp.state == "order1_complete":
            report_order1_closed(bot, scalp)
            bot.log(bot.LOG_INFO, "Scalp {}. Creating Order 2... ".format(scalp.id))
            scalp.create_order2()
            om.add_order(scalp.order2)

            scalps.scalps_order1_complete += 1
            scalps_added += 1

            # if scalps.scalps_added >= scalps.max_scalps-1:
            #     bot.run += 1
            #     scalps.scalps_added = 0

        if scalp.state == "order2":
            pass
            # log_scalp_order(bot, scalp, scalp.order2)

        if scalp.state == "closed":
            report_order2_closed(bot, scalp)
            report_close_scalp(bot, scalp)
            total_result += scalp.result_fact_diff

            scalps.remove_scalp(scalp.id)
            bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))

    if len(om.get_open_orders()) > 0:
        om.proceed_orders()
    time.sleep(bot.om_proceed_sleep)

bot.log(bot.LOG_INFO, "")
bot.log(bot.LOG_INFO, "")

bot.log(bot.LOG_INFO, "Total scalps added with order 1 complete {}".format(scalps_added))
bot.log(bot.LOG_INFO, "No more active scalps")
bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))
bot.log(bot.LOG_INFO, "Exiting...")

sys.exit(0)
