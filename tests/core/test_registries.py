import pytest

from src.core.registry import MultiRegistry, Registry


class TestRegistry:
    def test_register_and_get(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)

        assert reg.get("a") == 1

    def test_get_missing_key_raises(self):
        reg: Registry[str, int] = Registry()

        with pytest.raises(ValueError, match="not registered"):
            reg.get("missing")

    def test_register_duplicate_key_raises(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)

        with pytest.raises(ValueError, match="already registered"):
            reg.register("a", 2)

    def test_replace_overwrites(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)
        reg.replace("a", 2)

        assert reg.get("a") == 2

    def test_find_returns_none_for_missing(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)

        assert reg.find("a") == 1
        assert reg.find("missing") is None

    def test_unregister_removes_and_returns(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)

        assert reg.unregister("a") == 1
        assert "a" not in reg

    def test_unregister_missing_key_raises(self):
        reg: Registry[str, int] = Registry()

        with pytest.raises(ValueError, match="not registered"):
            reg.unregister("missing")

    def test_keys_and_contains(self):
        reg: Registry[str, int] = Registry()
        reg.register("a", 1)
        reg.register("b", 2)

        assert sorted(reg.keys()) == ["a", "b"]
        assert "a" in reg
        assert "c" not in reg


class TestMultiRegistry:
    def test_register_preserves_registration_order(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("k", 1)
        reg.register("k", 3)
        reg.register("k", 2)

        assert reg.get("k") == [1, 3, 2]

    def test_get_returns_copy(self):
        reg: MultiRegistry[str, list] = MultiRegistry()
        reg.register("k", [1])
        entries = reg.get("k")
        entries.append(99)

        assert reg.get("k") == [[1]]

    def test_get_missing_key_raises(self):
        reg: MultiRegistry[str, int] = MultiRegistry()

        with pytest.raises(ValueError, match="not registered"):
            reg.get("missing")

    def test_get_first(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("k", 10)
        reg.register("k", 20)

        assert reg.get_first("k") == 10

    def test_unregister_removes_single_entry(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("k", 1)
        reg.register("k", 2)
        reg.unregister("k", 1)

        assert reg.get("k") == [2]

    def test_unregister_last_entry_deletes_key(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("k", 1)
        reg.unregister("k", 1)

        assert "k" not in reg
        with pytest.raises(ValueError, match="not registered"):
            reg.get("k")

    def test_unregister_missing_entry_raises(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("k", 1)

        with pytest.raises(ValueError, match="not registered"):
            reg.unregister("k", 2)
        with pytest.raises(ValueError, match="not registered"):
            reg.unregister("missing", 1)

    def test_keys_and_contains(self):
        reg: MultiRegistry[str, int] = MultiRegistry()
        reg.register("a", 1)
        reg.register("b", 2)

        assert sorted(reg.keys()) == ["a", "b"]
        assert "a" in reg
        assert "c" not in reg