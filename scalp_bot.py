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


class ScalpBot(tkgcore.Bot):

    def __init__(self, default_config: str, log_filename=None):
        super(ScalpBot, self).__init__(default_config, log_filename)

        self.report_fields = list(["scalp-id", "state", "result-fact-diff", "start-qty", "cur1", "cur2", "symbol",
                                   "leg1-order-state", "leg1-order-status", "leg1-order-updates", "leg1-filled",
                                   "leg2-order-state", "leg2-order-status","leg2-filled",
                                   "leg2-order1-updates"])

        self.om_proceed_sleep = 0.0
        self.symbol = ""
        self.start_currency = ""
        self.dest_currency = ""

        self.start_amount = 0.0
        self.profit = 0.0
        self.commission = 0.0

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
        commission_fee = self.profit if commission_fee is None else commission_fee

        #t_p = 2 - (((1 - commission_fee) ** 2) / (1 + target_profit))

        t_p = (1+target_profit) / ((1-commission_fee)**2) - 1

        # self.profit / ((1 - self.commission) ** 2)
        return t_p
