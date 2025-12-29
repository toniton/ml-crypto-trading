import pytest
from backtest.backtest_data_loader import BacktestDataLoader


class TestBacktestDataLoader:

    @pytest.fixture
    def mock_data_dir(self, tmp_path):
        """Create a mock data file."""
        d = tmp_path / "data"
        d.mkdir()

        # Create a mock CSV file
        csv_content = """timestamp;open;high;low;close;volume;marketCap
2023-01-01 00:00:00;100;110;90;105;1000;1000000
2023-01-01 01:00:00;105;115;95;110;1100;1100000
"""
        p = d / "btc-usd.csv"
        p.write_text(csv_content)
        return str(d)

    def test_load_and_get_data(self, mock_data_dir):
        loader = BacktestDataLoader(mock_data_dir)
        data = loader.load("btc-usd")

        # Verify load
        assert len(data) == 2
        assert data[0].close_price == 105.0
        assert data[1].close_price == 110.0

        ts1 = data[0].timestamp
        ts2 = data[1].timestamp

        # Verify random access
        dp1 = loader.get_data("btc-usd", ts1)
        assert dp1 is not None
        assert dp1.close_price == 105.0

        dp2 = loader.get_data("btc-usd", ts2)
        assert dp2 is not None
        assert dp2.close_price == 110.0

        # Verify non-existent
        assert loader.get_data("btc-usd", 9999999999) is None
        assert loader.get_data("unknown", ts1) is None

    def test_file_not_found(self, tmp_path):
        loader = BacktestDataLoader(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            loader.load("non-existent")
