from decimal import Decimal
import pytest
from backtest.backtest_data_loader import BacktestDataLoader


class TestBacktestDataLoader:

    @pytest.fixture
    def mock_data_dir(self, tmp_path):
        """Create a mock data file."""
        d = tmp_path / "data"
        d.mkdir()

        # Create a mock CSV file with semicolon
        csv_content = """timestamp;open;high;low;close;volume;marketCap
2023-01-01 00:00:00;100;110;90;105;1000;1000000
2023-01-01 01:00:00;105;115;95;110;1100;1100000
"""
        p = d / "btc-usd.csv"
        p.write_text(csv_content)

        # Create another with comma and underscores
        csv_content_comma = """timestamp,open,high,low,close,volume,marketCap
2023-01-01 00:00:00,10,11,9,10.5,100,100000
2023-01-01 01:00:00,10.5,11.5,9.5,11,110,110000
"""
        p2 = d / "ETH_USD.csv"
        p2.write_text(csv_content_comma)

        return str(d)

    def test_load_and_get_data_decimal(self, mock_data_dir):
        loader = BacktestDataLoader(mock_data_dir)
        data = loader.load("btc-usd")

        # Verify load
        assert len(data) == 2
        assert isinstance(data[0].close_price, Decimal)
        assert data[0].close_price == Decimal("105.0")
        assert data[1].close_price == Decimal("110.0")

        ts1 = data[0].timestamp
        ts2 = data[1].timestamp

        # Verify random access
        dp1 = loader.get_data("btc-usd", ts1)
        assert dp1 is not None
        assert dp1.close_price == Decimal("105.0")

        dp2 = loader.get_data("btc-usd", ts2)
        assert dp2 is not None
        assert dp2.close_price == Decimal("110.0")

    def test_flexible_filename_loading(self, mock_data_dir):
        loader = BacktestDataLoader(mock_data_dir)

        # Test loading ETH_USD.csv with different variations
        data1 = loader.load("ETH_USD")
        assert len(data1) == 2
        assert data1[0].close_price == Decimal("10.5")

        data2 = loader.load("eth_usd")
        assert len(data2) == 2

        data3 = loader.load("eth-usd")
        assert len(data3) == 2

        data4 = loader.load("ETH-USD")
        assert len(data4) == 2

    def test_file_not_found(self, tmp_path):
        loader = BacktestDataLoader(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            loader.load("non-existent")
