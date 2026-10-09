from src.core.weekday import Weekday


class TestWeekday:
    def test_enum_values_and_ordering(self):
        assert Weekday.MONDAY == 0
        assert Weekday.TUESDAY == 1
        assert Weekday.WEDNESDAY == 2
        assert Weekday.THURSDAY == 3
        assert Weekday.FRIDAY == 4
        assert Weekday.SATURDAY == 5
        assert Weekday.SUNDAY == 6

    def test_is_weekday_property(self):
        assert Weekday.MONDAY.is_weekday is True
        assert Weekday.FRIDAY.is_weekday is True
        assert Weekday.SATURDAY.is_weekday is False
        assert Weekday.SUNDAY.is_weekday is False

    def test_is_weekend_property(self):
        assert Weekday.MONDAY.is_weekend is False
        assert Weekday.FRIDAY.is_weekend is False
        assert Weekday.SATURDAY.is_weekend is True
        assert Weekday.SUNDAY.is_weekend is True
