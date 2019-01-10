import tkgcore
from tkgcore import TradeOrder
from tkgcore import OrderWithAim
from tkgcore import RecoveryOrder, FokOrder
import uuid
import sys
import csv
import os
import time
from typing import Dict, Tuple, List
import copy


class SingleScalp(object):

    def __init__(self, symbol: str, start_currency: str, amount_start: float, depth: int, start_price: float, dest_currency: str,
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

        self.depth = depth
        self.price_step_incremental_per_depth = 0.0

        self.commission = commission
        self.order1_max_updates = order1_max_updates
        self.order2_max_updates_for_profit = order2_max_updates_for_profit
        self.order2_max_updates_market = order2_max_updates_market

        self.cancel_threshold = cancel_threshold

        self.order1 = None  # type: FokOrder
        self.order2 = None  # type: FokOrder

        self.result_fact_diff = 0.0

        self.cur1_diff = 0.0
        self.cur2_diff = 0.0

        self.id = str(uuid.uuid4())
        self.state = "new"  # "order1","order1_complete", "order1_not_filled",  "order2", "closed"

        self.supplementary = dict()  # for stats and additional data

    def create_order1(self):
        order1 = FokOrder.create_from_start_amount(self.symbol, self.start_currency, self.start_amount,
                                                   self.dest_currency, self.start_price, self.cancel_threshold,
                                                   self.order1_max_updates)
        self.order1 = order1
        self.state = "order1"

        return order1

    def create_order2(self):
        order2_target_amount = self.order1.filled_start_amount * (1 + self.profit)

        order2_side = tkgcore.core.get_trade_direction_to_currency(self.symbol, self.start_currency)

        order2_price = 0.0

        if order2_side == "buy":
            order2_price = self.order1.filled_dest_amount / order2_target_amount

        elif order2_side == "sell":
            order2_price = order2_target_amount / self.order1.filled_dest_amount


        # order2 = RecoveryOrder(self.symbol, self.dest_currency, self.order1.filled_dest_amount, self.start_currency,
        #                        order2_target_amount, self.commission, self.cancel_threshold,
        #                        self.order2_max_updates_for_profit,
        #                        self.order2_max_updates_market)

        order2 = FokOrder.create_from_start_amount(self.symbol, self.dest_currency, self.order1.filled_dest_amount,
                                                   self.start_currency, order2_price, self.cancel_threshold,
                                                   self.order2_max_updates_for_profit)

        self.state = "order2"

        self.order2 = order2
        return order2

    def update_state(self, order1_status: str, order2_status: str):

        if self.state == "new" and order1_status == "open":
            self.state = "order1"
            return self.state

        if self.state == "order1" and order1_status == "closed" and self.order1.filled > 0:
            self.state = "order1_complete"
            self.cur1_diff = -self.order1.filled_start_amount
            self.cur2_diff = self.order1.filled_dest_amount
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

            self.cur1_diff += self.order2.filled_dest_amount
            self.cur2_diff -= self.order2.filled_start_amount

            return self.state


class ScalpsCollection(object):
    def __init__(self, max_scalps: int = 1):
        self.max_scalps = max_scalps
        self.active_scalps = dict()  # type: Dict[str, SingleScalp]
        self.scalps_order1_complete = 0  # type: int

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

    def depth_list(self, state: str):
        """
        return list of depth of active scalps in state "state"
        :type state: str
        :return: list
        """
        return sorted([k.depth for k in self.active_scalps.values() if k.state == state or k.state == "new"])

    def missed_scalps_depth(self, state: str, max_active_scalps: int):
        """
        returns list of missed depth levels for scalps in <state>
        :param state:
        :param max_active_scalps:
        :return:
        """
        missed_scalps = list()
        scalps_should_be = range(1, max_active_scalps + 1)

        scalps_to_add = max_active_scalps - len(self.active_scalps)

        if scalps_to_add > 0:
            present_depths = self.depth_list(state)

            for i in scalps_should_be:
                if i not in present_depths:
                    missed_scalps.append(i)

                    if len(missed_scalps) >= scalps_to_add:
                        return missed_scalps
        return missed_scalps


class ScalpBot(tkgcore.Bot):

    def __init__(self, default_config: str, log_filename=None):
        super(ScalpBot, self).__init__(default_config, log_filename)

        self.report_fields = list(["scalp-id", "state", "result-fact-diff", "start-qty", "cur1", "cur2", "symbol",
                                   "depth", "order1_side", "ticker_price",
                                   "ma_short_window", "ma_long_window", "ma_short_long_threshold",
                                   "ma_short", "ma_long", "ma_short_long_rel_delta",
                                   "time_created_utc",
                                   "leg1-order-state", "leg1-order-status", "leg1-order-updates", "leg1-filled",
                                   "leg2-order-state", "leg2-order-status","leg2-filled",
                                   "leg2-order1-updates", "cur1-diff", "cur2-diff"])

        self.om_proceed_sleep = 0.0
        self.symbol = ""
        self.start_currency = ""
        self.dest_currency = ""

        self.start_amount = 0.0
        self.profit = 0.0
        self.commission = 0.0
        self.depth_step_in_profits = 0.0
        self.first_order_price_margin_in_profits_with_fees = 0.0

        self.ma_long_window = 0  # length of ma long window
        self.ma_short_window = 0
        self.ma_count = 0
        self.ma_short_long_threshold = 0.0 # threshhold

        self.total_result = 0.0
        self.max_active_scalps = 0  # maximum number of live active scalps
        self.max_buy_orders_per_run = 0

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

    def target_single_order_profit(self, target_profit: float = None, commission_fee: float = None):

        target_profit = self.profit if target_profit is None else target_profit
        commission_fee = self.commission if commission_fee is None else commission_fee

        #t_p = 2 - (((1 - commission_fee) ** 2) / (1 + target_profit))

        t_p = (1+target_profit) / ((1-commission_fee)**2) - 1

        # self.profit / ((1 - self.commission) ** 2)
        return t_p
