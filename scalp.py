
import tkgcore
from tkgcore import TradeOrder
from tkgcore import OrderWithAim
from tkgcore import RecoveryOrder
import uuid
import sys
import csv
import os
import time
from typing import Dict, Tuple, List
import copy

class FokOrder(OrderWithAim):
    """
    implement basic FOK order by limiting maximum trade order updates and than cancel
    """

    def _init(self):
        super()._init()
        self.state = "fok"  # just to make things a little pretty

    # redefine the _on_open_order checker to cancel active trade order if the number of order updates more
    # than max_order_updates
    def _on_open_order(self, active_trade_order: TradeOrder):
        if active_trade_order.update_requests_count >= self.max_order_updates \
                and active_trade_order.amount - active_trade_order.filled > self.cancel_threshold:
            return "cancel"
        return "hold"

    def new_scalp_from_ticker(self):
        ticker = bot.exchange.get_tickers(symbol)[symbol]
        new_scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency, profit_with_fee)
        return new_scalp
        scalps.add_scalp(new_scalp)


class ScalpBot(tkgcore.Bot):

    def __init__(self, default_config: str, log_filename=None ):
        super(ScalpBot, self).__init__(default_config, log_filename)

        self.report_fields = list(["scalp-id", "status", "result-fact-diff", "start-qty", "cur1", "cur2", "symbol",
                                   "leg1-order-updates", "leg1-filled"])


    def log_report(self, report):
        for r in self.report_fields:
            self.log(self.LOG_INFO, "{} = {}".format(r, report[r] if r in report else "None"))

    def save_csv_report(self, report: dict, filename: str = "report.csv"):
        write_header = False
        file_deals = "_{}/{}".format(self.exchange_id, filename)

        directory = os.path.dirname(file_deals)
        if not os.path.isdir(directory):
            os.mkdir(directory)

        if not os.path.isfile(file_deals):
            write_header = True

        with open(file_deals, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.report_fields, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerow(report)


class SingleScalp(object):
    cancel_threshold = 0
    commission = 0.0007
    order1_max_updates = 5
    order2_max_updates_for_profit = 50
    order2_max_updates_market = 5

    def __init__(self, symbol: str, start_currency: str, amount_start: float, start_price: float, dest_currency: str,
                 profit: float, order1: OrderWithAim = None, order2: RecoveryOrder = None):

        self.symbol = symbol

        self.start_currency = start_currency
        self.start_amount = amount_start
        self.start_price = start_price

        self.dest_currency = dest_currency

        self.profit = profit

        self.order1 = order1
        self.order2 = order2

        self.result_fact_diff = 0.0

        self.id = str(uuid.uuid4())
        self.state = "new"  # "order1","order1_complete", "order1_not_filled",  "order2", "closed"

    def create_order1(self):
        order1 = FokOrder.create_from_start_amount(self.symbol, self.start_currency, self.start_amount,
                                                   self.dest_currency, self.start_price, self.cancel_threshold,
                                                   self.order1_max_updates)
        self.order1 = order1
        self.state = "order1"

        return order1

    def create_order2(self):
        order2_target_amount = self.order1.filled_start_amount * (1+self.profit)

        order2 = RecoveryOrder(self.symbol, self.dest_currency, self.order1.filled_dest_amount, self.start_currency,
                               order2_target_amount, self.commission, self.cancel_threshold,
                               self.order2_max_updates_for_profit,
                               self.order2_max_updates_market)

        self.state = "order2"

        self.order2 = order2
        return order2

    def update_state(self, order1_status: str, order2_status: str):

        if self.state == "new" and order1_status == "open":
            self.state = "order1"
            return self.state

        if self.state == "order1" and order1_status == "closed" and self.order1.filled > 0:
            self.state = "order1_complete"
            return self.state

        if self.state == "order1" and order1_status == "closed" and self.order1.filled <= 0:
            self.state = "closed"
            self.result_fact_diff = 0
            return self.state

        if self.state == "order1_complete" and order2_status == "open":
            self.state = "order2"
            return self.state

        if self.state == "order2" and order2_status == "closed":
            self.state = "closed"
            self.result_fact_diff = self.order2.filled_dest_amount - self.order1.filled_start_amount
            return self.state


class ScalpsCollection(object):
    def __init__(self):
        self.max_scalps = 10
        self.active_scalps = dict()  # type: Dict[str, SingleScalp]

    def _report_scalp_add(self, scalp_id):
        print("Scalp ID: {} was added".format(scalp_id))

    def _report_scalp_removed(self, scalp_id):
        print("Scalp ID: {} was removed".format(scalp_id))

    def add_scalp(self, single_scalp: SingleScalp = None):
        self.active_scalps[single_scalp.id] = single_scalp
        self._report_scalp_add(single_scalp.id)

    def remove_scalp(self, scalp_id: str):
        self.active_scalps.pop(scalp_id)
        self._report_scalp_removed(scalp_id)


def log_status(_bot, _scalp):
    _bot.log(_bot.LOG_INFO, "######################################################################################")
    _bot.log(_bot.LOG_INFO, "Scalp ID: {}".format(_scalp.id))
    _bot.log(_bot.LOG_INFO,
            "State: {}. Order 1 status {} filled {}/{} (upd {}/{}). Order 2 status {} state {} filled {}/{} (upd "
            "{}/{}) ".
             format(_scalp.state,
                    _scalp.order1.filled,
                    _scalp.order1.status,
                    _scalp.order1.amount,
                    _scalp.order1.get_active_order().update_requests_count,
                    _scalp.order1.max_order_updates,
                    _scalp.order2.status,
                    _scalp.order2.state,
                    _scalp.order2.filled,
                    _scalp.order2.amount,
                    _scalp.order1.get_active_order().update_requests_count,
                    _scalp.order1.max_order_updates))

    _bot.log(_bot.LOG_INFO, "######################################################################################")


def log_scalp_order(_bot, _scalp,  _scalp_order: OrderWithAim):
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
    report["leg1-order-updates"] = int(_scalp.order1.orders_history[0].update_requests_count) if _scalp.order1 is not None \
        else None

    report["leg1-filled"] = float(_scalp.order1.orders_history[0].filled / _scalp.order1.orders_history[0].amount) if \
        _scalp.order1 is not None and _scalp.order1.orders_history[0].amount != 0.0 else None

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
        _bot.log(_bot.LOG_INFO, "Scalp ID: {}. Order 2 closed. Filled {} {}".format(_scalp.id, _scalp.order2.dest_currency,
                                                                                _scalp.order2.filled_dest_amount))
    else:
        _bot.log(_bot.LOG_INFO,
                 "Scalp ID: {}. Closed after Order 1.".format(_scalp.id))


symbol = "ETH/BTC"
start_currency = "BTC"
dest_currency = "ETH"

start_amount = 0.01
profit = 0.001
commission = 0.0007

profit_with_fee = profit / ((1 - commission) ** 2)  # target profit considering commission

bot = ScalpBot("_binance_test.json", "scalp.log")

bot.offline = True

total_result = 0.0
scalps_to_do = 1  # number of consecutive scalp runs
run = 1  # current run


# bot.init_logging()
bot.load_config_from_file(bot.config_filename)

bot.init_exchange()
if bot.offline:
    bot.log(bot.LOG_INFO, "Loading from offline test_data/markets.json test_data/tickers.csv")
    bot.exchange.set_offline_mode("test_data/markets.json", "test_data/tickers_many.csv")

bot.init_remote_reports()

bot.test_balance = 1
bot.start_currency = list(["BTC"])

balance = bot.load_balance()
bot.load_markets()

ticker = bot.exchange.get_tickers(symbol)[symbol]

# if bot.offline:
#     bot.fetch_tickers()
#     ticker = bot.tickers[symbol]
# else:
#     ticker = bot.exchange._ccxt.fetch_tickers(symbol)[symbol]

om = tkgcore.OwaManager(bot.exchange)

scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency, profit_with_fee)
scalps = ScalpsCollection()
scalps.add_scalp(scalp)


while len(scalps.active_scalps) > 0:
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "######################################################################################")
    bot.log(bot.LOG_INFO, "Total active scalps: {} ".format(len(scalps.active_scalps)))
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

    for scalp in active_scalps:
        bot.log(bot.LOG_INFO, "Proceed Scalp id: {}".format(scalp.id))

        order1_status = scalp.order1.status if scalp.order1 is not None else ""
        order2_status = scalp.order2.status if scalp.order2 is not None else ""

        scalp.update_state(order1_status, order2_status)

        if scalp.state == "new":

            bot.log(bot.LOG_INFO, "Scalp ID: {}. Creating order 1".format(scalp.id))
            scalp.create_order1()
            om.add_order(scalp.order1)

        if scalp.state == "order1":
            log_scalp_order(bot, scalp, scalp.order1)

        if scalp.state == "order1_complete":
            report_order1_closed(bot, scalp)
            bot.log(bot.LOG_INFO, "Scalp {}. Creating Order 2... ".format(scalp.id))
            scalp.create_order2()
            om.add_order(scalp.order2)

            # create new scalp if  have not executed total amount of scalps
            if len(scalps.active_scalps) < scalps.max_scalps:
                bot.log(bot.LOG_INFO, "Fetching tickers...")
                ticker = bot.exchange.get_tickers(symbol)[symbol]
                new_scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency, profit_with_fee)
                scalps.add_scalp(new_scalp)

        if scalp.state == "order2":
            log_scalp_order(bot, scalp, scalp.order2)

        if scalp.state == "closed":
            report_order2_closed(bot, scalp)
            report_close_scalp(bot, scalp)
            total_result += scalp.result_fact_diff

            scalps.remove_scalp(scalp.id)
            bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))

            run += 1
            # if run > scalps_to_do:
            #     break
            # create new scalp if  have not executed total amount of scalps
            if len(scalps.active_scalps) < scalps.max_scalps:
                bot.log(bot.LOG_INFO, "Fetching tickers...")

                ticker = bot.exchange.get_tickers(symbol)[symbol]
                new_scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency, profit_with_fee)
                scalps.add_scalp(new_scalp)

        if len(om.get_open_orders()) > 0:
            om.proceed_orders()
            time.sleep(0.01)




bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))
bot.log(bot.LOG_INFO, "Exiting...")

sys.exit(0)