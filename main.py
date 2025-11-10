#!/usr/bin/env python3
import threading
import webbrowser
from queue import Queue

from app_server import AppServer
from server.web_server import WebServer


def main():

    activity_queue = Queue()
    web = WebServer(activity_queue)
    app = AppServer(activity_queue)

    web_thread = threading.Thread(target=web.run, name="Webserver")
    app_thread = threading.Thread(target=app.startup, name="TradingEngine")
    web_thread.start()
    app_thread.start()

    # app.enable_backtest()
    # if signal_queue.get():
    #     app.enable_backtest()

    url = 'http://localhost:5555'
    webbrowser.open(url)
    pass


if __name__ == "__main__":
    main()
