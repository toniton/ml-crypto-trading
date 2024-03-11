from queue import Queue
from socket import socket, gethostbyname, AF_INET, SOCK_DGRAM

import joblib

from application import Application
from backtest_handler import BacktestHandler

PORT_NUMBER = 6200
SIZE = 4000


class AppServer:
    def __init__(self):
        self.s = socket(AF_INET, SOCK_DGRAM)
        self.app = Application()
        self.app.startup()

    def enable_backtest(self):
        self.s.bind((gethostbyname('0.0.0.0'), PORT_NUMBER))
        while True:
            pro_data = joblib.load(self.s.makefile("rbw"))
            BacktestHandler(self.app, pro_data).register_action()
            print(pro_data)

    def stop_backtest(self):
        self.s.shutdown(0)
