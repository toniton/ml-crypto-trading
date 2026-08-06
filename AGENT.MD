# Agent Guide: Integrating with MCT MCP Server

This guide explains how to integrate AI agents with the MCT trading bot using the Model Context Protocol (MCP) server for runtime configuration updates.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [MCP Server Setup](#mcp-server-setup)
3. [Available Tools](#available-tools)
4. [Integration Patterns](#integration-patterns)
5. [Common Use Cases](#common-use-cases)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Install the MCP Package

The MCP server requires the `mcp` package (already in `requirements.txt`):

```bash
pip install mcp
```

### 2. Run the MCP Server

Start the trading bot with the MCP server enabled:

```bash
TRADING_CONFIG_PATH=/path/to/trading-config.yaml python -m mcp_server.server
```

### 3. Connect Your Agent

Configure your AI agent to use the MCP server. See [Integration Patterns](#integration-patterns) for examples.

---

## MCP Server Setup

### Environment Configuration

The MCP server requires one environment variable:

**`TRADING_CONFIG_PATH`**: Absolute path to your `trading-config.yaml` file.

```bash
export TRADING_CONFIG_PATH=/home/user/ml-crypto-trading/trading-config.yaml
```

### Server Initialization

The MCP server initializes with:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "trading-config",
    instructions=(
        "Provides tools to inspect and update the trading bot's runtime configuration. "
        "Changes are written atomically to the YAML config file and picked up by the "
        "running application on its next config-reload cycle (every 30 seconds)."
    ),
)
```

### Server Location

The MCP server is located at:
```
mcp_server/server.py
```

---

## Available Tools

### 1. `get_trading_config()`

**Purpose**: Query the current trading configuration.

**Parameters**: None

**Returns**:
```json
{
  "consensus": {
    "buy": 1.3,
    "sell": 0.5
  },
  "dynamic_quantity": "max(min_qty, (balance * 0.02) / close)"
}
```

**Use Cases**:
- Audit current settings
- Verify changes were applied
- Report current state to trader

**Example**:
```python
config = agent.call_tool("get_trading_config", {})
print(f"Current buy threshold: {config['consensus']['buy']}")
```

---

### 2. `update_consensus(buy, sell)`

**Purpose**: Update consensus thresholds for buy/sell signals.

**Parameters**:
- `buy` (float): Buy consensus threshold (must be > 0)
- `sell` (float): Sell consensus threshold (must be > 0 and ≤ buy)

**Returns**:
```json
{
  "updated": {
    "consensus": {
      "buy": 1.5,
      "sell": 0.7
    }
  }
}
```

**Validation Rules**:
- Both values must be positive
- `sell` must not exceed `buy`
- Invalid values raise `ValueError`

**Use Cases**:
- Tighten buy threshold when market is uncertain
- Relax sell threshold to exit positions faster
- Adapt to market volatility conditions

**Example**:
```python
# Tighten criteria during high volatility
agent.call_tool("update_consensus", {
    "buy": 1.8,    # Require stronger agreement to buy
    "sell": 0.6    # Still relatively easy to sell
})
```

---

### 3. `update_dynamic_quantity(formula)`

**Purpose**: Update the position sizing formula at runtime.

**Parameters**:
- `formula` (str): Python expression for position sizing. Empty string disables dynamic sizing.

**Returns**:
```json
{
  "updated": {
    "dynamic_quantity": "(balance * 0.05 / close) * (1.5 if rsi(14) < 30 else 1.0)"
  }
}
```

**Available Variables**:
- `min_qty`: Minimum order quantity per asset
- `equity`: Current account equity
- `risk_pct`: Risk percentage setting
- `close`: Current market price
- `signal`: Signal strength (-1 to 1)
- `pnl`: Current profit/loss

**Available Indicators**:
- `rsi(period)`: Relative Strength Index
- `ema(period)`: Exponential Moving Average
- `sma(period)`: Simple Moving Average

**Use Cases**:
- Scale position size based on market conditions
- Disable dynamic sizing (pass empty string)
- Implement aggressive/conservative strategies

**Example - Scaled Position Sizing**:
```python
# Scale based on volatility
agent.call_tool("update_dynamic_quantity", {
    "formula": "min_qty * (2.0 if rsi(14) < 30 else 1.0 if rsi(14) > 70 else 1.5)"
})
```

**Example - Disable Dynamic Sizing**:
```python
# Use minimum quantity only
agent.call_tool("update_dynamic_quantity", {
    "formula": ""
})
```

---

## Integration Patterns

### Pattern 1: Claude AI Agent (Native MCP)

Claude natively supports MCP servers. Configure in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trading-config": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "TRADING_CONFIG_PATH": "/path/to/trading-config.yaml"
      }
    }
  }
}
```

**Usage**:
```
User: What's the current consensus threshold?
Claude: I'll check the trading configuration.
[Claude calls get_trading_config()]
Response: The buy threshold is 1.3 and sell is 0.5.
```

---

### Pattern 2: Custom Python Agent

Integrate the MCP server in your own Python agent:

```python
import asyncio
from mcp.server.fastmcp import FastMCP

# Load the MCP server
from mcp_server.server import mcp

async def agent_trading_logic():
    # Get current config
    config_result = await mcp.call_tool("get_trading_config", {})
    current_consensus = config_result[0].text  # JSON string
    
    # Parse and analyze
    import json
    config = json.loads(current_consensus)
    
    # Make decisions
    if config['consensus']['buy'] < 1.5:
        # Adjust based on market analysis
        await mcp.call_tool("update_consensus", {
            "buy": 1.6,
            "sell": 0.7
        })

# Run agent
asyncio.run(agent_trading_logic())
```

---

### Pattern 3: REST API Wrapper

Wrap the MCP server in a REST API for language-agnostic access:

```python
from fastapi import FastAPI
from mcp_server.config_reader import read_config, write_config

app = FastAPI()

@app.get("/api/config")
async def get_config():
    return read_config(os.environ["TRADING_CONFIG_PATH"])

@app.post("/api/consensus")
async def update_consensus_endpoint(buy: float, sell: float):
    # Validation
    if buy <= 0 or sell <= 0 or sell > buy:
        raise ValueError("Invalid parameters")
    
    path = os.environ["TRADING_CONFIG_PATH"]
    data = read_config(path)
    data.setdefault("consensus", {})
    data["consensus"]["buy"] = buy
    data["consensus"]["sell"] = sell
    write_config(path, data)
    
    return {"updated": data["consensus"]}
```

---

## Common Use Cases

### Use Case 1: Adaptive Consensus Based on Market Volatility

Agents can monitor market conditions and adjust consensus thresholds:

```python
async def adapt_to_volatility(current_vix):
    """Tighten consensus when market is uncertain"""
    
    if current_vix > 30:  # High volatility
        # Require stronger agreement
        await mcp.call_tool("update_consensus", {
            "buy": 2.0,
            "sell": 0.4
        })
    elif current_vix < 15:  # Low volatility
        # Relax criteria
        await mcp.call_tool("update_consensus", {
            "buy": 1.2,
            "sell": 0.7
        })
```

---

### Use Case 2: Dynamic Position Scaling

Agents can implement sophisticated position sizing based on market conditions:

```python
async def scale_positions(rsi_period=14):
    """Scale position size inversely to RSI"""
    
    formula = f"""
    if rsi({rsi_period}) < 30:
        max(min_qty, equity * 0.10 / close)  # Oversold: aggressive
    elif rsi({rsi_period}) > 70:
        max(min_qty, equity * 0.02 / close)  # Overbought: conservative
    else:
        max(min_qty, equity * 0.05 / close)  # Neutral: moderate
    """.strip()
    
    await mcp.call_tool("update_dynamic_quantity", {"formula": formula})
```

---

### Use Case 3: A/B Testing Strategies

Agents can switch between strategies and compare performance:

```python
strategies = {
    "aggressive": {
        "consensus": {"buy": 1.0, "sell": 0.8},
        "formula": "equity * 0.10 / close"
    },
    "conservative": {
        "consensus": {"buy": 2.0, "sell": 0.3},
        "formula": "min_qty"
    }
}

async def switch_strategy(strategy_name):
    """Switch between predefined strategies"""
    
    strategy = strategies[strategy_name]
    
    await mcp.call_tool("update_consensus", strategy["consensus"])
    await mcp.call_tool("update_dynamic_quantity", {"formula": strategy["formula"]})
    
    return f"Switched to {strategy_name} strategy"
```

---

### Use Case 4: Market Recovery Protocol

Agents can implement recovery logic after market downturns:

```python
async def market_recovery_protocol(recovery_phase):
    """Gradually restore trading after market recovery"""
    
    phases = {
        1: {"buy": 3.0, "sell": 0.1, "formula": ""},  # Conservative: no dynamic sizing
        2: {"buy": 2.0, "sell": 0.3, "formula": "min_qty * 2"},
        3: {"buy": 1.5, "sell": 0.5, "formula": "max(min_qty, equity * 0.03 / close)"},
    }
    
    phase = phases.get(recovery_phase, phases[3])
    
    await mcp.call_tool("update_consensus", {
        "buy": phase["buy"],
        "sell": phase["sell"]
    })
    
    if phase["formula"]:
        await mcp.call_tool("update_dynamic_quantity", {"formula": phase["formula"]})
```

---

## Best Practices

### 1. **Validate Before Update**

Always validate that new values make sense:

```python
async def safe_update_consensus(buy, sell):
    # Validate
    if buy <= 0 or sell <= 0:
        return {"error": "Values must be positive"}
    
    if sell > buy:
        return {"error": "Sell must be <= buy"}
    
    # Get current for comparison
    current = await mcp.call_tool("get_trading_config", {})
    
    # Update
    return await mcp.call_tool("update_consensus", {"buy": buy, "sell": sell})
```

---

### 2. **Track Configuration Changes**

Maintain a log of configuration changes:

```python
import json
from datetime import datetime

async def log_config_change(tool_name, params, result):
    """Log all configuration changes"""
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "tool": tool_name,
        "parameters": params,
        "result": result
    }
    
    with open("config_changes.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
```

---

### 3. **Gradual Updates**

Implement changes gradually to avoid market shock:

```python
async def gradual_consensus_update(target_buy, target_sell, steps=5):
    """Gradually transition to new consensus values"""
    
    current = await mcp.call_tool("get_trading_config", {})
    current_config = json.loads(current[0].text)
    
    current_buy = current_config["consensus"]["buy"]
    current_sell = current_config["consensus"]["sell"]
    
    for step in range(1, steps + 1):
        progress = step / steps
        new_buy = current_buy + (target_buy - current_buy) * progress
        new_sell = current_sell + (target_sell - current_sell) * progress
        
        await mcp.call_tool("update_consensus", {
            "buy": round(new_buy, 2),
            "sell": round(new_sell, 2)
        })
        
        await asyncio.sleep(60)  # Wait between updates
```

---

### 4. **Fallback Strategy**

Always have a safe fallback configuration:

```python
DEFAULT_SAFE_CONFIG = {
    "consensus": {"buy": 2.0, "sell": 0.3},
    "dynamic_quantity": "min_qty"  # Minimal risk
}

async def emergency_fallback():
    """Return to safe defaults on error"""
    
    try:
        # Attempt risky operation
        await agent_trading_logic()
    except Exception as e:
        print(f"Error: {e}. Falling back to safe config.")
        await mcp.call_tool("update_consensus", DEFAULT_SAFE_CONFIG["consensus"])
        await mcp.call_tool("update_dynamic_quantity", {"formula": DEFAULT_SAFE_CONFIG["dynamic_quantity"]})
```

---

### 5. **Monitor Configuration Drift**

Periodically verify that applied changes match expectations:

```python
async def verify_configuration(expected_config):
    """Verify applied configuration matches expectations"""
    
    current = await mcp.call_tool("get_trading_config", {})
    current_config = json.loads(current[0].text)
    
    if current_config != expected_config:
        print(f"Configuration mismatch!")
        print(f"Expected: {expected_config}")
        print(f"Current: {current_config}")
        return False
    
    return True
```

---

## Troubleshooting

### Issue: "Environment variable TRADING_CONFIG_PATH is not set"

**Solution**: Ensure the environment variable is exported before running:

```bash
export TRADING_CONFIG_PATH=/absolute/path/to/trading-config.yaml
python -m mcp_server.server
```

---

### Issue: "Configuration file not found"

**Solution**: Verify the file path is absolute and the file exists:

```bash
ls -la /path/to/trading-config.yaml
```

---

### Issue: "Changes not applied immediately"

**Expected Behavior**: The application picks up changes on its next config-reload cycle (typically every 30 seconds).

**To verify changes were written**: Check the YAML file directly:

```bash
cat /path/to/trading-config.yaml
```

---

### Issue: "Tool validation errors"

**Common causes**:
- `buy <= 0`: Buy threshold must be positive
- `sell > buy`: Sell must not exceed buy threshold
- Invalid formula syntax: Check Python expression syntax

**Solution**: Validate parameters before calling:

```python
if buy <= 0 or sell <= 0 or sell > buy:
    raise ValueError("Invalid consensus parameters")
```

---

### Issue: "Connection refused" when connecting from another machine

**Solution**: The MCP server runs locally by default. For remote access, wrap it in a REST API or use SSH tunneling:

```bash
# SSH tunnel
ssh -L 8000:localhost:8000 user@remote-host
```

---

## Advanced Topics

### Custom Tool Extensions

You can extend the MCP server with additional tools:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("trading-config")

@mcp.tool()
def get_trading_history(days: int = 7) -> dict:
    """Get trading history for the last N days"""
    # Implementation here
    pass

@mcp.tool()
def analyze_performance() -> dict:
    """Analyze current trading performance"""
    # Implementation here
    pass
```

---

### Testing Agent Integration

Test your agent integration with the MCP server:

```python
# tests/unit/mcp_server/test_agent_integration.py

import anyio
from mcp_server.server import mcp

def test_agent_can_get_config():
    result = anyio.run(mcp.call_tool, "get_trading_config", {})
    assert "consensus" in result
    assert "dynamic_quantity" in result

def test_agent_can_update_consensus():
    result = anyio.run(mcp.call_tool, "update_consensus", {"buy": 1.5, "sell": 0.6})
    assert result[0].text.contains("updated")
```

---

## Resources

- [Model Context Protocol (MCP) Docs](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCT Configuration Guide](docs/configuration.md)
- [MCT Architecture](docs/architecture.md)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review test cases in `tests/unit/mcp_server/`
3. Open an issue on [GitHub](https://github.com/toniton/ml-crypto-trading)
4. Join the [Discord community](https://discord.gg/vZh8w3Sz)
