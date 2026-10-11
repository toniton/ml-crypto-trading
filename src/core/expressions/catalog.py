from typing import Any, Dict, List

from src.core.expressions.schema import (
    ExpressionSchemaResponse,
    ExpressionScope,
    ExpressionValueType,
    FunctionSpec,
    OperatorSpec,
    ParameterSpec,
    SyntaxConstructSpec,
    VariableSpec,
)


class ExpressionCatalog:
    OPERATORS: List[OperatorSpec] = [
        OperatorSpec(
            symbol="+",
            name="Addition",
            category="Arithmetic",
            precedence=4,
            description="Adds two numeric values together",
            example="close + 10.5",
        ),
        OperatorSpec(
            symbol="-",
            name="Subtraction / Negation",
            category="Arithmetic",
            precedence=4,
            description="Subtracts right operand from left, or negates a value",
            example="close - avg_entry",
        ),
        OperatorSpec(
            symbol="*",
            name="Multiplication",
            category="Arithmetic",
            precedence=5,
            description="Multiplies two numeric values",
            example="equity * 0.02",
        ),
        OperatorSpec(
            symbol="/",
            name="Division",
            category="Arithmetic",
            precedence=5,
            description="Divides left operand by right operand",
            example="equity / close",
        ),
        OperatorSpec(
            symbol=">",
            name="Greater Than",
            category="Comparison",
            precedence=3,
            description="Returns true if left value is strictly greater than right value",
            example="close > sma(20)",
        ),
        OperatorSpec(
            symbol="<",
            name="Less Than",
            category="Comparison",
            precedence=3,
            description="Returns true if left value is strictly less than right value",
            example="rsi(14) < 30",
        ),
        OperatorSpec(
            symbol=">=",
            name="Greater Than or Equal",
            category="Comparison",
            precedence=3,
            description="Returns true if left value is greater than or equal to right value",
            example="close >= avg_entry * 1.05",
        ),
        OperatorSpec(
            symbol="<=",
            name="Less Than or Equal",
            category="Comparison",
            precedence=3,
            description="Returns true if left value is less than or equal to right value",
            example="pnl <= -100",
        ),
        OperatorSpec(
            symbol="==",
            name="Equality",
            category="Comparison",
            precedence=3,
            description="Returns true if both operands are equal",
            example="signal == 1",
        ),
        OperatorSpec(
            symbol="!=",
            name="Inequality",
            category="Comparison",
            precedence=3,
            description="Returns true if operands are not equal",
            example="signal != 0",
        ),
        OperatorSpec(
            symbol="and",
            name="Logical AND",
            category="Logical",
            precedence=2,
            description="Returns true if both conditions evaluate to true",
            example="rsi(14) < 30 and close > sma(50)",
        ),
        OperatorSpec(
            symbol="or",
            name="Logical OR",
            category="Logical",
            precedence=1,
            description="Returns true if either condition evaluates to true",
            example="pnl > 500 or pnl < -200",
        ),
        OperatorSpec(
            symbol="not",
            name="Logical NOT",
            category="Logical",
            precedence=6,
            description="Inverts a boolean condition",
            example="not (close < sma(200))",
        ),
    ]

    SYNTAX_CONSTRUCTS: List[SyntaxConstructSpec] = [
        SyntaxConstructSpec(
            name="Parenthesized Grouping",
            syntax_pattern="(<expression>)",
            description="Groups sub-expressions to control evaluation order and precedence",
            example="(equity * 0.02) / atr(14)",
        ),
        SyntaxConstructSpec(
            name="Ternary Conditional Expression",
            syntax_pattern="<value_if_true> if <condition> else <value_if_false>",
            description="Returns the first value if the condition is truthy, otherwise returns the fallback value",
            example="equity * 0.05 if confidence > 0.8 else equity * 0.01",
        ),
    ]

    FUNCTIONS: List[FunctionSpec] = [
        FunctionSpec(
            name="rsi",
            display_name="Relative Strength Index (RSI)",
            category="Technical Indicators",
            description=(
                "Calculates the Relative Strength Index momentum oscillator over a historical candle window (0 to 100)."
            ),
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=True,
                    default=14,
                    min_value=2,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="rsi(period: int = 14) -> number",
            example="rsi(14)",
            autocomplete_snippet="rsi(${1:14})",
        ),
        FunctionSpec(
            name="sma",
            display_name="Simple Moving Average (SMA)",
            category="Technical Indicators",
            description="Calculates the arithmetic average of closing prices over the specified candle period.",
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=True,
                    default=20,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="sma(period: int = 20) -> number",
            example="sma(20)",
            autocomplete_snippet="sma(${1:20})",
        ),
        FunctionSpec(
            name="ema",
            display_name="Exponential Moving Average (EMA)",
            category="Technical Indicators",
            description="Calculates the exponentially weighted moving average giving more weight to recent prices.",
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=True,
                    default=12,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="ema(period: int = 12) -> number",
            example="ema(12)",
            autocomplete_snippet="ema(${1:12})",
        ),
        FunctionSpec(
            name="atr",
            display_name="Average True Range (ATR)",
            category="Technical Indicators",
            description="Measures market volatility by averaging the true ranges over the specified candle period.",
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=True,
                    default=14,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="atr(period: int = 14) -> number",
            example="atr(14)",
            autocomplete_snippet="atr(${1:14})",
        ),
        FunctionSpec(
            name="highest",
            display_name="Rolling Highest (Maximum)",
            category="Technical Indicators",
            description="Returns the highest (maximum) value of a candle series over the prior N closed candles.",
            parameters=[
                ParameterSpec(
                    name="series",
                    type=ExpressionValueType.STRING,
                    description="Price or volume series name (e.g. high, low, close, open, volume)",
                    required=True,
                ),
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of prior candles",
                    required=True,
                    default=20,
                    min_value=1,
                ),
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="highest(series: series, period: int) -> number",
            example="highest(high, 20)",
            autocomplete_snippet="highest(${1:high}, ${2:20})",
        ),
        FunctionSpec(
            name="lowest",
            display_name="Rolling Lowest (Minimum)",
            category="Technical Indicators",
            description="Returns the lowest (minimum) value of a candle series over the prior N closed candles.",
            parameters=[
                ParameterSpec(
                    name="series",
                    type=ExpressionValueType.STRING,
                    description="Price or volume series name (e.g. high, low, close, open, volume)",
                    required=True,
                ),
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of prior candles",
                    required=True,
                    default=20,
                    min_value=1,
                ),
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="lowest(series: series, period: int) -> number",
            example="lowest(low, 20)",
            autocomplete_snippet="lowest(${1:low}, ${2:20})",
        ),
        FunctionSpec(
            name="max",
            display_name="Maximum",
            category="Math & Statistics",
            description="Returns the greatest value among the supplied arguments.",
            parameters=[
                ParameterSpec(
                    name="args",
                    type=ExpressionValueType.NUMBER,
                    description="Two or more numeric values",
                    required=True,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="max(a, b, ...) -> number",
            example="max(close, sma(50))",
            autocomplete_snippet="max(${1:val1}, ${2:val2})",
        ),
        FunctionSpec(
            name="min",
            display_name="Minimum",
            category="Math & Statistics",
            description="Returns the lowest value among the supplied arguments.",
            parameters=[
                ParameterSpec(
                    name="args",
                    type=ExpressionValueType.NUMBER,
                    description="Two or more numeric values",
                    required=True,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="min(a, b, ...) -> number",
            example="min(balance * 0.1, 1000)",
            autocomplete_snippet="min(${1:val1}, ${2:val2})",
        ),
        FunctionSpec(
            name="avg",
            display_name="Average",
            category="Math & Statistics",
            description="Returns the arithmetic mean of the supplied arguments.",
            parameters=[
                ParameterSpec(
                    name="args",
                    type=ExpressionValueType.NUMBER,
                    description="Two or more numeric values",
                    required=True,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="avg(a, b, ...) -> number",
            example="avg(high, low, close)",
            autocomplete_snippet="avg(${1:high}, ${2:low})",
        ),
        FunctionSpec(
            name="abs",
            display_name="Absolute Value",
            category="Math & Statistics",
            description="Returns the non-negative magnitude of a number.",
            parameters=[
                ParameterSpec(
                    name="val",
                    type=ExpressionValueType.NUMBER,
                    description="Numeric input",
                    required=True,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="abs(val: number) -> number",
            example="abs(pnl)",
            autocomplete_snippet="abs(${1:pnl})",
        ),
        FunctionSpec(
            name="clamp",
            display_name="Clamp Value",
            category="Utility",
            description="Constrains a value to lie within the given lower and upper bounds.",
            parameters=[
                ParameterSpec(
                    name="val",
                    type=ExpressionValueType.NUMBER,
                    description="Input value to clamp",
                    required=True,
                ),
                ParameterSpec(
                    name="min_val",
                    type=ExpressionValueType.NUMBER,
                    description="Lower bound",
                    required=True,
                ),
                ParameterSpec(
                    name="max_val",
                    type=ExpressionValueType.NUMBER,
                    description="Upper bound",
                    required=True,
                ),
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="clamp(val, min_val, max_val) -> number",
            example="clamp(equity * 0.02 / atr(14), min_qty, balance * 0.5)",
            autocomplete_snippet="clamp(${1:val}, ${2:min_val}, ${3:max_val})",
        ),
        FunctionSpec(
            name="round",
            display_name="Round",
            category="Utility",
            description="Rounds a number to a given number of decimal places.",
            parameters=[
                ParameterSpec(
                    name="val",
                    type=ExpressionValueType.NUMBER,
                    description="Numeric input",
                    required=True,
                ),
                ParameterSpec(
                    name="digits",
                    type=ExpressionValueType.NUMBER,
                    description="Decimal places (default 0)",
                    required=False,
                    default=0,
                ),
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="round(val: number, digits: int = 0) -> number",
            example="round(position_qty * 0.5, 4)",
            autocomplete_snippet="round(${1:val}, ${2:decimals})",
        ),
        FunctionSpec(
            name="regime",
            display_name="Market Regime",
            category="Market Regime",
            description=(
                "Returns the current classified market regime (e.g. TRENDING_UP, "
                "TRENDING_DOWN, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY, ILLIQUID, UNKNOWN)."
            ),
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=False,
                    default=20,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.STRING,
            signature="regime(period: int = 20) -> string",
            example="regime() == 'TRENDING_UP'",
            autocomplete_snippet="regime(${1:20})",
        ),
        FunctionSpec(
            name="volatility",
            display_name="Market Volatility (NATR)",
            category="Market Regime",
            description=(
                "Calculates the normalized Average True Range volatility percentage "
                "over the specified candle period."
            ),
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=False,
                    default=20,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="volatility(period: int = 20) -> number",
            example="volatility(20)",
            autocomplete_snippet="volatility(${1:20})",
        ),
        FunctionSpec(
            name="trend_strength",
            display_name="Trend Strength",
            category="Market Regime",
            description=(
                "Quantifies directional momentum divergence between fast and "
                "slow moving averages over the candle window."
            ),
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=False,
                    default=20,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="trend_strength(period: int = 20) -> number",
            example="trend_strength(20)",
            autocomplete_snippet="trend_strength(${1:20})",
        ),
        FunctionSpec(
            name="liquidity",
            display_name="Market Liquidity",
            category="Market Regime",
            description="Measures average candle trading volume across the specified lookback window.",
            parameters=[
                ParameterSpec(
                    name="period",
                    type=ExpressionValueType.NUMBER,
                    description="Lookback period in number of candles",
                    required=False,
                    default=20,
                    min_value=1,
                )
            ],
            return_type=ExpressionValueType.NUMBER,
            signature="liquidity(period: int = 20) -> number",
            example="liquidity(20)",
            autocomplete_snippet="liquidity(${1:20})",
        ),
        FunctionSpec(
            name="spread",
            display_name="Market Spread",
            category="Market Regime",
            description="Returns current normalized bid-ask spread percentage relative to close price.",
            parameters=[],
            return_type=ExpressionValueType.NUMBER,
            signature="spread() -> number",
            example="spread()",
            autocomplete_snippet="spread()",
        ),
    ]

    VARIABLES: List[VariableSpec] = [
        # Market Data
        VariableSpec(
            name="close",
            display_name="Close Price",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Latest closing / ticker price of the traded symbol",
            example_value=64250.0,
        ),
        VariableSpec(
            name="high",
            display_name="High Price",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Highest price recorded during the current market period",
            example_value=64800.0,
        ),
        VariableSpec(
            name="low",
            display_name="Low Price",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Lowest price recorded during the current market period",
            example_value=63900.0,
        ),
        VariableSpec(
            name="volume",
            display_name="Volume",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="units",
            description="Trading volume accumulated in the current interval",
            example_value=1420.5,
        ),
        VariableSpec(
            name="range",
            display_name="Price Range",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Absolute difference between period high and low (high - low)",
            example_value=900.0,
        ),
        VariableSpec(
            name="range_pct",
            display_name="Price Range %",
            category="Market Data",
            type=ExpressionValueType.NUMBER,
            unit="%",
            description="Price range as a percentage of close price ((high - low) / close)",
            example_value=0.014,
        ),

        # Account & Portfolio
        VariableSpec(
            name="balance",
            display_name="Available Balance",
            category="Account & Portfolio",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Unallocated settlement cash available for new orders",
            example_value=19882.50,
        ),
        VariableSpec(
            name="equity",
            display_name="Total Equity",
            category="Account & Portfolio",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Total portfolio net worth (available balance + open position market value)",
            example_value=23412.00,
        ),
        VariableSpec(
            name="risk_pct",
            display_name="Target Risk %",
            category="Account & Portfolio",
            type=ExpressionValueType.NUMBER,
            unit="%",
            description="Configured maximum portfolio equity risk percentage per trade (e.g. 0.02 for 2%)",
            example_value=0.02,
        ),

        # Position State
        VariableSpec(
            name="position_qty",
            display_name="Current Position Quantity",
            category="Position State",
            type=ExpressionValueType.NUMBER,
            unit="qty",
            description="Current open quantity held in base asset",
            example_value=0.055,
        ),
        VariableSpec(
            name="avg_entry",
            display_name="Average Entry Price",
            category="Position State",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Volume-weighted average execution price of current open position",
            example_value=62100.0,
        ),
        VariableSpec(
            name="pnl",
            display_name="Unrealized PnL",
            category="Position State",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Unrealized profit and loss in quote currency for open position",
            example_value=118.25,
        ),
        VariableSpec(
            name="realized_pnl",
            display_name="Realized PnL",
            category="Position State",
            type=ExpressionValueType.NUMBER,
            unit="$",
            description="Cumulative realized profit and loss from closed trades in session",
            example_value=450.00,
        ),

        # Consensus & Signals
        VariableSpec(
            name="signal",
            display_name="Consensus Direction",
            category="Consensus & Signals",
            type=ExpressionValueType.NUMBER,
            unit="signal",
            description="Directional trade signal (+1 for BUY, -1 for SELL, 0 for NEUTRAL)",
            example_value=1,
            applicable_scopes=[
                ExpressionScope.DYNAMIC_QUANTITY,
                ExpressionScope.GUARD_CONDITION,
                ExpressionScope.GENERAL_CALCULATION,
            ],
        ),
        VariableSpec(
            name="confidence",
            display_name="Model Confidence",
            category="Consensus & Signals",
            type=ExpressionValueType.NUMBER,
            unit="ratio",
            description="Normalized confidence score (0.0 to 1.0) of consensus decision",
            example_value=0.85,
            applicable_scopes=[
                ExpressionScope.DYNAMIC_QUANTITY,
                ExpressionScope.GUARD_CONDITION,
                ExpressionScope.GENERAL_CALCULATION,
            ],
        ),
        VariableSpec(
            name="vote_ratio",
            display_name="Agent Vote Ratio",
            category="Consensus & Signals",
            type=ExpressionValueType.NUMBER,
            unit="ratio",
            description="Proportion of agent committee votes supporting current trade action",
            example_value=0.75,
            applicable_scopes=[
                ExpressionScope.DYNAMIC_QUANTITY,
                ExpressionScope.GUARD_CONDITION,
                ExpressionScope.GENERAL_CALCULATION,
            ],
        ),

        # Asset Rules
        VariableSpec(
            name="min_qty",
            display_name="Minimum Order Quantity",
            category="Asset Rules",
            type=ExpressionValueType.NUMBER,
            unit="qty",
            description="Exchange lot-size minimum required for placing orders on symbol",
            example_value=0.001,
        ),
        VariableSpec(
            name="decimals",
            display_name="Quote Decimals",
            category="Asset Rules",
            type=ExpressionValueType.NUMBER,
            unit="precision",
            description="Allowed precision for order size formatting",
            example_value=4,
        ),

        # Market Regime
        VariableSpec(
            name="regime",
            display_name="Current Market Regime",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            unit="regime",
            description=(
                "Current classified market regime string (TRENDING_UP, TRENDING_DOWN, "
                "RANGING, HIGH_VOLATILITY, LOW_VOLATILITY, ILLIQUID, UNKNOWN)"
            ),
            example_value="TRENDING_UP",
        ),
        VariableSpec(
            name="volatility",
            display_name="Market Volatility (NATR)",
            category="Market Regime",
            type=ExpressionValueType.NUMBER,
            unit="%",
            description="Current normalized average true range volatility percentage (ATR / close)",
            example_value=0.024,
        ),
        VariableSpec(
            name="trend_strength",
            display_name="Trend Strength",
            category="Market Regime",
            type=ExpressionValueType.NUMBER,
            unit="momentum",
            description="Quantified directional trend strength metric (-1.0 to 1.0)",
            example_value=0.015,
        ),
        VariableSpec(
            name="liquidity",
            display_name="Market Liquidity",
            category="Market Regime",
            type=ExpressionValueType.NUMBER,
            unit="vol",
            description="Average volume metric across recent candle window",
            example_value=1500.0,
        ),
        VariableSpec(
            name="spread",
            display_name="Market Spread",
            category="Market Regime",
            type=ExpressionValueType.NUMBER,
            unit="%",
            description="Normalized bid-ask spread percentage relative to close price",
            example_value=0.0005,
        ),

        # Regime Constants
        VariableSpec(
            name="TRENDING_UP",
            display_name="Regime: TRENDING_UP",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'TRENDING_UP'",
            example_value="TRENDING_UP",
        ),
        VariableSpec(
            name="TRENDING_DOWN",
            display_name="Regime: TRENDING_DOWN",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'TRENDING_DOWN'",
            example_value="TRENDING_DOWN",
        ),
        VariableSpec(
            name="RANGING",
            display_name="Regime: RANGING",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'RANGING'",
            example_value="RANGING",
        ),
        VariableSpec(
            name="HIGH_VOLATILITY",
            display_name="Regime: HIGH_VOLATILITY",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'HIGH_VOLATILITY'",
            example_value="HIGH_VOLATILITY",
        ),
        VariableSpec(
            name="LOW_VOLATILITY",
            display_name="Regime: LOW_VOLATILITY",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'LOW_VOLATILITY'",
            example_value="LOW_VOLATILITY",
        ),
        VariableSpec(
            name="ILLIQUID",
            display_name="Regime: ILLIQUID",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'ILLIQUID'",
            example_value="ILLIQUID",
        ),
        VariableSpec(
            name="UNKNOWN",
            display_name="Regime: UNKNOWN",
            category="Market Regime",
            type=ExpressionValueType.STRING,
            description="Regime constant literal 'UNKNOWN'",
            example_value="UNKNOWN",
        ),
    ]

    @classmethod
    def get_schema(cls) -> ExpressionSchemaResponse:
        scope_map: Dict[ExpressionScope, List[str]] = {}
        all_function_names = [f.name for f in cls.FUNCTIONS]

        for scope in ExpressionScope:
            vars_for_scope = [
                v.name for v in cls.VARIABLES
                if scope in v.applicable_scopes
            ]
            scope_map[scope] = vars_for_scope + all_function_names

        return ExpressionSchemaResponse(
            language_version="1.0.0",
            max_expression_length=1000,
            operators=cls.OPERATORS,
            syntax_constructs=cls.SYNTAX_CONSTRUCTS,
            functions=cls.FUNCTIONS,
            variables=cls.VARIABLES,
            scopes=scope_map,
        )

    @classmethod
    def get_sample_context_variables(cls, scope: ExpressionScope) -> Dict[str, Any]:
        return {
            v.name: v.example_value
            for v in cls.VARIABLES
            if scope in v.applicable_scopes
        }
