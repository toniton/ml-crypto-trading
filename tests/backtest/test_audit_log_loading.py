from decimal import Decimal
import pytest
from backtest.backtest_data_loader import BacktestDataLoader


class TestAuditLogDataLoader:
    @pytest.fixture
    def audit_log_dir(self, tmp_path):
        d = tmp_path / "audit_logs"
        d.mkdir()

        # Create a mock audit log file BTC_USD.log
        # timestamp,asset,event_type,action,price,quantity,volume,high_price,low_price,close_price
        content = """timestamp,asset,event_type,action,price,quantity,volume,high_price,low_price,close_price
1704067200000,BTC_USD,market_data,none,,,"1000.0","50100.0","49900.0","50000.0"
1704070800000,BTC_USD,market_data,none,,,"1100.0","51100.0","50900.0","51000.0"
"""
        p = d / "audit-BTC_USD.log"
        p.write_text(content)

        # Also one with dated filename
        content_eth = """timestamp,asset,event_type,action,price,quantity,volume,high_price,low_price,close_price
1704067200000,ETH_USD,market_data,none,,,"100.0","2510.0","2490.0","2500.0"
"""
        p_eth = d / "audit-ETH_USD-2024-01.log"
        p_eth.write_text(content_eth)

        return str(d)

    def test_load_audit_log(self, audit_log_dir):
        loader = BacktestDataLoader(audit_log_dir)

        # Test loading audit-BTC_USD.log
        data = loader.load("BTC_USD")
        assert len(data) == 2
        assert data[0].close_price == Decimal("50000.0")
        assert data[0].timestamp == 1704067200  # ms to s
        assert data[1].close_price == Decimal("51000.0")

    def test_load_dated_audit_log(self, audit_log_dir):
        loader = BacktestDataLoader(audit_log_dir)

        # Test loading audit-ETH_USD-2024-01.log via glob
        data = loader.load("ETH_USD")
        assert len(data) == 1
        assert data[0].close_price == Decimal("2500.0")
        assert data[0].timestamp == 1704067200
