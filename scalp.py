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


class ScalpBot(tkgcore.Bot):

    def __init__(self, default_config: str, log_filename=None):
        super(ScalpBot, self).__init__(default_config, log_filename)

        self.report_fields = list(["scalp-id", "status", "result-fact-diff", "start-qty", "cur1", "cur2", "symbol",
                                   "leg1-order-updates", "leg1-filled"])

        self.om_proceed_sleep = 0.0
        self.symbol = ""
        self.start_currency = ""
        self.dest_currency = ""

        self.start_amount = 0.0
        self.profit = 0.0
        self.commission = 0.0

        self.total_result = 0.0
        self.max_active_scalps = 0  # maximum number of live active scalps
        self.scalps_to_do = 1  # number of consecutive scalp runs

        self.max_runs = 0
        self.run = 0  # current run

        self.om_proceed_sleep = 0.0  # sleep after orders proceed
        self.order1_max_updates = 0
        self.order2_max_updates_for_profit = 0
        self.order2_max_updates_market = 0
        self.cancel_threshold = 0.0

        self.offline_tickers_file = "test_data/tickers_many.csv"

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

    def target_profit(self):
        return self.profit / ((1 - self.commission) ** 2)


class SingleScalp(object):

    def __init__(self, symbol: str, start_currency: str, amount_start: float, start_price: float, dest_currency: str,
                 profit: float,
                 commission: float = 0.001,
                 order1_max_updates: int = 5,
                 order2_max_updates_for_profit: int = 50,
                 order2_max_updates_market: int = 5,
                 cancel_threshold: float = 0.0):

        self.symbol = symbol

        self.start_currency = start_currency
        self.start_amount = amount_start
        self.start_price = start_price

        self.dest_currency = dest_currency
        self.profit = profit

        self.commission = commission
        self.order1_max_updates = order1_max_updates
        self.order2_max_updates_for_profit = order2_max_updates_for_profit
        self.order2_max_updates_market = order2_max_updates_market

        self.cancel_threshold = cancel_threshold

        self.order1 = None  # type: FokOrder
        self.order2 = None  # type: RecoveryOrder

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
        order2_target_amount = self.order1.filled_start_amount * (1 + self.profit)

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
    def __init__(self, max_scalps: int = 1):
        self.max_scalps = max_scalps
        self.active_scalps = dict()  # type: Dict[str, SingleScalp]
        self.scalps_added = 0  # type: int

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


def log_scalp_status(_bot, _scalp):
    _bot.log(_bot.LOG_INFO, "######################################################################################")
    _bot.log(_bot.LOG_INFO, "Scalp ID: {}".format(_scalp.id))
    _bot.log(_bot.LOG_INFO,
             "State: {}. Order 1 status {} filled {}/{} (upd {}/{}). Order 2 status {} state {} filled {}/{} (upd "
             "{}/{}) ".
             format(_scalp.state,
                    _scalp.order1.status if _scalp.order1 is not None else None,
                    _scalp.order1.filled if _scalp.order1 is not None else None,
                    _scalp.order1.amount if _scalp.order1 is not None else None,
                    _scalp.order1.get_active_order().update_requests_count
                    if _scalp.order1 is not None and _scalp.order1.get_active_order() is not None else None,

                    _scalp.order1.max_order_updates if _scalp.order1 is not None else None,
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
    report["leg1-order-updates"] = int(
        _scalp.order1.orders_history[0].update_requests_count) if _scalp.order1 is not None \
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

profit_with_fee = bot.target_profit()  # target profit considering commission
scalps_to_do = bot.scalps_to_do  # number of consecutive scalp runs

run = 0  # current run
total_result = 0.0

ticker = bot.exchange.get_tickers(symbol)[symbol]

om = tkgcore.OwaManager(bot.exchange, bot.max_order_update_attempts, bot.max_order_update_attempts, bot.request_sleep)
om.log = lambda x, y: x

scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency, profit_with_fee)
scalps = ScalpsCollection(bot.max_active_scalps)
scalps.add_scalp(scalp)

while len(scalps.active_scalps) > 0:
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "")
    bot.log(bot.LOG_INFO, "######################################################################################")
    bot.log(bot.LOG_INFO, "Run: {}/{}".format(bot.run, bot.max_runs))
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

    if bot.run > bot.max_runs and active_scalps == 0:
        bot.log(bot.LOG_INFO, "Max runs reached {}/{} and no active scalps.".format(bot.run, bot.max_runs))
        break

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

            # create new scalp if  have not executed total amount of scalps
            if len(scalps.active_scalps) <= scalps.max_scalps and bot.run < bot.max_runs:
                bot.log(bot.LOG_INFO, "Adding new scalp after order1 is complete  ")
                bot.log(bot.LOG_INFO, "Fetching tickers...")
                ticker = bot.exchange.get_tickers(symbol)[symbol]
                new_scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency,
                                        profit_with_fee,
                                        bot.commission,
                                        bot.order1_max_updates,
                                        bot.order2_max_updates_for_profit,
                                        bot.order2_max_updates_market,
                                        bot.cancel_threshold
                                        )

                scalps.add_scalp(new_scalp)
                scalps.scalps_added += 1

            if scalps.scalps_added >= scalps.max_scalps-1:
                bot.run += 1
                # scalps.scalps_added = 0

        if scalp.state == "order2":
            pass
            # log_scalp_order(bot, scalp, scalp.order2)

        if scalp.state == "closed":
            report_order2_closed(bot, scalp)
            report_close_scalp(bot, scalp)
            total_result += scalp.result_fact_diff

            scalps.remove_scalp(scalp.id)
            bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))

            if len(scalps.active_scalps) <= scalps.max_scalps and bot.run < bot.max_runs:
                bot.log(bot.LOG_INFO, "Adding new scalp after order2 is complete  ")

                bot.log(bot.LOG_INFO, "Fetching tickers...")

                ticker = bot.exchange.get_tickers(symbol)[symbol]
                new_scalp = SingleScalp(symbol, start_currency, start_amount, ticker["bid"], dest_currency,
                                        profit_with_fee,
                                        bot.commission,
                                        bot.order1_max_updates,
                                        bot.order2_max_updates_for_profit,
                                        bot.order2_max_updates_market,
                                        bot.cancel_threshold
                                        )

                scalps.add_scalp(new_scalp)

            # else:

            if scalps.scalps_added >= scalps.max_scalps - 1:
                bot.run += 1
                # scalps.scalps_added = 0

        if len(om.get_open_orders()) > 0:
            om.proceed_orders()
            time.sleep(bot.om_proceed_sleep)

bot.log(bot.LOG_INFO, "")
bot.log(bot.LOG_INFO, "")
bot.log(bot.LOG_INFO, "No more active scalps")
bot.log(bot.LOG_INFO, "Total result from {}".format(total_result))
bot.log(bot.LOG_INFO, "Exiting...")

sys.exit(0)
