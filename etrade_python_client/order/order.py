import json
import logging
from logging.handlers import RotatingFileHandler
import configparser
import random
import re

# loading configuration file
config = configparser.ConfigParser()
config.read('config.ini')

# logger settings
logger = logging.getLogger('my_logger')
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler("python_client.log", maxBytes=5 * 1024 * 1024, backupCount=3)
FORMAT = "%(asctime)-15s %(message)s"
fmt = logging.Formatter(FORMAT, datefmt='%m/%d/%Y %I:%M:%S %p')
handler.setFormatter(fmt)
logger.addHandler(handler)


class Order:

    def __init__(self, session, account, base_url):
        self.session = session
        self.account = account
        self.base_url = base_url

    def preview_order(self):
        """
        Call preview order API based on selecting from different given options

        :param self: Pass in authenticated session and information on selected account
        """


        # User's order selection
        order = self.user_select_order()

        # URL for the API endpoint
        url = self.base_url + "/v1/accounts/" + self.account["accountIdKey"] + "/orders/preview.json"

        # Add parameters and header information
        headers = {"Content-Type": "application/xml", "consumerKey": config["DEFAULT"]["CONSUMER_KEY"]}

        # Add payload for POST Request
        payload = """<PreviewOrderRequest>
                       <orderType>EQ</orderType>
                       <clientOrderId>{0}</clientOrderId>
                       <Order>
                           <allOrNone>false</allOrNone>
                           <priceType>{1}</priceType>
                           <orderTerm>{2}</orderTerm>
                           <marketSession>REGULAR</marketSession>
                           <stopPrice></stopPrice>
                           <limitPrice>{3}</limitPrice>
                           <Instrument>
                               <Product>
                                   <securityType>EQ</securityType>
                                   <symbol>{4}</symbol>
                               </Product>
                               <orderAction>{5}</orderAction>
                               <quantityType>QUANTITY</quantityType>
                               <quantity>{6}</quantity>
                           </Instrument>
                       </Order>
                   </PreviewOrderRequest>"""
        payload = payload.format(order["client_order_id"], order["price_type"], order["order_term"],
                                 order["limit_price"], order["symbol"], order["order_action"], order["quantity"])

        # Make API call for POST request
        response = self.session.post(url, header_auth=True, headers=headers, data=payload)
        logger.debug("Request Header: %s", response.request.headers)
        logger.debug("Request payload: %s", payload)

        # Handle and parse response
        if response is not None and response.status_code == 200:
            parsed = json.loads(response.text)
            logger.debug("Response Body: %s", json.dumps(parsed, indent=4, sort_keys=True))
            data = response.json()
            print("\nPreview Order:")

            if data is not None and "PreviewOrderResponse" in data and "PreviewIds" in data["PreviewOrderResponse"]:
                for previewids in data["PreviewOrderResponse"]["PreviewIds"]:
                    print("Preview ID: " + str(previewids["previewId"]))
            else:
                # Handle errors
                data = response.json()
                if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                    print("Error: " + data["Error"]["message"])
                else:
                    print("Error: Preview Order API service error")

            if data is not None and "PreviewOrderResponse" in data and "Order" in data["PreviewOrderResponse"]:
                for orders in data["PreviewOrderResponse"]["Order"]:
                    order["limitPrice"] = orders["limitPrice"]

                    if orders is not None and "Instrument" in orders:
                        for instrument in orders["Instrument"]:
                            if instrument is not None and "orderAction" in instrument:
                                print("Action: " + instrument["orderAction"])
                            if instrument is not None and "quantity" in instrument:
                                print("Quantity: " + str(instrument["quantity"]))
                            if instrument is not None and "Product" in instrument \
                                    and "symbol" in instrument["Product"]:
                                print("Symbol: " + instrument["Product"]["symbol"])
                            if instrument is not None and "symbolDescription" in instrument:
                                print("Description: " + str(instrument["symbolDescription"]))

                if orders is not None and "priceType" in orders and "limitPrice" in orders:
                    print("Price Type: " + orders["priceType"])
                    if orders["priceType"] == "MARKET":
                        print("Price: MKT")
                    else:
                        print("Price: " + str(orders["limitPrice"]))
                if orders is not None and "orderTerm" in orders:
                    print("Duration: " + orders["orderTerm"])
                if orders is not None and "estimatedCommission" in orders:
                    print("Estimated Commission: " + str(orders["estimatedCommission"]))
                if orders is not None and "estimatedTotalAmount" in orders:
                    print("Estimated Total Cost: " + str(orders["estimatedTotalAmount"]))
            else:
                # Handle errors
                data = response.json()
                if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                    print("Error: " + data["Error"]["message"])
                else:
                    print("Error: Preview Order API service error")
        else:
            # Handle errors
            data = response.json()
            if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                print("Error: " + data["Error"]["message"])
            else:
                print("Error: Preview Order API service error")

    def previous_order(self, session, account, prev_orders):
        """
        Calls preview order API based on a list of previous orders

        :param session: authenticated session
        :param account: information on selected account
        :param prev_orders: list of instruments from previous orders
        """

        if prev_orders is not None:
            while True:

                # Display previous instruments for user selection
                print("")
                count = 1
                for order in prev_orders:
                    print(str(count) + ")\tOrder Action: " + order["order_action"] + " | "
                          + "Security Type: " + str(order["security_type"]) + " | "
                          + "Term: " + str(order["order_term"]) + " | "
                          + "Quantity: " + str(order["quantity"]) + " | "
                          + "Symbol: " + order["symbol"] + " | "
                          + "Price Type: " + order["price_type"])
                    count = count + 1
                print(str(count) + ")\t" "Go Back")
                options_select = input("Please select an option: ")

                if options_select.isdigit() and 0 < int(options_select) < len(prev_orders) + 1:

                    # URL for the API endpoint
                    url = self.base_url + "/v1/accounts/" + account["accountIdKey"] + "/orders/preview.json"

                    # Add parameters and header information
                    headers = {"Content-Type": "application/xml", "consumerKey": config["DEFAULT"]["CONSUMER_KEY"]}

                    # Add payload for POST Request
                    payload = """<PreviewOrderRequest>
                                   <orderType>{0}</orderType>
                                   <clientOrderId>{1}</clientOrderId>
                                   <Order>
                                       <allOrNone>false</allOrNone>
                                       <priceType>{2}</priceType>  
                                       <orderTerm>{3}</orderTerm>   
                                       <marketSession>REGULAR</marketSession>
                                       <stopPrice></stopPrice>
                                       <limitPrice>{4}</limitPrice>
                                       <Instrument>
                                           <Product>
                                               <securityType>{5}</securityType>
                                               <symbol>{6}</symbol>
                                           </Product>
                                           <orderAction>{7}</orderAction> 
                                           <quantityType>QUANTITY</quantityType>
                                           <quantity>{8}</quantity>
                                       </Instrument>
                                   </Order>
                               </PreviewOrderRequest>"""

                    options_select = int(options_select)
                    prev_orders[options_select - 1]["client_order_id"] = str(random.randint(1000000000, 9999999999))
                    payload = payload.format(prev_orders[options_select - 1]["order_type"],
                                             prev_orders[options_select - 1]["client_order_id"],
                                             prev_orders[options_select - 1]["price_type"],
                                             prev_orders[options_select - 1]["order_term"],
                                             prev_orders[options_select - 1]["limitPrice"],
                                             prev_orders[options_select - 1]["security_type"],
                                             prev_orders[options_select - 1]["symbol"],
                                             prev_orders[options_select - 1]["order_action"],
                                             prev_orders[options_select - 1]["quantity"])

                    # Make API call for POST request
                    response = session.post(url, header_auth=True, headers=headers, data=payload)
                    logger.debug("Request Header: %s", response.request.headers)
                    logger.debug("Request payload: %s", payload)

                    # Handle and parse response
                    if response is not None and response.status_code == 200:
                        parsed = json.loads(response.text)
                        logger.debug("Response Body: %s", json.dumps(parsed, indent=4, sort_keys=True))
                        data = response.json()
                        print("\nPreview Order: ")
                        if data is not None and "PreviewOrderResponse" in data and "PreviewIds" in data["PreviewOrderResponse"]:
                            for previewids in data["PreviewOrderResponse"]["PreviewIds"]:
                                print("Preview ID: " + str(previewids["previewId"]))
                        else:
                            # Handle errors
                            data = response.json()
                            if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                                print("Error: " + data["Error"]["message"])
                            else:
                                print("Error: Preview Order API service error")

                        if data is not None and "PreviewOrderResponse" in data and "Order" in data[
                            "PreviewOrderResponse"]:
                            for orders in data["PreviewOrderResponse"]["Order"]:
                                prev_orders[options_select - 1]["limitPrice"] = orders["limitPrice"]

                                if orders is not None and "Instrument" in orders:
                                    for instruments in orders["Instrument"]:
                                        if instruments is not None and "orderAction" in instruments:
                                            print("Action: " + instruments["orderAction"])
                                        if instruments is not None and "quantity" in instruments:
                                            print("Quantity: " + str(instruments["quantity"]))
                                        if instruments is not None and "Product" in instruments \
                                                and "symbol" in instruments["Product"]:
                                            print("Symbol: " + instruments["Product"]["symbol"])
                                        if instruments is not None and "symbolDescription" in instruments:
                                            print("Description: " + str(instruments["symbolDescription"]))

                            if orders is not None and "priceType" in orders and "limitPrice" in orders:
                                print("Price Type: " + orders["priceType"])
                                if orders["priceType"] == "MARKET":
                                    print("Price: MKT")
                                else:
                                    print("Price: " + str(orders["limitPrice"]))
                            if orders is not None and "orderTerm" in orders:
                                print("Duration: " + orders["orderTerm"])
                            if orders is not None and "estimatedCommission" in orders:
                                print("Estimated Commission: " + str(orders["estimatedCommission"]))
                            if orders is not None and "estimatedTotalAmount" in orders:
                                print("Estimated Total Cost: " + str(orders["estimatedTotalAmount"]))
                        else:
                            # Handle errors
                            data = response.json()
                            if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                                print("Error: " + data["Error"]["message"])
                            else:
                                print("Error: Preview Order API service error")
                    else:
                        # Handle errors
                        data = response.json()
                        if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                            print("Error: " + data["Error"]["message"])
                        else:
                            print("Error: Preview Order API service error")
                    break
                elif options_select.isdigit() and int(options_select) == len(prev_orders) + 1:
                    break
                else:
                    print("Unknown Option Selected!")

    @staticmethod
    def print_orders(response, status):
        """
        Formats and displays a list of orders

        :param response: response object of a list of orders
        :param status: order status related to the response object
        :return a list of previous orders
        """
        prev_orders = []
        if response is not None and "OrdersResponse" in response and "Order" in response["OrdersResponse"]:
            for order in response["OrdersResponse"]["Order"]:
                if order is not None and "OrderDetail" in order:
                    for details in order["OrderDetail"]:
                        if details is not None and "Instrument" in details:
                            for instrument in details["Instrument"]:
                                order_str = ""
                                order_obj = {"price_type": None,
                                             "order_term": None,
                                             "order_indicator": None,
                                             "order_type": None,
                                             "security_type": None,
                                             "symbol": None,
                                             "order_action": None,
                                             "quantity": None}
                                if order is not None and 'orderType' in order:
                                    order_obj["order_type"] = order["orderType"]

                                if order is not None and 'orderId' in order:
                                    order_str += "Order #" + str(order["orderId"]) + " : "

                                if instrument is not None and 'Product' in instrument \
                                        and 'securityType' in instrument["Product"]:
                                    order_str += "Type: " + instrument["Product"]["securityType"] + " | "
                                    order_obj["security_type"] = instrument["Product"]["securityType"]

                                if instrument is not None and 'orderAction' in instrument:
                                    order_str += "Order Type: " + instrument["orderAction"] + " | "
                                    order_obj["order_action"] = instrument["orderAction"]

                                if instrument is not None and 'orderedQuantity' in instrument:
                                    order_str += "Quantity(Exec/Entered): " + str("{:,}".format(instrument["orderedQuantity"])) + " | "
                                    order_obj["quantity"] = instrument["orderedQuantity"]

                                if instrument is not None and 'Product' in instrument and 'symbol' in instrument["Product"]:
                                    order_str += "Symbol: " + instrument["Product"]["symbol"] + " | "
                                    order_obj["symbol"] = instrument["Product"]["symbol"]

                                if details is not None and 'priceType' in details:
                                    order_str += "Price Type: " + details["priceType"] + " | "
                                    order_obj["price_type"] = details["priceType"]

                                if details is not None and 'orderTerm' in details:
                                    order_str += "Term: " + details["orderTerm"] + " | "
                                    order_obj["order_term"] = details["orderTerm"]

                                if details is not None and 'limitPrice' in details:
                                    order_str += "Price: " + str('${:,.2f}'.format(details["limitPrice"])) + " | "
                                    order_obj["limitPrice"] = details["limitPrice"]

                                if status == "Open" and details is not None and 'netBid' in details:
                                    order_str += "Bid: " + details["netBid"] + " | "
                                    order_obj["bid"] = details["netBid"]

                                if status == "Open" and details is not None and 'netAsk' in details:
                                    order_str += "Ask: " + details["netAsk"] + " | "
                                    order_obj["ask"] = details["netAsk"]

                                if status == "Open" and details is not None and 'netPrice' in details:
                                    order_str += "Last Price: " + details["netPrice"] + " | "
                                    order_obj["netPrice"] = details["netPrice"]

                                if status == "indiv_fills" and instrument is not None and 'filledQuantity' in instrument:
                                    order_str += "Quantity Executed: " + str("{:,}".format(instrument["filledQuantity"])) + " | "
                                    order_obj["quantity"] = instrument["filledQuantity"]

                                if status != "open" and status != "expired" and status != "rejected" and instrument is not None \
                                        and "averageExecutionPrice" in instrument:
                                    order_str += "Price Executed: " + str('${:,.2f}'.format(instrument["averageExecutionPrice"])) + " | "

                                if status != "expired" and status != "rejected" and details is not None and 'status' in details:
                                    order_str += "Status: " + details["status"]

                                print(order_str)
                                prev_orders.append(order_obj)
        return prev_orders

    @staticmethod
    def options_selection(options):
        """
        Formats and displays different options in a menu

        :param options: List of options to display
        :return the number user selected
        """
        while True:
            print("")
            for num, price_type in enumerate(options, start=1):
                print("{})\t{}".format(num, price_type))
            options_select = input("Please select an option: ")
            if options_select.isdigit() and 0 < int(options_select) < len(options) + 1:
                return options_select
            else:
                print("Unknown Option Selected!")

    def user_select_order(self):
        """
            Provides users options to select to preview orders
            :param self test
            :return user's order selections
            """
        order = {"price_type": "",
                 "order_term": "",
                 "symbol": "",
                 "order_action": "",
                 "limit_price":"",
                 "quantity": ""}

        price_type_options = ["MARKET", "LIMIT"]
        order_term_options = ["GOOD_FOR_DAY", "IMMEDIATE_OR_CANCEL", "FILL_OR_KILL"]
        order_action_options = ["BUY", "SELL", "BUY_TO_COVER", "SELL_SHORT"]

        print("\nPrice Type:")
        order["price_type"] = price_type_options[int(self.options_selection(price_type_options)) - 1]

        if order["price_type"] == "MARKET":
            order["order_term"] = "GOOD_FOR_DAY"
        else:
            print("\nOrder Term:")
            order["order_term"] = order_term_options[int(self.options_selection(order_term_options)) - 1]

        order["limit_price"] = None
        if order["price_type"] == "LIMIT":
            while order["limit_price"] is None or not order["limit_price"].isdigit() \
                    and not re.match(r'\d+(?:[.]\d{2})?$', order["limit_price"]):
                order["limit_price"] = input("\nPlease input limit price: ")

        order["client_order_id"] = random.randint(1000000000, 9999999999)

        while order["symbol"] == "":
            order["symbol"] = input("\nPlease enter a stock symbol :")

        print("\nOrder Action Type:")
        order["order_action"] = order_action_options[int(self.options_selection(order_action_options)) - 1]

        while not order["quantity"].isdigit():
            order["quantity"] = input("\nPlease type quantity:")

        return order

    def preview_order_menu(self, session, account, prev_orders):
        """
        Provides the different options for preview orders: select new order or select from previous order

        :param session: authenticated session
        :param account: information on selected account
        :param prev_orders: list of instruments from previous orders
        """
        menu_list = {"1": "Select New Order",
                     "2": "Select From Previous Orders",
                     "3": "Go Back"}

        while True:
            print("")
            options = menu_list.keys()
            for entry in options:
                print(entry + ")\t" + menu_list[entry])

            selection = input("Please select an option: ")
            if selection == "1":
                print("\nPreview Order: ")
                self.preview_order()
                break
            elif selection == "2":
                self.previous_order(session, account, prev_orders)
                break
            elif selection == "3":
                break
            else:
                print("Unknown Option Selected!")

    def cancel_order(self):
        """
        Calls cancel order API to cancel an existing order
        :param self: Pass parameter with authenticated session and information on selected account
        """
        while True:
            # Display a list of Open Orders
            # URL for the API endpoint
            url = self.base_url + "/v1/accounts/" + self.account["accountIdKey"] + "/orders.json"

            # Add parameters and header information
            params_open = {"status": "OPEN"}
            headers = {"consumerkey": config["DEFAULT"]["CONSUMER_KEY"]}

            # Make API call for GET request
            response_open = self.session.get(url, header_auth=True, params=params_open, headers=headers)

            logger.debug("Request Header: %s", response_open.request.headers)
            logger.debug("Response Body: %s", response_open.text)

            print("\nOpen Orders: ")
            # Handle and parse response
            if response_open.status_code == 204:
                logger.debug(response_open)
                print("None")
                menu_items = {"1": "Go Back"}
                while True:
                    print("")
                    options = menu_items.keys()
                    for entry in options:
                        print(entry + ")\t" + menu_items[entry])

                    selection = input("Please select an option: ")
                    if selection == "1":
                        break
                    else:
                        print("Unknown Option Selected!")
                break
            elif response_open.status_code == 200:
                parsed = json.loads(response_open.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_open.json()

                order_list = []
                count = 1
                if data is not None and "OrdersResponse" in data and "Order" in data["OrdersResponse"]:
                    for order in data["OrdersResponse"]["Order"]:
                        if order is not None and "OrderDetail" in order:
                            for details in order["OrderDetail"]:
                                if details is not None and "Instrument" in details:
                                    for instrument in details["Instrument"]:
                                        order_str = ""
                                        order_obj = {"price_type": None,
                                                     "order_term": None,
                                                     "order_indicator": None,
                                                     "order_type": None,
                                                     "security_type": None,
                                                     "symbol": None,
                                                     "order_action": None,
                                                     "quantity": None}
                                        if order is not None and 'orderType' in order:
                                            order_obj["order_type"] = order["orderType"]

                                        if order is not None and 'orderId' in order:
                                            order_str += "Order #" + str(order["orderId"]) + " : "
                                        if instrument is not None and 'Product' in instrument and 'securityType' \
                                                in instrument["Product"]:
                                            order_str += "Type: " + instrument["Product"]["securityType"] + " | "
                                            order_obj["security_type"] = instrument["Product"]["securityType"]

                                        if instrument is not None and 'orderAction' in instrument:
                                            order_str += "Order Type: " + instrument["orderAction"] + " | "
                                            order_obj["order_action"] = instrument["orderAction"]

                                        if instrument is not None and 'orderedQuantity' in instrument:
                                            order_str += "Quantity(Exec/Entered): " + str(
                                                "{:,}".format(instrument["orderedQuantity"])) + " | "
                                            order_obj["quantity"] = instrument["orderedQuantity"]

                                        if instrument is not None and 'Product' in instrument and 'symbol' \
                                                in instrument["Product"]:
                                            order_str += "Symbol: " + instrument["Product"]["symbol"] + " | "
                                            order_obj["symbol"] = instrument["Product"]["symbol"]

                                        if details is not None and 'priceType' in details:
                                            order_str += "Price Type: " + details["priceType"] + " | "
                                            order_obj["price_type"] = details["priceType"]

                                        if details is not None and 'orderTerm' in details:
                                            order_str += "Term: " + details["orderTerm"] + " | "
                                            order_obj["order_term"] = details["orderTerm"]

                                        if details is not None and 'limitPrice' in details:
                                            order_str += "Price: " + str(
                                                '${:,.2f}'.format(details["limitPrice"])) + " | "
                                            order_obj["limitPrice"] = details["limitPrice"]

                                        if instrument is not None and 'filledQuantity' in instrument:
                                            order_str += "Quantity Executed: " \
                                                         + str("{:,}".format(instrument["filledQuantity"])) + " | "
                                            order_obj["quantity"] = instrument["filledQuantity"]

                                        if instrument is not None and "averageExecutionPrice" in instrument:
                                            order_str += "Price Executed: " + str(
                                                '${:,.2f}'.format(instrument["averageExecutionPrice"])) + " | "

                                        if details is not None and 'status' in details:
                                            order_str += "Status: " + details["status"]

                                        print(str(count) + ")\t" + order_str)
                                        count = 1 + count
                                        order_list.append(order["orderId"])

                    print(str(count) + ")\tGo Back")
                    selection = input("Please select an option: ")
                    if selection.isdigit() and 0 < int(selection) < len(order_list) + 1:
                        # URL for the API endpoint
                        url = self.base_url + "/v1/accounts/" + self.account["accountIdKey"] + "/orders/cancel.json"

                        # Add parameters and header information
                        headers = {"Content-Type": "application/xml", "consumerKey": config["DEFAULT"]["CONSUMER_KEY"]}

                        # Add payload for POST Request
                        payload = """<CancelOrderRequest>
                                        <orderId>{0}</orderId>
                                    </CancelOrderRequest>
                                   """
                        payload = payload.format(order_list[int(selection) - 1])

                        # Add payload for PUT Request
                        response = self.session.put(url, header_auth=True, headers=headers, data=payload)
                        logger.debug("Request Header: %s", response.request.headers)
                        logger.debug("Request payload: %s", payload)

                        # Handle and parse response
                        if response is not None and response.status_code == 200:
                            parsed = json.loads(response.text)
                            logger.debug("Response Body: %s", json.dumps(parsed, indent=4, sort_keys=True))
                            data = response.json()
                            if data is not None and "CancelOrderResponse" in data \
                                    and "orderId" in data["CancelOrderResponse"]:
                                print("\nOrder number #" + str(
                                    data["CancelOrderResponse"]["orderId"]) + " successfully Cancelled.")
                            else:
                                # Handle errors
                                logger.debug("Response Headers: %s", response.headers)
                                logger.debug("Response Body: %s", response.text)
                                data = response.json()
                                if 'Error' in data and 'message' in data["Error"] \
                                        and data["Error"]["message"] is not None:
                                    print("Error: " + data["Error"]["message"])
                                else:
                                    print("Error: Cancel Order API service error")
                        else:
                            # Handle errors
                            logger.debug("Response Headers: %s", response.headers)
                            logger.debug("Response Body: %s", response.text)
                            data = response.json()
                            if 'Error' in data and 'message' in data["Error"] and data["Error"]["message"] is not None:
                                print("Error: " + data["Error"]["message"])
                            else:
                                print("Error: Cancel Order API service error")
                        break

                    elif selection.isdigit() and int(selection) == len(order_list) + 1:
                        break
                    else:
                        print("Unknown Option Selected!")
                else:
                    # Handle errors
                    logger.debug("Response Body: %s", response_open.text)
                    if response_open is not None and response_open.headers['Content-Type'] == 'application/json' \
                            and "Error" in response_open.json() and "message" in response_open.json()["Error"] \
                            and response_open.json()["Error"]["message"] is not None:
                        print("Error: " + response_open.json()["Error"]["message"])
                    else:
                        print("Error: Balance API service error")
                    break
            else:
                # Handle errors
                logger.debug("Response Body: %s", response_open.text)
                if response_open is not None and response_open.headers['Content-Type'] == 'application/json' \
                        and "Error" in response_open.json() and "message" in response_open.json()["Error"] \
                        and response_open.json()["Error"]["message"] is not None:
                    print("Error: " + response_open.json()["Error"]["message"])
                else:
                    print("Error: Balance API service error")
                break

    def view_orders(self):
        """
        Calls orders API to provide the details for the orders

        :param self: Pass in authenticated session and information on selected account
        """
        while True:
            # URL for the API endpoint
            url = self.base_url + "/v1/accounts/" + self.account["accountIdKey"] + "/orders.json"

            # Add parameters and header information
            headers = {"consumerkey": config["DEFAULT"]["CONSUMER_KEY"]}
            params_open = {"status": "OPEN"}
            params_executed = {"status": "EXECUTED"}
            params_indiv_fills = {"status": "INDIVIDUAL_FILLS"}
            params_cancelled = {"status": "CANCELLED"}
            params_rejected = {"status": "REJECTED"}
            params_expired = {"status": "EXPIRED"}

            # Make API call for GET request
            response_open = self.session.get(url, header_auth=True, params=params_open, headers=headers)
            response_executed = self.session.get(url, header_auth=True, params=params_executed, headers=headers)
            response_indiv_fills = self.session.get(url, header_auth=True, params=params_indiv_fills, headers=headers)
            response_cancelled = self.session.get(url, header_auth=True, params=params_cancelled, headers=headers)
            response_rejected = self.session.get(url, header_auth=True, params=params_rejected, headers=headers)
            response_expired = self.session.get(url, header_auth=True, params=params_expired, headers=headers)

            prev_orders = []

            # Open orders
            logger.debug("Request Header: %s", response_open.request.headers)
            logger.debug("Response Body: %s", response_open.text)

            print("\nOpen Orders:")
            # Handle and parse response
            if response_open.status_code == 204:
                logger.debug(response_open)
                print("None")
            elif response_open.status_code == 200:
                parsed = json.loads(response_open.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_open.json()

                # Display list of open orders
                prev_orders.extend(self.print_orders(data, "open"))

            # Executed orders
            logger.debug("Request Header: %s", response_executed.request.headers)
            logger.debug("Response Body: %s", response_executed.text)
            logger.debug(response_executed.text)

            print("\nExecuted Orders:")
            # Handle and parse response
            if response_executed.status_code == 204:
                logger.debug(response_executed)
                print("None")
            elif response_executed.status_code == 200:
                parsed = json.loads(response_executed.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_executed.json()

                # Display list of executed orders
                prev_orders.extend(self.print_orders(data, "executed"))

            # Individual fills orders
            logger.debug("Request Header: %s", response_indiv_fills.request.headers)
            logger.debug("Response Body: %s", response_indiv_fills.text)

            print("\nIndividual Fills Orders:")
            # Handle and parse response
            if response_indiv_fills.status_code == 204:
                logger.debug("Response Body: %s", response_indiv_fills)
                print("None")
            elif response_indiv_fills.status_code == 200:
                parsed = json.loads(response_indiv_fills.text)
                logger.debug("Response Body: %s", json.dumps(parsed, indent=4, sort_keys=True))
                data = response_indiv_fills.json()

                # Display list of individual fills orders
                prev_orders.extend(self.print_orders(data, "indiv_fills"))

            # Cancelled orders
            logger.debug("Request Header: %s", response_cancelled.request.headers)
            logger.debug("Response Body: %s", response_cancelled.text)

            print("\nCancelled Orders:")
            # Handle and parse response
            if response_cancelled.status_code == 204:
                logger.debug(response_cancelled)
                print("None")
            elif response_cancelled.status_code == 200:
                parsed = json.loads(response_cancelled.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_cancelled.json()

                # Display list of open orders
                prev_orders.extend(self.print_orders(data, "cancelled"))

            # Rejected orders
            logger.debug("Request Header: %s", response_rejected.request.headers)
            logger.debug("Response Body: %s", response_rejected.text)

            print("\nRejected Orders:")
            # Handle and parse response
            if response_rejected.status_code == 204:
                logger.debug(response_rejected)
                print("None")
            elif response_rejected.status_code == 200:
                parsed = json.loads(response_rejected.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_rejected.json()

                # Display list of open orders
                prev_orders.extend(self.print_orders(data, "rejected"))

            # Expired orders
            print("\nExpired Orders:")
            # Handle and parse response
            if response_expired.status_code == 204:
                logger.debug(response_executed)
                print("None")
            elif response_expired.status_code == 200:
                parsed = json.loads(response_expired.text)
                logger.debug(json.dumps(parsed, indent=4, sort_keys=True))
                data = response_expired.json()

                # Display list of open orders
                prev_orders.extend(self.print_orders(data, "expired"))

            menu_list = {"1": "Preview Order",
                         "2": "Cancel Order",
                         "3": "Go Back"}

            print("")
            options = menu_list.keys()
            for entry in options:
                print(entry + ")\t" + menu_list[entry])

            selection = input("Please select an option: ")
            if selection == "1":
                self.preview_order_menu(self.session, self.account, prev_orders)
            elif selection == "2":
                self.cancel_order()
            elif selection == "3":
                break
            else:
                print("Unknown Option Selected!")
