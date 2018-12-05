# -*- coding: utf-8 -*-
# from . import context
from .context import scalp_bot
from scalp_bot import ScalpBot, ScalpsCollection, SingleScalp
import unittest


class ScalpsBotTestSuite(unittest.TestCase):

    def test_target_amount(self):

        bot = ScalpBot("../_config_default.json")

        profit = 0.0005
        fee = 0.00075
        target_profit = bot.target_single_order_profit(profit, fee)

        # (45-45*fee)*(target_profit)*(1-fee) - (45-45*fee) = 45*profit )
        self.assertEqual(45*(1+profit), (45-45*fee)*(target_profit+1)*(1-fee))
        self.assertEqual(45.0225, 45*(1+profit))
        self.assertAlmostEqual(45.0901, 45 * (target_profit+1), 4)  # 45.0901 target amount for order2

    def test_depth_list(self):

        scalps = ScalpsCollection(10)

        depth_list = scalps.depth_list("order1")
        self.assertEqual(depth_list, [])

        ticker = 1

        for i in range(1, 11):
            scalp = SingleScalp("BTC/USDT", "USDT", 1, i, ticker*i, "BTC", 0.001)
            scalp.state = "order1"
            scalps.add_scalp(scalp)

        depth_list = scalps.depth_list("order1")

        self.assertEqual(depth_list, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        scalps = ScalpsCollection(10)
        for i in range(1, 11):
            scalp = SingleScalp("BTC/USDT", "USDT", 1, i, ticker*i, "BTC", 0.001)
            if i < 5:
                scalp.state = "order2"
            else:
                scalp.state = "order1"

            scalps.add_scalp(scalp)

        depth_list = scalps.depth_list("order1")
        self.assertEqual(depth_list, [5,  6,  7,  8,  9, 10])

        max_scalps = 15

        missed_scalps = scalps.missed_scalps_depth("order1", max_scalps)
        self.assertEqual(5, len(missed_scalps))
        self.assertListEqual([1, 2, 3, 4, 11], missed_scalps)





if __name__ == '__main__':
    unittest.main()
