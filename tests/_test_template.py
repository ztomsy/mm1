# -*- coding: utf-8 -*-
# from . import context
from scalp_bot import ScalpBot
import unittest


class ScalpsBotTestSuite(unittest.TestCase):

    def test_target_profit(self):

        bot = ScalpBot("../_config_default.json")

        profit = 0.0005
        fee = 0.00075
        target_profit = bot.target_profit(profit, fee)

        # (45-45*fee)*(target_profit)*(1-fee) - (45-45*fee) = 45*profit )
        self.assertEqual(45*(1+profit), (45-45*fee)*(target_profit)*(1-fee))
        self.assertEqual(45.0225, 45*(1+profit))
        self.assertAlmostEqual(45.0901, 45 * target_profit, 4)  # 45.0901 target amount for order2


if __name__ == '__main__':
    unittest.main()
