#!/usr/bin/env python3
import webbrowser
from queue import Queue

from app_server import AppServer


def main():
    signal_queue = Queue()
    app = AppServer()
    # app.enable_backtest()
    # if signal_queue.get():
    #     app.enable_backtest()

    url = 'https://localhost:8000'
    webbrowser.open(url)
    pass


if __name__ == "__main__":
    main()
