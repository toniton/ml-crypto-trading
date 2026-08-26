import threading

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class OrderReconciler(ApplicationLoggingMixin):
    RECONCILE_INTERVAL_SECONDS = 60.0

    def __init__(self, order_manager):
        self._order_manager = order_manager
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="OrderReconciler")
        self._thread.start()
        self.app_logger.info("Order reconciler started")

    def stop(self):
        self._stop_event.set()
        self._trigger_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.RECONCILE_INTERVAL_SECONDS + 5)
        self.app_logger.info("Order reconciler stopped")

    def trigger(self):
        self._trigger_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            self._trigger_event.wait(timeout=self.RECONCILE_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            self._trigger_event.clear()
            try:
                self._order_manager.reconcile_pending_orders()
            except Exception as exc:
                self.app_logger.warning(f"Reconciliation cycle failed: {exc}")
        self.app_logger.info("Order reconciler thread exiting")
