from __future__ import annotations

from src.llm.math_normalizer import DelimiterStream, normalize_math_delimiters


class TestNormalizeMathDelimiters:
    def test_display_math_becomes_own_block(self):
        assert normalize_math_delimiters(r"\[ x \approx y \]") == "\n\n$$\nx \\approx y\n$$\n\n"

    def test_inline_math_promoted_to_display_block(self):
        assert normalize_math_delimiters(r"\( a \times b \)") == "\n\n$$\na \\times b\n$$\n\n"

    def test_formula_inside_prose_gets_container_whitespace(self):
        raw = "So total is:\n\n\\[ Total = 0.02282867 + 0.00005 \\]\n\nwhich matches."
        rendered = normalize_math_delimiters(raw)
        assert "$$\nTotal = 0.02282867 + 0.00005\n$$" in rendered
        assert "\n\n$$" in rendered and "$$\n\n" in rendered

    def test_reported_net_worth_example_keeps_latex(self):
        raw = (
            r"\[ 0.02282867 \text{ BTC} \times $64,249.78/\text{BTC}"
            r" \approx $1,466.70 \]"
        )
        rendered = normalize_math_delimiters(raw)
        assert rendered.startswith("\n\n$$\n")
        assert rendered.endswith("$$\n\n")
        assert r"\text{ BTC}" in rendered
        assert r"\times" in rendered
        assert r"\approx" in rendered
        assert r"\$64,249.78" in rendered
        assert r"\$1,466.70" in rendered

    def test_currency_inside_math_is_escaped_for_katex(self):
        rendered = normalize_math_delimiters(r"\[ value = 0.02 \times $64,249.78 \]")
        assert rendered == "\n\n$$\nvalue = 0.02 \\times \\$64,249.78\n$$\n\n"

    def test_excess_newlines_collapsed(self):
        assert normalize_math_delimiters("a\n\n\n\nb") == "a\n\nb"

    def test_currency_in_prose_not_treated_as_math(self):
        assert normalize_math_delimiters("worth $1,467") == "worth $1,467"

    def test_plain_text_unchanged(self):
        assert normalize_math_delimiters("hello world") == "hello world"


class TestDelimiterStream:
    def test_reassembles_delimiter_split_across_chunks(self):
        stream = DelimiterStream()
        assert stream.push("\\") == ""
        assert stream.push("[x \\approx y \\]") == "\n\n$$\nx \\approx y\n$$\n\n"
        assert stream.flush() == ""

    def test_inline_delimiters_promoted_across_chunks(self):
        stream = DelimiterStream()
        parts = []
        for token in [r"\(a", r" \times ", r"b\)"]:
            parts.append(stream.push(token))
        parts.append(stream.flush())
        assert "".join(parts) == "\n\n$$\na \\times b\n$$\n\n"

    def test_plain_text_flows_through_unchanged(self):
        stream = DelimiterStream()
        parts = []
        for token in ["hello ", "world", "!"]:
            parts.append(stream.push(token))
        parts.append(stream.flush())
        assert "".join(parts) == "hello world!"